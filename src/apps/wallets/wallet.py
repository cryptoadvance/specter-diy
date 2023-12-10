from app import AppError
import platform
from platform import maybe_mkdir, delete_recursively
import json
from embit import ec, hashes
from embit.networks import NETWORKS
from embit.psbt import DerivationPath
from embit.descriptor import Descriptor
from embit.descriptor.checksum import add_checksum
from embit.descriptor.arguments import AllowedDerivation
from embit.transaction import SIGHASH
from .screens import WalletScreen, WalletInfoScreen
from .commands import DELETE, EDIT, MENU, INFO, EXPORT
from gui.screens import Menu, QRAlert, Alert, Prompt
import lvgl as lv

class WalletError(AppError):
    NAME = "Wallet error"


class Wallet:

    GAP_LIMIT = 20
    DescriptorClass = Descriptor
    Networks = NETWORKS

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
                    (EXPORT, "Export wallet descriptor"),
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
                    await show_screen(WalletInfoScreen(self.name, self.full_policy, keys, self.is_complex))
                    continue
                elif cmd == EXPORT:
                    await self.export_menu(show_screen)
                    continue
            # other commands go to the wallet manager
            return cmd

    async def export_menu(self, show_screen):
        while True:
            buttons = [
                (None, "Export options"),
                (1, "Show QR code"),
                (2, "Save to SD card", platform.sdcard.is_present),
            ]
            menuitem = await show_screen(Menu(buttons, last=(255, None), title="Export wallet %s" % self.name))
            desc = add_checksum(str(self.descriptor.branch(0)))
            obj = {
                "descriptor": desc,
                "label": self.name,
            }
            if self.descriptor.num_branches > 2:
                obj["branches"] = [add_checksum(str(self.descriptor.branch(i))) for i in range(self.descriptor.num_branches)]
            if menuitem == 1:
                await show_screen(QRAlert(title="Export wallet %s" % self.name, qr_width=450,
                        message="Scan this QR code with compatible software wallet", qr_message=json.dumps(obj)))
            elif menuitem == 2:
                if not platform.sdcard.is_present:
                    raise WalletError("SD card is not present")
                with platform.sdcard as sd:
                    fname = "%s.json" % (self.name or "wallet")
                    if sd.file_exists(fname):
                        confirm = await show_screen(Prompt("Overwrite?", message="File %s already exists on the SD card. Overwrite?" % fname))
                        if not confirm:
                            return
                    with sd.open(fname, "w") as f:
                        json.dump(obj, f)
                await show_screen(Alert("Success!", "Wallet descriptor is written to\n\n%s" % fname))
            else:
                return

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

    def check_network(self, network):
        """
        Checks that all the keys belong to the network (version of xpub and network of private key).
        Returns True if all keys belong to the network, False otherwise.
        """
        # all possible xprv / xpub versions
        versions = [v for k,v in network.items() if k[1:] in ["prv","pub"]]
        for k in self.keys:
            if k.is_extended:
                if k.key.version not in versions:
                    return False
            elif k.is_private and isinstance(k.key, ec.PrivateKey):
                if k.key.network["wif"] != network["wif"]:
                    return False
        return True

    def wipe(self):
        if self.path is None:
            raise WalletError("I don't know path...")
        delete_recursively(self.path, include_self=True)

    def get_address(self, idx: int, network: str, branch_index=0):
        desc, gap = self.get_descriptor(idx, branch_index)
        return desc.address(self.Networks[network]), gap

    def get_descriptor(self, idx: int, branch_index=0):
        if branch_index < 0 or branch_index >= self.descriptor.num_branches:
            raise WalletError("Invalid branch index %d - can be between 0 and %d" % (branch_index, self.descriptor.num_branches))
        if idx < 0 or idx >= 0x80000000:
            raise WalletError("Invalid index %d" % idx)
        return self.descriptor.derive(idx, branch_index=branch_index), self.gaps[branch_index]

    def script_pubkey(self, derivation: list):
        """Returns script_pubkey and gap limit"""
        # derivation can be only two elements
        branch_idx, idx = derivation
        desc, gap = self.get_descriptor(idx, branch_idx)
        return desc.script_pubkey(), gap

    @property
    def fingerprint(self):
        """Fingerprint of the wallet - hash160(descriptor)"""
        return hashes.hash160(str(self.descriptor))[:4]

    def owns(self, psbt_scope):
        """
        Checks that psbt scope belongs to the wallet.
        """
        return self.descriptor.owns(psbt_scope)

    def get_derivation(self, bip32_derivations={}, taproot_bip32_derivations={}):
        # otherwise we need standard derivation
        for derivation in bip32_derivations.values():
            der = self.descriptor.check_derivation(derivation)
            if der is not None:
                return der
        for leafs, derivation in taproot_bip32_derivations.values():
            der = self.descriptor.check_derivation(derivation)
            if der is not None:
                return der

    def update_gaps(self, psbtv=None, known_idxs=None):
        gaps = self.gaps
        # update from psbt
        if psbtv is not None:
            for i in range(psbtv.num_inputs+psbtv.num_outputs):
                sc = psbtv.input(i) if i < psbtv.num_inputs else psbtv.output(i-psbtv.num_inputs)
                if self.owns(sc):
                    res = self.get_derivation(sc.bip32_derivations, sc.taproot_bip32_derivations)
                    if res is not None:
                        idx, branch_idx = res
                        if idx + self.GAP_LIMIT > gaps[branch_idx]:
                            gaps[branch_idx] = idx + self.GAP_LIMIT + 1
        # update from gaps arg
        if known_idxs is not None:
            for i, gap in enumerate(gaps):
                if known_idxs[i] is not None and known_idxs[i] + self.GAP_LIMIT > gap:
                    gaps[i] = known_idxs[i] + self.GAP_LIMIT
        self.unused_recv = gaps[0] - self.GAP_LIMIT
        self.gaps = gaps

    def fill_scope(self, scope, fingerprint):
        """Fills derivation paths in inputs"""
        if not self.owns(scope):
            return False
        der = self.get_derivation(scope.bip32_derivations, scope.taproot_bip32_derivations)
        if der is None:
            return False
        idx, branch_idx = der
        desc = self.descriptor.derive(idx, branch_index=branch_idx)
        # find keys with our fingerprint
        for key in desc.keys:
            if key.fingerprint == fingerprint:
                pub = key.get_public_key()
                # fill our derivations
                scope.bip32_derivations[pub] = DerivationPath(
                    fingerprint, key.derivation
                )
        # fill script
        scope.witness_script = desc.witness_script()
        scope.redeem_script = desc.redeem_script()
        return True

    @property
    def keys(self):
        return self.descriptor.keys

    @property
    def has_private_keys(self):
        return any([k.is_private for k in self.keys])

    def get_key_dicts(self, network):
        keys = [{
            "key": k,
        } for k in self.keys]
        # get XYZ-pubs
        slip132_ver = "xpub"
        canonical_ver = "xpub"
        if self.descriptor.is_pkh:
            if self.descriptor.is_wrapped:
                slip132_ver = "ypub"
            elif self.descriptor.is_segwit:
                slip132_ver = "zpub"
        elif self.descriptor.is_basic_multisig:
            if self.descriptor.is_wrapped:
                slip132_ver = "Ypub"
            elif self.descriptor.is_segwit:
                slip132_ver = "Zpub"
        for k in keys:
            k["is_private"] = k["key"].is_private
            ver = slip132_ver.replace("pub", "prv") if k["is_private"] else slip132_ver
            k["slip132"] = k["key"].to_string(self.Networks[network][ver])
            ver = canonical_ver.replace("pub", "prv") if k["is_private"] else canonical_ver
            k["canonical"] = k["key"].to_string(self.Networks[network][ver])
            k["is_nums"] = (k["key"].sec() == ec.NUMS_PUBKEY.sec()) # nothing up my sleeve
        return keys

    def sign_psbt(self, psbt, sighash=SIGHASH.ALL):
        if not self.has_private_keys:
            return
        # psbt may not have derivation for other keys
        # and in case of WIF key there is no derivation whatsoever
        for i, inp in enumerate(psbt.inputs):
            der = self.get_derivation(inp.bip32_derivations, inp.taproot_bip32_derivations)
            if der is None:
                continue
            idx, branch = der
            derived = self.descriptor.derive(idx, branch_index=branch)
            keys = [k for k in derived.keys if k.is_private]
            for k in keys:
                if k.is_private:
                    psbt.sign_with(k.private_key, sighash)

    def sign_input(self, psbtv, i, sig_stream, sighash=SIGHASH.ALL, extra_scope_data=None):
        if not self.has_private_keys:
            return 0
        inp = psbtv.input(i)
        inp.update(extra_scope_data)
        der = self.get_derivation(inp.bip32_derivations, inp.taproot_bip32_derivations)
        if der is None:
            return 0
        idx, branch = der
        derived = self.descriptor.derive(idx, branch_index=branch)
        keys = [k for k in derived.keys if k.is_private]
        count = 0
        for k in keys:
            if k.is_private:
                count += psbtv.sign_input(i, k.private_key, sig_stream, sighash, extra_scope_data=extra_scope_data)
        return count


    @classmethod
    def parse(cls, desc, path=None):
        name = "Untitled"
        if "&" in desc:
            arr = desc.split("&")
            desc = arr[-1]
            name = "&".join(arr[:-1]) # so name with & can be parsed as well
        w = cls.from_descriptor(desc, path)
        w.name = name
        return w

    @classmethod
    def from_descriptor(cls, desc:str, path):
        # remove checksum if it's there and all spaces
        desc = desc.split("#")[0].replace(" ", "")
        descriptor = cls.DescriptorClass.from_string(desc)
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
        if self.descriptor.is_taproot:
            p = "Taproot\n"
        elif self.descriptor.is_segwit:
            p = "Nested Segwit\n" if self.descriptor.is_wrapped else "Native Segwit\n"
        else:
            p = "Legacy\n"
        pp = self.descriptor.full_policy
        if not self.is_complex:
            p += pp
        else:
            prefix = "Miniscript:\n" if self.is_miniscript else "\n"
            p += prefix+pp.replace(",",", ")
        return p

    @property
    def is_miniscript(self):
        return not (self.descriptor.is_basic_multisig or self.descriptor.is_pkh or self.descriptor.is_taproot)

    @property
    def is_taptree(self):
        return bool(self.descriptor.taptree)

    @property
    def is_complex(self):
        return self.is_miniscript or self.is_taptree

    def __str__(self):
        return "%s&%s" % (self.name, self.descriptor)

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__, str(self))
