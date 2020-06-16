from platform import maybe_mkdir
from .scripts import SingleKey, Multisig
import json
from bitcoin import ec
from bitcoin.networks import NETWORKS
import hashlib

class WalletError(Exception):
    pass

class Wallet:
    SCRIPTS = [
        SingleKey, 
        Multisig,
    ]
    GAP_LIMIT = 20
    """
    Wallet class, 
    wrapped=False - native segwit, 
    wrapped=True - nested segwit
    """
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

    def save(self, key):
        if self.path is None:
            raise WalletError("Path is not defined")
        desc = self.descriptor()
        with open(self.path+"/descriptor", "w") as f:
            f.write(desc)
        sig = key.sign(hashlib.sha256(desc).digest())
        with open(self.path+"/descriptor.sig", "wb") as f:
            f.write(sig.serialize())
        obj = {
            "gaps": self.gaps,
            "name": self.name,
            "unused_recv": self.unused_recv
        }
        with open(self.path+"/meta.json", "w") as f:
            json.dump(obj, f)

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
        return self.script.scriptpubkey(derivation), self.gaps[change]

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
    def from_path(cls, path, pubkey):
        """Loads wallet from the folder"""
        path = path.rstrip("/")
        with open(path+"/descriptor", "r") as f:
            desc = f.read()
        with open(path+"/descriptor.sig", "rb") as f:
            sig = ec.Signature.parse(f.read())
        if not pubkey.verify(sig, hashlib.sha256(desc).digest()):
            raise WalletError("Wallet signature is invalid")
        w = cls.from_descriptor(desc, path)
        with open(path+"/meta.json", "r") as f:
            obj = json.load(f)
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

