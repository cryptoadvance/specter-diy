from app import BaseApp, AppError
from gui.screens import Menu, DerivationScreen, NumericScreen, Alert, InputScreen, Prompt
from .screens import XPubScreen
import json
from binascii import hexlify
from embit.liquid.networks import NETWORKS
from embit import bip32
from helpers import is_liquid
from io import BytesIO
import platform
from collections import OrderedDict

# --- Standard single-sig wallet types --------------------------------------
# Each script type has exactly one standard BIP purpose and account-key
# derivation. Fresh wallets are always built from that derivation - the
# account key is re-derived when the key currently on screen sits on a
# different path - so the descriptor key-origin and the signing key can never
# disagree (issue #393).
#
# Older Specter DIY firmware instead wrapped *whatever key was on screen* in
# the chosen script (issues #393, #281), so valid-but-non-standard wallets
# exist in the wild: tr(m/84'...), pkh(m/84'...), wpkh(m/48'.../2'...),
# tr(<custom>...), ... Those stay reproducible through a single generic
# "recover using the displayed key" choice, shown only when the displayed
# path differs from the standard one and guarded by a warning - never as an
# ordinary wallet type.
# value: (bip_purpose, descriptor_template, menu_label, name_prefix)
WALLET_TYPES = OrderedDict([
    ("wpkh",    (84, "wpkh(%s%s/{0,1}/*)",     "Native Segwit", "Native")),
    ("nested",  (49, "sh(wpkh(%s%s/{0,1}/*))", "Nested Segwit", "Nested")),
    ("legacy",  (44, "pkh(%s%s/{0,1}/*)",      "Legacy",        "Legacy")),
    ("taproot", (86, "tr(%s%s/{0,1}/*)",       "Taproot",       "Taproot")),
])
_PURPOSE_TO_TYPE = {v[0]: k for k, v in WALLET_TYPES.items()}

_HARDENED = 0x80000000


def _parse_path(derivation):
    """Parsed index list for a derivation string, or None if unparseable."""
    try:
        return bip32.parse_path(derivation)
    except Exception:
        return None


def _same_path(a, b):
    """True when two derivation strings denote the same BIP32 path."""
    pa = _parse_path(a)
    return pa is not None and pa == _parse_path(b)


def _account_index(derivation):
    """Best-effort account number: element [2] when the first three levels are
    hardened. Covers ``m/P'/C'/A'`` and deeper paths (e.g. BIP48
    ``m/48'/C'/A'/script'``). Returns None when there is no such element."""
    idxs = _parse_path(derivation)
    if idxs is None or len(idxs) < 3 or not all(i >= _HARDENED for i in idxs[:3]):
        return None
    return idxs[2] - _HARDENED


def _standard_wallet_type(derivation, coin):
    """The WALLET_TYPES key whose *standard* derivation the displayed path
    already matches: exactly three hardened levels, a known purpose, and this
    network's coin_type. None for non-standard / deeper / custom paths (so the
    UI never calls a wrong-coin_type or multisig key "recommended")."""
    idxs = _parse_path(derivation)
    if idxs is None or len(idxs) != 3 or not all(i >= _HARDENED for i in idxs):
        return None
    purpose, coin_type = idxs[0] - _HARDENED, idxs[1] - _HARDENED
    if coin_type != coin:
        return None
    return _PURPOSE_TO_TYPE.get(purpose)


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
                filename = await self.save_all_to_sd(file_format, self.account, show_screen)
                if filename is not None:
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

    async def save_all_to_sd(self, file_format, account, show_screen):

        fingerprint = hexlify(self.keystore.fingerprint).decode()

        extension = "txt" if file_format == self.export_specter_diy else "json"
        filename = "%s-%s-%d-all.%s" % (
            file_format, fingerprint, account, extension,
        )

        if not platform.sdcard.is_present:
            raise AppError("Please insert SD card")

        with platform.sdcard as sd:
            if sd.file_exists(filename):
                confirm = await show_screen(Prompt("Overwrite?", message="File %s already exists on the SD card. Overwrite?" % filename))
                if not confirm:
                    return
            with sd.open(filename, "w") as f:
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
            with platform.sdcard as sd:
                if sd.file_exists(filename):
                    confirm = await show_screen(Prompt("Overwrite?", message="File %s already exists on the SD card. Overwrite?" % filename))
                    if not confirm:
                        return
                with sd.open(filename, "w") as f:
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
                await self.save_all_to_sd(file_format, account, show_screen)
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
            await self.create_wallet(derivation, canonical, prefix, show_screen)
        elif res:
            filename = "%s-%s.txt" % (fingerprint, derivation[2:].replace("/", "-"))
            with platform.sdcard as sd:
                with sd.open(filename, "w") as f:
                    f.write(res)
            await show_screen(
                Alert("Saved!",
                      "Extended public key is saved to the file:\n\n%s" % filename,
                      button_text="Close")
            )

    async def create_wallet(self, derivation, xpub, prefix, show_screen):
        """Shows a wallet-creation menu and passes a descriptor to the wallets app.

        The script type the user picks fixes the derivation (see
        ``WALLET_TYPES``). When the key on screen is not already on that path,
        the user explicitly chooses between the standard wallet (account key
        re-derived from the standard path) and a warned recovery wallet built
        from the displayed key verbatim - the only way to reproduce the
        non-standard script/derivation pairs older firmware could create.
        """
        net = NETWORKS[self.network]
        coin = net["bip32"]
        recommended = _standard_wallet_type(derivation, coin)

        buttons = []
        if recommended:
            buttons.append((None, "Recommended"))
            buttons.append((recommended, WALLET_TYPES[recommended][2]))
        buttons.append((None, "Other"))
        for key in WALLET_TYPES:
            if key != recommended:
                buttons.append((key, WALLET_TYPES[key][2]))

        menuitem = await show_screen(Menu(
            buttons, last=(255, None),
            title="Select wallet type to create",
        ))
        if menuitem == 255 or menuitem is None or menuitem not in WALLET_TYPES:
            return

        purpose, template, type_name, name_prefix = WALLET_TYPES[menuitem]
        # Standard wallets follow the BIP44 layout: purpose fixed by the script
        # type, coin_type fixed by the active network, account carried over from
        # the displayed key (or the account selected in the menu).
        account = _account_index(derivation)
        std_account = account if account is not None else self.account
        std_target = "m/%dh/%dh/%dh" % (purpose, coin, std_account)

        use_displayed = False
        if not _same_path(derivation, std_target):
            # The displayed key would be discarded for a standard wallet. Make
            # the choice - and the non-standard option - explicit.
            choice = await show_screen(Menu(
                [
                    ("standard",
                     "Standard %s\n%s" % (type_name, std_target)),
                    ("recover",
                     "Recover using displayed key\n%s\nNon-standard - recovery only"
                     % derivation),
                ],
                last=(255, None),
                title="%s derivation" % type_name,
                note=("New wallets use the standard path. Recovery reproduces a "
                      "wallet made with older Specter DIY versions."),
            ))
            if choice == 255 or choice is None:
                return
            use_displayed = (choice == "recover")

        if use_displayed:
            confirm = await show_screen(Prompt(
                "Recover non-standard wallet",
                "This builds a %s wallet from the key you are viewing:\n\n"
                "%s\n\n"
                "This derivation is NOT standard. Other wallet software may "
                "not discover it from your seed automatically. Only continue "
                "if you are deliberately recovering an existing wallet."
                "\n\nContinue?" % (type_name, derivation),
                warning="Non-standard - recovery only",
            ))
            if not confirm:
                return
            # displayed key + its exact key-origin path, wrapped in the chosen
            # script - byte-for-byte what the older firmware produced.
            key_prefix, key_xpub = prefix, xpub
        elif _same_path(derivation, std_target):
            key_prefix, key_xpub = prefix, xpub
        else:
            self.show_loader(title="Deriving %s key..." % type_name)
            hdkey = self.keystore.get_xpub(std_target)
            key_xpub = hdkey.to_base58(net["xpub"])
            fingerprint = hexlify(self.keystore.fingerprint).decode()
            key_prefix = "[%s/%s]" % (fingerprint, std_target[2:])

        desc = template % (key_prefix, key_xpub)

        # get wallet names from the wallets app
        s, _ = await self.communicate(BytesIO(b"listwallets"), app="wallets")
        names = json.load(s)
        base_account = account if account is not None else std_account
        nn = "%s %d%s" % (name_prefix, base_account,
                          " recovery" if use_displayed else "")
        name_suggestion = nn
        i = 1
        # make sure we don't suggest an existing name
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
        # add blinding key on liquid
        if is_liquid(self.network):
            desc = "blinded(slip77(%s),%s)" % (self.keystore.slip77_key, desc)
        data = "addwallet %s&%s" % (name, desc)
        await self.communicate(BytesIO(data.encode()), app="wallets")


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
