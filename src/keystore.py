from bitcoin import bip32, ec, script, hashes
from bitcoin.networks import NETWORKS
import secp256k1
import os
import ujson as json
import ure as re
from ubinascii import unhexlify, hexlify
from rng import get_random_bytes

def multi(*args):
    return script.multisig(args[0], args[1:])

def sortedmulti(*args):
    return multi(args[0], *sorted(args[1:]))

DESCRIPTOR_SCRIPTS = {
    "pkh": script.p2pkh,
    "wpkh": script.p2wpkh,
    "sh": script.p2sh,
    "wsh": script.p2wsh,
    "multi": multi,
    "sortedmulti": sortedmulti,
}

class KeyStore:
    def __init__(self, seed=None, storage_root="/flash"):
        self.root = None
        self._wallets = []
        self.network = None
        self.storage_root = storage_root
        self.storage_path = None
        self.idkey = None
        self.fingerprint = None
        self.load_seed(seed)

    def load_seed(self, seed):
        if seed is not None:
            self.root = bip32.HDKey.from_seed(seed)
            self.fingerprint = self.root.child(0).fingerprint
            # id key to sign wallet files stored on untrusted external chip
            self.idkey = self.root.child(0x1D, hardened=True)

    def get_xpub(self, derivation):
        xpub = self.root.derive(derivation)
        ver = bip32.detect_version(derivation)
        xpub.version = ver
        return xpub.to_public()

    def load_wallets(self, network_name):
        self.network = NETWORKS[network_name]
        fingerprint = hexlify(self.fingerprint).decode()
        self.storage_path = "%s/%s/%s" % (self.storage_root, network_name, fingerprint)
        # FIXME: refactor with for loop
        try: # create network folder
            d = "/".join(self.storage_path.split("/")[:-1])
            os.mkdir(d)
        except:
            pass
        try:
            os.mkdir(self.storage_path)
        except:
            pass
        files = [f[0] for f in os.ilistdir(self.storage_path) if f[0].endswith("_wallet.json")]
        self._wallets = []
        for fname in files:
            fname = self.storage_path+"/"+fname
            with open(fname) as f:
                content = f.read()
            with open(fname.replace(".json",".sig"),"rb") as f:
                sig = ec.Signature.parse(f.read())
            if self.idkey.verify(sig, hashes.sha256(content)):
                self._wallets.append(Wallet.parse(content, self.network, fname=fname))
            else:
                raise RuntimeError("Invalid signature for wallet")

    def get_wallet_fname(self):
        files = [int(f[0].split("_")[0]) for f in os.ilistdir(self.storage_path) if f[0].endswith("_wallet.json")]
        if len(files) > 0:
            idx = max(files)+1
        else:
            idx = 0
        fname = self.storage_path+"/"+("%d_wallet.json" % idx)
        return fname

    def create_wallet(self, name, descriptor):
        for w in self._wallets:
            if w.name == name:
                raise ValueError("Wallet '%s' already exists", name)
        fname = self.get_wallet_fname()
        w = Wallet(name, descriptor, self.network, fname=fname)
        data = w.save(fname)
        h = hashes.sha256(data)
        sig = self.idkey.sign(h)
        with open(fname.replace(".json",".sig"),"wb") as f:
            f.write(sig.serialize())
        self._wallets.append(w)

    def check_new_wallet(self, name, descriptor):
        for w in self._wallets:
            if w.name == name:
                raise ValueError("Wallet \"%s\" already exists" % name)
        w = Wallet(name, descriptor, self.network)
        includes_myself = False
        for arg in w.args:
            try:
                if self.owns_key(arg):
                    includes_myself = True
            except:
                continue
        if not includes_myself:
            raise ValueError("Wallet is not controlled by my key")
        return w

    def owns_key(self, key):
        if key.fingerprint == self.fingerprint:
            mykey = self.root.derive(key.parent_derivation).to_public()
            if key.key == mykey:
                return True
        return False

    def delete_wallet(self, w):
        if w in self._wallets:
            idx = self._wallets.index(w)
            self._wallets.pop(idx)
            os.remove(w.fname)
            os.remove(w.fname.replace(".json",".sig"))

    def get_wallet_by_name(self, name):
        for w in self.wallets:
            if w == name:
                return w

    @property
    def wallets(self):
        return self._wallets

    @property
    def is_initialized(self):
        return (self.root is not None)

    def check_psbt(self, tx):
        obj = {}
        # print how much we are spending and where
        total_in = 0
        wallet = None
        # detect wallet tx inputs belong to
        for w in self.wallets:
            if w.owns(tx.inputs[0]):
                wallet = w
                break
        if wallet is None:
            raise ValueError("Can't find the wallet owning input")
        # calculate the amount we are spending
        for inp in tx.inputs:
            total_in += inp.witness_utxo.value
            if not wallet.owns(psbt_in=inp):
                raise ValueError("Mixed inputs from different wallets!")
        obj["total_in"] = total_in
        change_out = 0 # value that goes back to us
        send_outputs = []
        for i, out in enumerate(tx.outputs):
            # check if it is a change or not:
            if wallet.owns(psbt_out=out, tx_out=tx.tx.vout[i]):
                change_out += tx.tx.vout[i].value
            else:
                send_outputs.append(tx.tx.vout[i])
        obj["wallet"] = wallet
        obj["spending"] = total_in-change_out
        obj["send_outputs"] = [{"value": out.value, "address": out.script_pubkey.address(self.network)} for out in send_outputs]
        obj["fee"] = total_in-change_out-sum([out.value for out in send_outputs])
        return obj

    def sign(self, tx):
        # good practice to randomize context 
        # it reduces chances of side-channel attacks
        secp256k1.context_randomize(get_random_bytes(32))
        tx.sign_with(self.root)
        return tx

class DerivedKey:
    def __init__(self, key, fingerprint=None, parent_derivation=None, address_derivation="_"):
        self.key = key
        self.fingerprint = fingerprint
        self.parent_derivation = parent_derivation
        self.address_derivation = address_derivation

    @classmethod
    def parse(cls, s):
        fingerprint = None
        parent_derivation = None
        address_derivation = "_"
        m = re.match("\[(.*)\](.*)", s)
        if m:
            parent_derivation = m.group(1)
            if not parent_derivation.startswith("m/"):
                arr = parent_derivation.split("/")
                fingerprint = unhexlify(arr[0])
                if len(fingerprint) != 4:
                    raise ValueError("Invalid fingerprint in derivation path")
                parent_derivation = "m/"+"/".join(arr[1:])
            parent_derivation = bip32.parse_path(parent_derivation)
            s = m.group(2)
        if "/" in s:
            arr = s.split("/")
            address_derivation = "/".join(arr[1:])
            s = arr[0]
        key = bip32.HDKey.from_base58(s)
        return cls(key, fingerprint, parent_derivation, address_derivation)

    def __repr__(self):
        s = ""
        if self.parent_derivation is not None:
            s = "[%s]" % bip32.path_to_str(self.parent_derivation, self.fingerprint)
        s += self.key.to_base58()
        return s

def parse_argument(e):
    # for now int, HDKey or pubkey
    # int
    if len(e) < 4:
        return int(e)
    # pubkey
    if len(e) == 66 or len(e) == 130:
        return ec.PublicKey.parse(unhexlify(e))
    # otherwise - xpub
    return DerivedKey.parse(e)

def parse_descriptor(desc):
    # remove checksum if it is there
    desc = desc.split("#")[0]
    # for now only pkh, sh, wpkh, wsh, multi, sortedmulti
    is_multisig = False
    d = desc
    # re.match doesnt work for some reason
    arr = d.split("(")
    wrappers = arr[:-1]
    d = arr[-1].split(")")[0]
    wrappers = list(reversed([DESCRIPTOR_SCRIPTS[w] for w in wrappers]))
    args = []
    for e in d.split(","):
        args.append(parse_argument(e))
    return wrappers, args

class Wallet:
    def __init__(self, name, descriptor, network, fname=None):
        self.fname = fname
        self.name = name
        self.descriptor = descriptor
        self.network = network
        self.wrappers, self.args = parse_descriptor(descriptor)

    @property
    def is_multisig(self):
        return ((multi in self.wrappers) or (sortedmulti in self.wrappers))

    @property
    def policy(self):
        # TODO: improve policy parsing
        p = "Single key"
        if self.is_multisig:
            p = "%d of %d multisig" % (self.args[0], len(self.args)-1)
        return p

    @property
    def script_type(self):
        # TODO: check that script type is one of good ones
        return "-".join([w.__name__ for w in reversed(self.wrappers)])

    @property
    def keys(self):
        return [key for key in self.args[1:]] if self.is_multisig else self.args

    def script(self, idx, change=False):
        args = []
        # derive args if possible
        for arg in self.args:
            # if DerivedKey we should get public key with right index
            try:
                pub = arg.key.child(int(change)).child(idx).key
                args.append(pub)
            except:
                args.append(arg)
        sc = self.wrappers[0](*args)
        for wrapper in self.wrappers[1:]:
            sc = wrapper(sc)
        return sc

    def address(self, idx, change=False):
        sc = self.script(idx, change)
        return sc.address(network=self.network)

    def owns(self, psbt_in=None, psbt_out=None, tx_out=None):
        """Pass psbt_in or psbt_out + tx_out to check if it is owned by the wallet"""
        # FIXME: implement check
        bip32_derivations = None
        output = None
        if psbt_in is not None:
            bip32_derivations = psbt_in.bip32_derivations
            output = psbt_in.witness_utxo
        if psbt_out is not None:
            bip32_derivations = psbt_out.bip32_derivations
            output = tx_out
        args = []
        for arg in self.args:
            # check if it is DerivedKey
            try:
                fingerprint = arg.fingerprint
            except:
                args.append(arg)
                continue
            derived = False
            parent_len = len(arg.parent_derivation)
            for pub in bip32_derivations:
                if ((bip32_derivations[pub].fingerprint == arg.fingerprint) and
                    (len(bip32_derivations[pub].derivation) == (parent_len+2)) and
                    (bip32_derivations[pub].derivation[:parent_len] == arg.parent_derivation)):
                    der = bip32_derivations[pub].derivation[parent_len:]
                    if der[0] > 1:
                        raise ValueError("Change index cant be more than one")
                    if der[1] > 0x80000000:
                        raise ValueError("Address index cant be hardened")
                    # FIXME: add check if index is too large
                    mypub = arg.key.derive(der).key
                    if mypub != pub:
                        return False
                    else:
                        args.append(mypub)
                        derived = True
                        break
            if not derived:
                return False
        sc = self.wrappers[0](*args)
        for wrapper in self.wrappers[1:]:
            sc = wrapper(sc)
        return (sc == output.script_pubkey)

    def save(self, fname):
        obj = {"name": self.name, "descriptor": self.descriptor}
        data = json.dumps(obj)
        with open(fname,"w") as f:
            f.write(data)
        return data

    @classmethod
    def load(cls, fname, network):
        with open(fname, "r") as f:
            content = f.read()
        return cls.parse(content, network, fname)

    @classmethod
    def parse(cls, s, network, fname=None):
        content = json.loads(s)
        return cls(content["name"], content["descriptor"], network, fname)
