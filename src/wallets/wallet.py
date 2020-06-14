from platform import maybe_mkdir
from .scripts import SingleKey, Multisig

class WalletError(Exception):
    pass

class Wallet:
    SCRIPTS = [
        SingleKey, 
        Multisig,
    ]
    """
    Wallet class, 
    wrapped=False - native segwit, 
    wrapped=True - nested segwit
    """
    def __init__(self, script, wrapped=False, path=None):
        self.path = path
        if path is not None:
            maybe_mkdir(path)
        if type(script) not in type(self).SCRIPTS:
            raise WalletError("%s not in %s" % (type(script), type(self).SCRIPTS))
        self.script = script
        self.wrapped = wrapped

    @classmethod
    def parse(cls, desc, path=None):
        return cls.from_descriptor(desc, path)

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
    def register(cls, scriptcls):
        """Registers an additional script class"""
        cls.SCRIPTS.append(scriptcls)

    def descriptor(self):
        desc = str(self.script)
        if self.wrapped:
            desc = "sh(%s)" % desc
        return desc

    def __str__(self):
        return self.descriptor()

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, str(self))

