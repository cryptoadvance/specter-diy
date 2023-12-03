from app import BaseApp, AppError
from gui.screens import Menu, DerivationScreen, NumericScreen, Alert, InputScreen
from .screens import XPubScreen
import json
from binascii import hexlify
from embit.liquid.networks import NETWORKS
from embit import bip32
from helpers import is_liquid, SDCardFile
from io import BytesIO
import platform
from collections import OrderedDict

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
    name = "xpub"

    def __init__(self, path):
        self.account = 0
        pass

    async def menu(self, show_screen, show_all=False):
        net = NETWORKS[self.network]
        coin = net["bip32"]
        if not show_all:
            buttons = [
                (None, "Recommended"),
                ("m/84h/%dh/%dh" % (coin, self.account), "Single key"),
                ("m/48h/%dh/%dh/2h" % (coin, self.account), "Multisig"),
                (None, "Other keys"),
                (0, "Show more keys"),
                (2, "Change account number"),
                (1, "Enter custom derivation"),
                (3, "Export all keys for this account"),
                (4, "Export multiple accounts"),
            ]
        else:
            buttons = [
                (None, "Recommended"),
                (
                    "m/84h/%dh/%dh" % (coin, self.account),
                    "Single Native Segwit\nm/84h/%dh/%dh" % (coin, self.account)
                ),
                (
                    "m/48h/%dh/%dh/2h" % (coin, self.account),
                    "Multisig Native Segwit\nm/48h/%dh/%dh/2h" % (coin, self.account),
                ),
                (None, "Other keys"),
                (
                    "m/86h/%dh/%dh" % (coin, self.account),
                    "Single Taproot\nm/86h/%dh/%dh" % (coin, self.account)
                ),
                (
                    "m/49h/%dh/%dh" % (coin, self.account),
                    "Single Nested Segwit\nm/49h/%dh/%dh" % (coin, self.account)
                ),
                (
                    "m/48h/%dh/%dh/1h" % (coin, self.account),
                    "Multisig Nested Segwit\nm/48h/%dh/%dh/1h" % (coin, self.account),
                ),
            ]
        # wait for menu selection
        menuitem = await show_screen(
            Menu(
                buttons,
                title="Select the key",
                note="Current account number: %d" % self.account,
                last=(255, None),
            )
        )

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
        elif menuitem == 2:
            account = await show_screen(NumericScreen(current_val=str(self.account)))
            if account and int(account) >= 0x80000000:
                raise AppError("Account number too large")
            try:
                self.account = int(account)
            except:
                self.account = 0
            return await self.menu(show_screen)
        elif menuitem == 3:
            file_format = await self.save_menu(show_screen)
            if file_format:
                filename = self.save_all_to_sd(file_format)
                await show_screen(
                    Alert("Saved!",
                          "Public keys are saved to the file:\n\n%s" % filename,
                          button_text="Close")
                )
        elif menuitem == 4:
            from_account = await show_screen(
                NumericScreen(
                    title="Enter START account number",
                    current_val=str(self.account)
                )
            )
            to_account = await show_screen(
                NumericScreen(
                    title="Enter END account number",
                    current_val=str(self.account)
                )
            )
            if from_account is None or to_account is None:
                return
            if from_account == "":
                from_account = self.account
            if to_account == "":
                to_account = self.account
            from_account = int(from_account)
            to_account = int(to_account)
            file_format = await self.save_menu(show_screen)
            await self.export_multiple_accounts_xpubs(
                from_account, to_account, file_format, show_screen
            )
        else:
            await self.show_xpub(menuitem, show_screen)
            return True
        return False

    def save_all_to_sd(self, file_format, account=None):
        if account is None:
            account = self.account

        fingerprint = hexlify(self.keystore.fingerprint).decode()

        extension = "txt" if file_format == self.export_specter_diy else "json"
        filename = "%s-%s-%d-all.%s" % (
            file_format, fingerprint, account, extension,
        )

        if not platform.is_sd_present():
            raise AppError("Please insert SD card")

        with SDCardFile(filename, "w") as f:
            self._dump_account(f, file_format, account)

        return filename

    async def export_multiple_accounts_xpubs(
        self,
        from_account,
        to_account,
        file_format,
        show_screen,
    ):
        if from_account > to_account:
            from_account, to_account = to_account, from_account
        if to_account >= 0x80000000:
            raise AppError('Account number too large')
        fingerprint = hexlify(self.keystore.fingerprint).decode()
        if file_format == self.export_specter_diy:
            # in our format we can dump any number of accounts in one file
            filename = "%s-%s-%d-%d.txt" % (
                file_format, fingerprint, from_account, to_account
            )
            with SDCardFile(filename, "w") as f:
                for account in range(from_account, to_account+1):
                    self.show_loader(title="Exporting account %d..." % account)
                    self._dump_account(f, file_format, account)
            await show_screen(
                Alert(
                    "Success!",
                    "File was successfully saved under:\n\n%s" % filename,
                    button_text="OK",
                )
            )
        else: # cc format - one file per account
            for account in range(from_account, to_account+1):
                self.show_loader(title="Exporting account %d..." % account)
                self.save_all_to_sd(file_format, account)
            await show_screen(
                Alert(
                    "Success!",
                    "All accounts are saved to corresponding files.",
                    button_text="OK",
                )
            )

    def _dump_account(self, f, file_format, account):
        """dump all keys of one account to a file"""
        coin = NETWORKS[self.network]["bip32"]
        derivations = [
            ('bip84', "p2wpkh", "m/84'/%d'/%d'" % (coin, account)),
            ('bip86', "p2tr", "m/86'/%d'/%d'" % (coin, account)),
            ('bip49', "p2sh-p2wpkh", "m/49'/%d'/%d'" % (coin, account)),
            ('bip44', "p2pkh", "m/44'/%d'/%d'" % (coin, account)),
            ('bip48_1', "p2sh-p2wsh", "m/48'/%d'/%d'/1'" % (coin, account)),
            ('bip48_2', "p2wsh", "m/48'/%d'/%d'/2'" % (coin, account)),
        ]
        fingerprint = hexlify(self.keystore.fingerprint).decode()

        if file_format == self.export_specter_diy:
            for keytype, scripttype, der in derivations:
                xpub = self.keystore.get_xpub(der)
                f.write("[%s/%s]%s\n" % (
                    fingerprint,
                    der.replace("m/", "").replace("'","h"),
                    xpub.to_base58(NETWORKS[self.network]["xpub"]),
                ))
        else:
            # coldcard generic json format
            m = self.keystore.get_xpub("m")
            data = {
                "xpub": m.to_base58(NETWORKS[self.network]["xpub"]),
                "xfp": fingerprint,
                "account": account,
                "chain": "BTC" if self.network == "main" else "XTN"
            }

            for keytype, scripttype, der in derivations:
                xpub = self.keystore.get_xpub(der)

                data[keytype] = {
                    "name": scripttype,
                    "deriv": der,
                    "xpub": xpub.to_base58(NETWORKS[self.network]["xpub"]),
                    "_pub": xpub.to_base58(
                        bip32.detect_version(
                            der,
                            default="xpub",
                            network=NETWORKS[self.network]
                        )
                    )
                }

            json.dump(data, f)

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
        res = await show_screen(
            XPubScreen(xpub=canonical, slip132=slip132, prefix=prefix)
        )
        if res == XPubScreen.CREATE_WALLET:
            await self.create_wallet(derivation, canonical, prefix, ver, show_screen)
        elif res:
            filename = "%s-%s.txt" % (fingerprint, derivation[2:].replace("/", "-"))
            with SDCardFile(filename, "w") as f:
                f.write(res)
            await show_screen(
                Alert("Saved!",
                      "Extended public key is saved to the file:\n\n%s" % filename,
                      button_text="Close")
            )

    async def create_wallet(self, derivation, xpub, prefix, version, show_screen):
        """Shows a wallet creation menu and passes descriptor to the wallets app"""
        net = NETWORKS[self.network]
        descriptors = OrderedDict({
            "zpub": ("wpkh(%s%s/{0,1}/*)" % (prefix, xpub), "Native Segwit"),
            "ypub": ("sh(wpkh(%s%s/{0,1}/*))" % (prefix, xpub), "Nested Segwit"),
            "legacy": ("pkh(%s%s/{0,1}/*)" % (prefix, xpub), "Legacy"),
            "taproot": ("tr(%s%s/{0,1}/*)" % (prefix, xpub), "Taproot"),
            # multisig is not supported yet - requires cosigners app
        })

        if version == net["ypub"]:
            buttons = [
                (None, "Recommended"),
                descriptors.pop("ypub"),
                (None, "Other"),
            ]
        elif version == net["zpub"]:
            buttons = [
                (None, "Recommended"),
                descriptors.pop("zpub"),
                (None, "Other"),
            ]
        elif "/86h/" in derivation:
            buttons = [
                (None, "Recommended"),
                descriptors.pop("taproot"),
                (None, "Other"),
            ]
        elif "/44h/" in derivation:
            buttons = [
                (None, "Recommended"),
                descriptors.pop("legacy"),
                (None, "Other"),
            ]
        else:
            buttons = []
        buttons += [descriptors[k] for k in descriptors]
        menuitem = await show_screen(Menu(buttons, last=(255, None),
                                     title="Select wallet type to create"))
        if menuitem == 255:
            return
        else:
            # get wallet names from the wallets app
            s, _ = await self.communicate(BytesIO(b"listwallets"), app="wallets")
            names = json.load(s)
            if menuitem.startswith("pkh("):
                name_suggestion = "Legacy %d" % self.account
            elif menuitem.startswith("wpkh("):
                name_suggestion = "Native %d" % self.account
            elif menuitem.startswith("sh(wpkh("):
                name_suggestion = "Nested %d" % self.account
            elif menuitem.startswith("tr("):
                name_suggestion = "Taproot %d" % self.account
            else:
                name_suggestion = "Wallet %d" % self.account
            nn = name_suggestion
            i = 1
            # make sure we don't suggest existing name
            while name_suggestion in names:
                name_suggestion = "%s (%d)" % (nn, i)
                i += 1
            name = await show_screen(InputScreen(title="Name your wallet",
                    note="",
                    suggestion=name_suggestion,
                    min_length=1, strip=True
            ))
            if not name:
                return
            # send the wallets app addwallet command with descriptor
            desc = menuitem
            # add blinding key on liquid
            if is_liquid(self.network):
                desc = "blinded(slip77(%s),%s)" % (self.keystore.slip77_key, desc)
            data = "addwallet %s&%s" % (name, desc)
            stream = BytesIO(data.encode())
            await self.communicate(stream, app="wallets")


    async def save_menu(self, show_screen):
        buttons = [(0, "Specter-DIY (plaintext)"), (1, "Cold Card (json)")]
        # wait for menu selection
        menuitem = await show_screen(Menu(buttons, last=(255, None),
                                          title="Select a format"))

        # process the menu button:
        # back button
        if menuitem == 255:
            return None
        elif menuitem == 0:
            return self.export_specter_diy
        elif menuitem == 1:
            return self.export_coldcard
        return None


    def wipe(self):
        # nothing to delete
        pass
