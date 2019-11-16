from bitcoin import bip32, ec, script, hashes
from bitcoin.networks import NETWORKS
import os
import ujson as json
import ure as re
from ubinascii import unhexlify, hexlify

is_simulator = False
try:
    import pyb
except:
    is_simulator = True

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
    "sortedmulti": sortedmulti
}

class KeyStore:
    def __init__(self, seed=None):
        self.root = None
        self._wallets = []
        self.network = None
        self.storage_path = None
        self.load_seed(seed)
        self.idkey = None

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
        fingerprint = hexlify(self.fingerprint).decode('utf-8')
        if is_simulator:
            self.storage_path = "%s/%s" % (network_name, fingerprint)
        else:
            self.storage_path = "/flash/%s/%s" % (network_name, fingerprint)
        # FIXME: refactor with for loop
        try: # network folder
            d = "/".join(self.storage_path.split("/")[:-1])
            os.mkdir(d)
        except:
            pass
        try:
            os.mkdir(self.storage_path)
        except:
            pass # probably exists
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

    def delete_wallet(self, w):
        if w in self._wallets:
            self._wallets.pop(w)
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
    wrappers = []
    d = desc
    m = re.match('(\w+)\((.*)\)$', d)
    while m:
        wrappers.append(m.group(1))
        d = m.group(2)
        m = re.match('(\w+)\((.*)\)$', d)
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
        # FIXME: parse descriptor here
        self.wrappers, self.args = parse_descriptor(descriptor)

    def address(self, idx, change=False):
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
        return sc.address(network=self.network)

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
