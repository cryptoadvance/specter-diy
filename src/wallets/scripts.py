from bitcoin import bip32, script
from binascii import unhexlify, hexlify

class ScriptError(Exception):
    pass

class DescriptorScript:
    def script(self, derivation):
        raise WalletError("Not implemented")

    def get_keys(self):
        raise WalletError("Not implemented")

    def __str__(self):
        return ""

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, str(self))

class SingleKey(DescriptorScript):
    def __init__(self, key):
        self.key = key

    @classmethod
    def parse(cls, desc):
        if not desc.startswith("wpkh(") or not desc.endswith(")"):
            raise ScriptError("Invalid script format: %s" % desc)
        key = DescriptorKey.parse(desc[len("wpkh("):-1])
        return cls(key)

    def scriptpubkey(self, derivation):
        """Derivation should be an array of two ints: [change 0 or 1, index]"""
        if len(derivation) != 2:
            raise ScriptError("Derivation should be of len 2")
        change, idx = derivation
        if change not in [0,1] or idx < 0:
            raise ScriptError("Invalid change or index")
        pub = self.key.derive([change, idx])
        return script.p2wpkh(pub)

    def get_keys(self):
        return [self.key]

    def __str__(self):
        return "wpkh(%s)" % str(self.key)

class Multisig(DescriptorScript):
    def __init__(self, sigs_required:int, keys:list, sort_keys:bool=True):
        if sigs_required > len(keys) or sigs_required <= 0:
            raise ScriptError("Can't do %d of %d multisig" % (sigs_required, len(keys)))
        self.sigs_required = sigs_required
        self.sort_keys = sort_keys
        self.keys = keys

    def get_keys(self):
        return self.keys

    @classmethod
    def parse(cls, desc):
        # removing two trailing brackets because there is multi( as well
        if not desc.startswith("wsh(") or not desc.endswith("))"):
            raise ScriptError("Invalid script format: %s" % desc)
        desc = desc[len("wsh("):-2]
        multi, args = desc.split("(")
        if multi == "sortedmulti":
            sort_keys = True
        elif multi == "multi":
            sort_keys = False
        else:
            raise ScriptError("Invalid script format: %s" % desc)
        sigs_required, *keys = args.split(",")
        sigs_required = int(sigs_required)
        keys = [DescriptorKey.parse(key) for key in keys]
        return cls(sigs_required, keys, sort_keys)

    def scriptpubkey(self, derivation):
        """Derivation should be an array of two ints: [change 0 or 1, index]"""
        if len(derivation) != 2:
            raise ScriptError("Derivation should be of len 2")
        change, idx = derivation
        if change not in [0,1] or idx < 0:
            raise ScriptError("Invalid change or index")
        pubs = [key.derive([change, idx]) for key in self.keys]
        if self.sort_keys:
            pubs = sorted(pubs)
        return script.p2wsh(script.multisig(self.sigs_required, pubs))

    def __str__(self):
        keystring = ",".join([str(key) for key in self.keys])
        desc = "multi(%d,%s)" % (self.sigs_required, keystring)
        if self.sort_keys:
            desc = "sorted"+desc
        return "wsh(%s)" % desc


class DescriptorKey:
    """A key with derivation path in the form [fingerprint/derivation]xpub"""
    def __init__(self, xpub, fingerprint=None, derivation=None):
        if isinstance(xpub, str):
            self.key = bip32.HDKey.from_base58(xpub)
        else:
            self.key = xpub
        if derivation is not None:
            if isinstance(derivation, str):
                self.derivation = bip32.parse_path(derivation)
            else:
                self.derivation = derivation
            self.fingerprint = fingerprint
        else:
            # we don't know derivation - use it as root
            self.fingerprint = self.key.child(0).fingerprint
            self.derivation = []

    def derive(self, derivation):
        """Returns a key derived from this key"""
        if isinstance(derivation, str):
            derivation = bip32.parse_path(derivation)
        xpub = self.key.derive(derivation)
        derivation = self.derivation + derivation
        return DescriptorKey(xpub, self.fingerprint, derivation)

    def sec(self):
        return self.key.sec()

    @classmethod
    def parse(cls, s):
        # remove spaces
        s.strip().replace(" ","")
        fingerprint = None
        derivation = None
        # ok we probably have at least derivation
        if s.startswith("["):
            try:
                der, xpub = s[1:].split("]")
            except:
                raise WalletError("Invalid key format: %s" % s)
            if der.startswith("m/"):
                derivation = bip32.parse_path(der)
            else:
                fingerprint = unhexlify(der[:8])
                derivation = bip32.parse_path("m"+der[8:])
        else:
            xpub = s
        key = bip32.HDKey.from_base58(xpub)
        return cls(key, fingerprint, derivation)

    def __str__(self):
        xpub = self.key.to_base58()
        prefix = ""
        if self.derivation is not None:
            prefix = "[%s]" % bip32.path_to_str(self.derivation)
            if self.fingerprint is not None:
                prefix = prefix.replace("m", hexlify(self.fingerprint).decode())
        return prefix+xpub

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, str(self))