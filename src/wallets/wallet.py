from platform import maybe_mkdir
from .scripts import SingleKey, Multisig
import json
from bitcoin import ec
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
            "name": self.name
        }
        with open(self.path+"/meta.json", "w") as f:
            json.dump(obj, f)

    @classmethod
    def parse(cls, desc, path=None):
        return cls.from_descriptor(desc, path)

    @classmethod
    def from_descriptor(cls, desc, path):
        # remove checksum if it's there and all spaces
        desc = desc.split("#")[0].replace(" ", "")
        name = "Untitled"
        if "&" in desc:
            name, desc = desc.split("&")
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
        return cls(script, wrapped, path, name=name)

    @classmethod
    def from_path(cls, path, pubkey):
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
        return w

    @classmethod
    def register(cls, scriptcls):
        """Registers an additional script class"""
        cls.SCRIPTS.append(scriptcls)

    def descriptor(self):
        desc = str(self.script)
        if self.wrapped:
            desc = "sh(%s)" % desc
        return desc

    def __str__(self):
        return "%s&%s" % (self.name, self.descriptor())

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, str(self))

