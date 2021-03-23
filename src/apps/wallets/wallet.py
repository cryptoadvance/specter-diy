from app import AppError
from platform import maybe_mkdir, delete_recursively
import json
from bitcoin import ec, hashes, script
from bitcoin.networks import NETWORKS
from bitcoin.psbt import DerivationPath
from bitcoin.descriptor import Descriptor
from bitcoin.descriptor.arguments import AllowedDerivation
import hashlib
from .screens import WalletScreen, WalletInfoScreen
from .commands import DELETE, EDIT, MENU, INFO
from gui.screens import Menu
import lvgl as lv

class WalletError(AppError):
    NAME = "Wallet error"


class Wallet:
    """
    Wallet class,
    wrapped=False - native segwit,
    wrapped=True - nested segwit
    """

    GAP_LIMIT = 20

    def __init__(self, desc, path=None, name="Untitled"):
        self.name = name
        self.path = path
        if self.path is not None:
            self.path = self.path.rstrip("/")
            maybe_mkdir(self.path)
        self.descriptor = desc
        # receive and change gap limits
        self.gaps = [self.GAP_LIMIT for b in range(self.descriptor.num_branches)]
        self.name = name
        self.unused_recv = 0
        self.keystore = None

    async def show(self, network, show_screen):
        while True:
            scr = WalletScreen(self, network, idx=self.unused_recv)
            cmd = await show_screen(scr)
            if cmd == MENU:
                buttons = [
                    (INFO, "Show detailed information"),
                    (EDIT, lv.SYMBOL.EDIT + " Change the name"),
                    # value, label,                            enabled, color
                    (DELETE, lv.SYMBOL.TRASH + " Delete wallet", True, 0x951E2D),
                ]
                cmd = await show_screen(Menu(buttons, last=(255, None), title=self.name, note="What do you want to do?"))
                if cmd == 255:
                    continue
                elif cmd == INFO:
                    keys = self.get_key_dicts(network)
                    for k in keys:
                        k["mine"] = True if self.keystore and self.keystore.owns(k["key"]) else False
                    await show_screen(WalletInfoScreen(self.name, self.full_policy, keys, self.is_miniscript))
                    continue
            # other commands go to the wallet manager
            return cmd

    @property
    def is_watchonly(self):
        """Checks if the wallet is watch-only (doesn't control the key) or not"""
        return not (
            any([self.keystore.owns(k) if self.keystore else False for k in self.keys])
            or
            any([k.is_private for k in self.descriptor.keys])
        )

    def save(self, keystore, path=None):
        # wallet has access to keystore only if it's saved or loaded from file
        self.keystore = keystore
        if path is not None:
            self.path = path.rstrip("/")
        if self.path is None:
            raise WalletError("Path is not defined")
        maybe_mkdir(self.path)
        desc = str(self.descriptor)
        keystore.save_aead(self.path + "/descriptor", plaintext=desc.encode())
        obj = {"gaps": self.gaps, "name": self.name, "unused_recv": self.unused_recv}
        meta = json.dumps(obj).encode()
        keystore.save_aead(self.path + "/meta", plaintext=meta)

    def wipe(self):
        if self.path is None:
            raise WalletError("I don't know path...")
        delete_recursively(self.path, include_self=True)

    def get_address(self, idx: int, network: str, change=False):
        sc, gap = self.script_pubkey([int(change), idx])
        return sc.address(NETWORKS[network]), gap

    def script_pubkey(self, derivation: list):
        """Returns script_pubkey and gap limit"""
        # derivation can be only two elements
        change, idx = derivation
        if change not in [0, 1]:
            raise WalletError("Invalid change index %d - can be 0 or 1" % change)
        if idx < 0:
            raise WalletError("Invalid index %d - can't be negative" % idx)
        sc = self.descriptor.derive(idx, branch_index=change).script_pubkey()
        return sc, self.gaps[change]

    @property
    def fingerprint(self):
        """Fingerprint of the wallet - hash160(descriptor)"""
        return hashes.hash160(str(self.descriptor))[:4]

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
        # check that script_pubkey matches
        sc, _ = self.script_pubkey(derivation)
        return sc == output.script_pubkey

    def get_derivation(self, scope):
        # check if wallet derivation is there (custom psbt field)
        derivation = None
        wallet_key = b"\xfc\xca\x01" + self.fingerprint
        # derivation is a sequence of 2 bytes - branch_index and wildcard index
        if wallet_key in scope.unknown and len(scope.unknown[wallet_key]) == 8:
            der = scope.unknown[wallet_key]
            derivation = []
            for i in range(len(der) // 4):
                idx = int.from_bytes(der[4 * i : 4 * i + 4], "little")
                derivation.append(idx)
            return derivation
        # otherwise we need standard derivation
        for pub in scope.bip32_derivations:
            if len(scope.bip32_derivations[pub].derivation) >= 2:
                der = self.descriptor.check_derivation(scope.bip32_derivations[pub])
                if der is not None:
                    return der

    def update_gaps(self, psbt=None, known_idxs=None):
        gaps = self.gaps
        # update from psbt
        if psbt is not None:
            scopes = []
            for inp in psbt.inputs:
                if self.owns(inp):
                    scopes.append(inp)
            for i, out in enumerate(psbt.outputs):
                if self.owns(psbt_out=out, tx_out=psbt.tx.vout[i]):
                    scopes.append(out)
            for scope in scopes:
                res = self.get_derivation(scope)
                if res is not None:
                    change, idx = res
                    if idx + self.GAP_LIMIT > gaps[change]:
                        gaps[change] = idx + self.GAP_LIMIT + 1
        # update from gaps arg
        if known_idxs is not None:
            for i, gap in enumerate(gaps):
                if known_idxs[i] is not None and known_idxs[i] + self.GAP_LIMIT > gap:
                    gaps[i] = known_idxs[i] + self.GAP_LIMIT
        self.unused_recv = gaps[0] - self.GAP_LIMIT
        self.gaps = gaps

    def fill_psbt(self, psbt, fingerprint):
        """Fills derivation paths in inputs"""
        for scope in psbt.inputs:
            # fill derivation paths
            wallet_key = b"\xfc\xca\x01" + self.fingerprint
            if wallet_key not in scope.unknown:
                continue
            der = scope.unknown[wallet_key]
            wallet_derivation = []
            for i in range(len(der) // 4):
                idx = int.from_bytes(der[4 * i : 4 * i + 4], "little")
                wallet_derivation.append(idx)
            # find keys with our fingerprint
            for key in self.descriptor.keys:
                if key.fingerprint == fingerprint:
                    pub = key.derive(wallet_derivation).get_public_key()
                    # fill our derivations
                    scope.bip32_derivations[pub] = DerivationPath(
                        fingerprint, key.derivation + wallet_derivation
                    )
            # fill script
            scope.witness_script = self.descriptor.derive(*wallet_derivation).witness_script()
            if self.descriptor.sh:
                scope.redeem_script = self.descriptor.derive(*wallet_derivation).redeem_script()
        return psbt

    @property
    def keys(self):
        return self.descriptor.keys

    @property
    def wrapped(self):
        return self.descriptor.sh    

    def get_key_dicts(self, network):
        keys = [{
            "key": k,
        } for k in self.keys]
        # get XYZ-pubs
        slip132_ver = "xpub"
        canonical_ver = "xpub"
        if self.descriptor.is_pkh:
            if self.wrapped:
                slip132_ver = "ypub"
            else:
                slip132_ver = "zpub"
        elif self.descriptor.is_basic_multisig:
            if self.wrapped:
                slip132_ver = "Ypub"
            else:
                slip132_ver = "Zpub"
        for k in keys:
            k["is_private"] = k["key"].is_private
            ver = slip132_ver.replace("pub", "prv") if k["is_private"] else slip132_ver
            k["slip132"] = k["key"].to_string(NETWORKS[network][ver])
            ver = canonical_ver.replace("pub", "prv") if k["is_private"] else canonical_ver
            k["canonical"] = k["key"].to_string(NETWORKS[network][ver])
        return keys

    @classmethod
    def parse(cls, desc, path=None):
        name = "Untitled"
        if "&" in desc:
            name, desc = desc.split("&")
        w = cls.from_descriptor(desc, path)
        w.name = name
        return w

    @classmethod
    def from_descriptor(cls, desc:str, path):
        # remove checksum if it's there and all spaces
        desc = desc.split("#")[0].replace(" ", "")
        descriptor = Descriptor.from_string(desc)
        no_derivation = all([k.is_extended and k.allowed_derivation is None for k in descriptor.keys])
        if no_derivation:
            for k in descriptor.keys:
                if k.is_extended:
                    # allow /{0,1}/*
                    k.allowed_derivation = AllowedDerivation.default()
        return cls(descriptor, path)

    @classmethod
    def from_path(cls, path, keystore):
        """Loads wallet from the folder"""
        path = path.rstrip("/")
        _, desc = keystore.load_aead(path + "/descriptor")
        w = cls.from_descriptor(desc.decode(), path)
        _, meta = keystore.load_aead(path + "/meta")
        obj = json.loads(meta.decode())
        if "gaps" in obj:
            w.gaps = obj["gaps"]
        if "name" in obj:
            w.name = obj["name"]
        if "unused_recv" in obj:
            w.unused_recv = obj["unused_recv"]
        # wallet has access to keystore only if it's saved or loaded from file
        w.keystore = keystore
        return w

    @property
    def policy(self):
        if self.descriptor.is_segwit:
            p = "Nested Segwit, " if self.descriptor.is_wrapped else "Native Segwit, "
        else:
            p = "Legacy, "
        p += self.descriptor.brief_policy
        return p

    @property
    def full_policy(self):
        if self.descriptor.is_segwit:
            p = "Nested Segwit\n" if self.descriptor.is_wrapped else "Native Segwit\n"
        else:
            p = "Legacy\n"
        pp = self.descriptor.full_policy
        if not self.is_miniscript:
            p += pp
        else:
            p += "Miniscript:\n"+pp.replace(",",", ")
        return p

    @property
    def is_miniscript(self):
        return not (self.descriptor.is_basic_multisig or self.descriptor.is_pkh)

    def __str__(self):
        return "%s&%s" % (self.name, self.descriptor)

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, str(self))
