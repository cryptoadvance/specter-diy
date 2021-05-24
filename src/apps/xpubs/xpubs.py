from app import BaseApp, AppError
from gui.screens import Menu, DerivationScreen, NumericScreen, Alert
from .screens import XPubScreen
import json
from binascii import hexlify
from bitcoin.networks import NETWORKS
from bitcoin import bip32
from io import BytesIO
import platform


class XpubApp(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    export_coldcard = "ckcc"
    export_generic_json = "json"
    export_specter_diy = "specter-diy"
    button = "Master public keys"
    prefixes = [b"fingerprint", b"xpub"]

    def __init__(self, path):
        self.account = 0
        pass

    async def menu(self, show_screen, show_all=False):
        net = NETWORKS[self.network]
        coin = net["bip32"]
        buttons = [
            (None, "Recommended"),
            ("m/84h/%dh/%dh" % (coin, self.account), "Single key"),
            ("m/48h/%dh/%dh/2h" % (coin, self.account), "Multisig"),
            (None, "Other keys"),
        ]
        if show_all:
            buttons += [
                (
                    "m/84h/%dh/%dh" % (coin, self.account),
                    "Single Native Segwit\nm/84h/%dh/%dh" % (coin, self.account)
                ),
                (
                    "m/49h/%dh/%dh" % (coin, self.account),
                    "Single Nested Segwit\nm/49h/%dh/%dh" % (coin, self.account)
                ),
                (
                    "m/48h/%dh/%dh/2h" % (coin, self.account),
                    "Multisig Native Segwit\nm/48h/%dh/%dh/2h" % (coin, self.account),
                ),
                (
                    "m/48h/%dh/%dh/1h" % (coin, self.account),
                    "Multisig Nested Segwit\nm/48h/%dh/%dh/1h" % (coin, self.account),
                ),
            ]
        else:
            buttons += [(0, "Show more keys"), (2, "Change account number"), (1, "Enter custom derivation"),
                        (3, "Export all keys")]
        # wait for menu selection
        menuitem = await show_screen(Menu(buttons, last=(255, None),
                                          title="Select the key",
                                          note="Current account number: %d" % self.account))

        # process the menu button:
        # back button
        if menuitem == 255:
            return False
        elif menuitem == 0:
            return await self.menu(show_screen, show_all=True)
        elif menuitem == 1:
            der = await show_screen(DerivationScreen())
            if der is not None:
                await self.show_xpub(der, show_screen)
                return True
        elif menuitem == 3:
            format = await self.save_menu(show_screen)
            if format is not False:

                fingerprint = hexlify(self.keystore.fingerprint).decode()
                extension = "json"
                coin = net["bip32"]

                derivations = [
                    ('bip49', "p2wpkh", "m/49'/%d'/%d'" % (coin, self.account)),
                    ('bip84', "p2sh-p2wpkh", "m/84'/%d'/%d'" % (coin, self.account)),
                    ('bip44', "p2pkh", "m/44'/%d'/%d'" % (coin, self.account)),
                    ('bip48_2', "p2wsh", "m/48'/%d'/%d'/2'" % (coin, self.account)),
                    ('bip48_1', "p2sh-p2wsh", "m/48'/%d'/%d'/1'" % (coin, self.account)),
                ]

                if format == self.export_specter_diy:
                    filedata = ""
                    for der in derivations:
                        xpub = self.keystore.get_xpub(der[2])
                        filedata += "[%s/%s]%s\n" % (fingerprint, der[2][2:].replace("'","h"), xpub.to_base58(net["xpub"]))
                    extension = "txt"
                else:
                    m = self.keystore.get_xpub("m")
                    data = {
                        "xpub": m.to_base58(NETWORKS[self.network]["xpub"]),
                        "xfp": fingerprint,
                        "account": self.account,
                        "chain": "BTC" if self.network == "main" else "XTN"
                    }

                    for der in derivations:
                        xpub = self.keystore.get_xpub(der[2])

                        data[der[0]] = {
                            "name": der[1],
                            "deriv": der[2],
                            "xpub": xpub.to_base58(net["xpub"]),
                            "_pub": xpub.to_base58(bip32.detect_version(der[2], default="xpub", network=net))
                        }

                    filedata = json.dumps(data).encode()

                filename = "%s-%s-%d-all.%s" % (format, fingerprint, self.account, extension)

                self.write_file(filename, filedata)
                await show_screen(
                    Alert("Saved!",
                          "Public keys are saved to the file:\n\n%s" % filename,
                          button_text="Close")
                )

        elif menuitem == 2:
            account = await show_screen(NumericScreen(current_val=str(self.account)))
            if account and int(account) > 0x80000000:
                raise AppError('Account number too large')
            try:
                self.account = int(account)
            except:
                self.account = 0
            return await self.menu(show_screen)
        else:
            await self.show_xpub(menuitem, show_screen)
            return True
        return False

    async def process_host_command(self, stream, show_screen):
        if self.keystore.is_locked:
            raise AppError("Device is locked")
        # reads prefix from the stream (until first space)
        prefix = self.get_prefix(stream)
        # get device fingerprint, data is ignored
        if prefix == b"fingerprint":
            return BytesIO(hexlify(self.keystore.fingerprint)), {}
        # get xpub,
        # data: derivation path in human-readable form like m/44h/1h/0
        elif prefix == b"xpub":
            try:
                path = stream.read().strip()
                # convert to list of indexes
                path = bip32.parse_path(path.decode())
            except:
                raise AppError('Invalid path: "%s"' % path.decode())
            # get xpub
            xpub = self.keystore.get_xpub(bip32.path_to_str(path))
            # send back as base58
            return BytesIO(xpub.to_base58(NETWORKS[self.network]["xpub"]).encode()), {}
        raise AppError("Unknown command")

    async def show_xpub(self, derivation, show_screen):
        self.show_loader(title="Deriving the key...")
        derivation = derivation.rstrip("/")
        net = NETWORKS[self.network]
        xpub = self.keystore.get_xpub(derivation)
        ver = bip32.detect_version(derivation, default="xpub", network=net)
        canonical = xpub.to_base58(net["xpub"])
        slip132 = xpub.to_base58(ver)
        if slip132 == canonical:
            slip132 = None
        fingerprint = hexlify(self.keystore.fingerprint).decode()
        prefix = "[%s%s]" % (
            fingerprint,
            derivation[1:],
        )
        res = await show_screen(XPubScreen(xpub=canonical, slip132=slip132, prefix=prefix))
        if res:
            filename = "%s-%s.txt" % (fingerprint, derivation[2:].replace("/", "-"))
            self.write_file(filename, res)
            await show_screen(
                Alert("Saved!",
                      "Extended public key is saved to the file:\n\n%s" % filename,
                      button_text="Close")
            )

    def write_file(self, filename, filedata):
        if not platform.is_sd_present():
            raise AppError("SD card is not present")
        platform.mount_sdcard()
        with open(platform.fpath("/sd/%s" % filename), "w") as f:
            f.write(filedata)
        platform.unmount_sdcard()

    async def save_menu(self, show_screen):
        buttons = [(0, "Specter-DIY (plaintext)"), (1, "Cold Card (json)")]
        # wait for menu selection
        menuitem = await show_screen(Menu(buttons, last=(255, None),
                                          title="Select a format"))

        # process the menu button:
        # back button
        if menuitem == 255:
            return False
        elif menuitem == 0:
            return self.export_specter_diy
        elif menuitem == 1:
            return self.export_coldcard
        return False

    def wipe(self):
        # nothing to delete
        pass
