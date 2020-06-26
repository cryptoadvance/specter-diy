from platform import maybe_mkdir, delete_recursively
from .scripts import SingleKey, Multisig
import json
from bitcoin import ec, hashes, script
from bitcoin.networks import NETWORKS
from bitcoin.psbt import DerivationPath
import hashlib

class WalletError(Exception):
    pass

class Wallet:
    """
    Wallet class, 
    wrapped=False - native segwit, 
    wrapped=True - nested segwit
    """
    SCRIPTS = [
        SingleKey, 
        Multisig,
    ]
    GAP_LIMIT = 20
    def __init__(self, script, wrapped=False, path=None, name="Untitled"):
        self.name = name
        self.path = path
        if self.path is not None:
            self.path = self.path.rstrip("/")
            maybe_mkdir(self.path)
        if type(script) not in type(self).SCRIPTS:
            raise WalletError("%s not in %s" % (type(script), type(self).SCRIPTS))
        self.script = script
        self.wrapped = wrapped
        # receive and change gap limits
        self.gaps = [type(self).GAP_LIMIT, type(self).GAP_LIMIT]
        self.name = name
        self.unused_recv = 0

    def save(self, keystore, path=None):
        if path is not None:
            self.path = path
        if self.path is None:
            raise WalletError("Path is not defined")
        desc = self.descriptor()
        keystore.save_aead(self.path+"/descriptor", plaintext=desc.encode())
        obj = {
            "gaps": self.gaps,
            "name": self.name,
            "unused_recv": self.unused_recv
        }
        meta = json.dumps(obj).encode()
        keystore.save_aead(self.path+"/meta", plaintext=meta)

    def wipe(self):
        if self.path is None:
            raise WalletError("I don't know path...")
        delete_recursively(self.path, include_self=True)

    def get_address(self, idx:int, network:str, change=False):
        sc, gap = self.scriptpubkey([int(change), idx])
        return sc.address(NETWORKS[network]), gap

    def scriptpubkey(self, derivation:list):
        """Returns scriptpubkey and gap limit"""
        # derivation can be only two elements
        change, idx = derivation
        if change not in [0,1]:
            raise WalletError("Invalid change index %d - can be 0 or 1" % change)
        if idx < 0:
            raise WalletError("Invalid index %d - can't be negative" % idx)
        sc = self.script.scriptpubkey(derivation)
        if self.wrapped:
            sc = script.p2sh(sc)
        return sc, self.gaps[change]

    @property
    def fingerprint(self):
        """Fingerprint of the wallet - hash160(descriptor)"""
        return hashes.hash160(self.descriptor())[:4]

    def owns(self, psbt_in=None, psbt_out=None, tx_out=None):
        """
        Checks that psbt scope belongs to the wallet.
        Pass psbt_in or psbt_out + tx_out
        """
        output = None
        derivation = None
        if psbt_in is not None:
            output = psbt_in.witness_utxo
            derivation = self.get_derivation(psbt_in)
        if psbt_out is not None:
            output = tx_out
            derivation = self.get_derivation(psbt_out)

        # derivation not found
        if derivation is None:
            return False
        # check that scriptpubkey matches
        sc, _ = self.scriptpubkey(derivation)
        return (sc == output.script_pubkey)

    def get_derivation(self, scope):
        # check if wallet derivation is there (custom psbt field)
        derivation = None
        wallet_key = b"\xfc\xca\x01"+self.fingerprint
        # only 2-index derivations are allowed
        if wallet_key in scope.unknown and len(scope.unknown[wallet_key])==8:
            der = scope.unknown[wallet_key]
            derivation = []
            for i in range(len(der)//4):
                idx = int.from_bytes(der[4*i:4*i+4], 'little')
                derivation.append(idx)
            return derivation
        # otherwise we need standard derivation
        # we take any of the derivations and extract last two indexes
        for pub in scope.bip32_derivations:
            if len(scope.bip32_derivations[pub].derivation) >= 2:
                return scope.bip32_derivations[pub].derivation[-2:]

    def fill_psbt(self, psbt, fingerprint):
        """Fills derivation paths in inputs"""
        for scope in psbt.inputs:
            # fill derivation paths
            wallet_key = b"\xfc\xca\x01"+self.fingerprint
            if wallet_key not in scope.unknown:
                continue
            der = scope.unknown[wallet_key]
            wallet_derivation = []
            for i in range(len(der)//4):
                idx = int.from_bytes(der[4*i:4*i+4], 'little')
                wallet_derivation.append(idx)
            # find keys with our fingerprint
            for key in self.script.get_keys():
                if key.fingerprint == fingerprint:
                    pub = key.derive(wallet_derivation).get_public_key()
                    # fill our derivations
                    scope.bip32_derivations[pub] = DerivationPath(fingerprint, key.derivation + wallet_derivation)
            # fill script
            scope.witness_script = self.script.witness_script(wallet_derivation)
            if self.wrapped:
                scope.redeem_script = self.script.scriptpubkey(wallet_derivation)
        return psbt

    @classmethod
    def parse(cls, desc, path=None):
        name = "Untitled"
        if "&" in desc:
            name, desc = desc.split("&")
        w = cls.from_descriptor(desc, path)
        w.name = name
        return w

    @classmethod
    def from_descriptor(cls, desc, path):
        # remove checksum if it's there and all spaces
        desc = desc.split("#")[0].replace(" ", "")
        wrapped = False
        # detect wrapper
        if desc.startswith("sh("):
            if not desc.endswith(")"):
                raise WalletError("Failed parsing descriptor %s" % desc)
            wrapped = True
            desc = desc[len("sh("):-1]
        script = None
        for scriptcls in cls.SCRIPTS:
            # for every script class try to parse it
            try:
                script = scriptcls.parse(desc)
                # ok we got it
                break
            except:
                pass
        if script is None:
            raise WalletError("Can't find proper type for %s" % desc)
        return cls(script, wrapped, path)

    @classmethod
    def from_path(cls, path, keystore):
        """Loads wallet from the folder"""
        path = path.rstrip("/")
        _, desc = keystore.load_aead(path+"/descriptor")
        w = cls.from_descriptor(desc.decode(), path)
        _, meta = keystore.load_aead(path+"/meta")
        obj = json.loads(meta.decode())
        if "gaps" in obj:
            w.gaps = obj["gaps"]
        if "name" in obj:
            w.name = obj["name"]
        if "unused_recv" in obj:
            w.unused_recv = obj["unused_recv"]
        return w

    @classmethod
    def register(cls, scriptcls):
        """Registers an additional script class"""
        cls.SCRIPTS.append(scriptcls)

    def descriptor(self):
        """Returns descriptor of the wallet"""
        desc = str(self.script)
        if self.wrapped:
            desc = "sh(%s)" % desc
        return desc

    def __str__(self):
        return "%s&%s" % (self.name, self.descriptor())

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, str(self))

