from app import BaseApp, AppError
from gui.screens import Menu, DerivationScreen, NumericScreen, Alert, InputScreen, Prompt
from .screens import XPubScreen
from . import scope as xpubauth_scope
import json
from binascii import hexlify
from embit.liquid.networks import NETWORKS
from embit import bip32
from helpers import is_liquid
from io import BytesIO
import platform
from collections import OrderedDict

# A single derivation-path request ("xpub <path>") is tiny. Cap the host
# input well above any realistic path but far below anything that could
# exhaust RAM on the STM32F469, and enforce it before .decode()/parsing.
MAX_XPUB_PATH_LEN = 1024

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
    prefixes = [b"fingerprint", b"xpub", b"xpubauth"]
    name = "xpub"

    def __init__(self, path):
        self.account = 0
        # volatile scoped multi-xpub authorization (RAM only, never
        # persisted); see scope.py for the grammar and matching rules
        self._authorization = None

    def init(self, keystore, network, show_loader, communicate):
        super().init(keystore, network, show_loader, communicate)
        # a new key or network invalidates any prior authorization -
        # it belongs to a specific keystore on a specific network
        self._authorization = None

    def on_lock(self):
        self._authorization = None

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
        # non-interactive: used for device discovery/identification by
        # companion software, must not require on-device confirmation
        if prefix == b"fingerprint":
            return BytesIO(hexlify(self.keystore.fingerprint)), {}
        # get xpub,
        # data: derivation path in human-readable form like m/44h/1h/0
        elif prefix == b"xpub":
            # bound the host input before decoding - a derivation path is
            # tiny, anything larger is malformed or a memory-exhaustion
            # attempt and must be rejected before it becomes a str
            raw = stream.read(MAX_XPUB_PATH_LEN + 1)
            if len(raw) > MAX_XPUB_PATH_LEN:
                raise AppError("Path request too large")
            path_str = None
            try:
                path_str = raw.strip().decode()
                # convert to list of indexes
                path = bip32.parse_path(path_str)
            except (ValueError, IndexError):
                # narrow, not bare: decode() raises UnicodeError (a
                # ValueError subclass) on non-UTF-8 input, and
                # bip32.parse_path raises ValueError / IndexError on a
                # malformed or empty path component. Anything else is a
                # real bug and should propagate, not be masked as
                # "Invalid path".
                raise AppError('Invalid path: "%s"' % (path_str or raw))
            # a real derivation path is a handful of levels deep; anything
            # past the limit the scoped parser already enforces
            # (scope.MAX_PATH_DEPTH) is malformed or a derivation-DoS
            # attempt - reject it before doing any BIP32 work
            if len(path) > xpubauth_scope.MAX_PATH_DEPTH:
                raise AppError(
                    "Path too deep (max %d)" % xpubauth_scope.MAX_PATH_DEPTH
                )
            # normalize to the canonical string representation
            derivation = bip32.path_to_str(path)
            # Validate the request fully - network, then authorization -
            # *before* deriving anything. The xpub is never leaked on a
            # mismatch, but there's no reason to spend the derivation on a
            # request that's going to be refused either way.
            #
            # A standard-purpose path (44'/48'/49'/84'/86'/87') whose coin
            # type doesn't match the network currently active on this
            # device can never be legitimately shared from here - the same
            # rule an xpubauth scope is held to (see scope.py), now also
            # enforced for individual, non-scoped requests. Tell the local
            # user exactly what was asked for and why it's refused, and
            # send the host a machine-parseable reason (which network this
            # device is actually on) instead of silently deriving a key
            # for a network it isn't set to.
            if xpubauth_scope.standard_path_coin_type_mismatch(
                path, NETWORKS[self.network]["bip32"]
            ):
                device_net = self.network
                hint = xpubauth_scope.network_hint_for_path(path)
                switch_to = hint if hint else "the matching network"
                # UX note: from a pure usability standpoint this screen
                # would ideally carry a second "Network settings" button
                # that takes the user straight to the network picker, so
                # they don't have to hunt for it in the menu after being
                # told to switch. It's deliberately left out for now:
                # host commands run in their own asyncio task, separate
                # from the main() menu loop, and this firmware has no
                # primitive for one to drive the other's navigation. The
                # only way to show the picker from here is to stack it as
                # a popup over whatever menu happens to be active, which
                # works but is a fair bit of plumbing for one button.
                # Worth revisiting if/when cross-task navigation exists -
                # the UX win is real.
                await show_screen(
                    Alert(
                        "Host tried to get access\nto the following Xpub",
                        "Derivation:\n%s\n\n"
                        "This device is currently on %s.\n"
                        "This Xpub cannot be shared from here.\n\n"
                        "To share it, switch the device\nto %s in the settings first." % (
                            derivation, NETWORKS[device_net]["name"], switch_to,
                        ),
                        button_text="OK",
                    )
                )
                raise AppError("network mismatch: device is on %s" % device_net)
            # a previously approved scope covers this exact normalized
            # path and hasn't already been used - no extra prompt needed
            authorized = self._authorization is not None and (
                self._authorization.try_consume(self.network, path)
            )
            # derive the xpub - to hand straight back for an authorized
            # path, or to show the user exactly what would be shared
            xpub_str = self.keystore.get_xpub(derivation).to_base58(
                NETWORKS[self.network]["xpub"]
            )
            if authorized:
                if self._authorization.remaining <= 0:
                    self._authorization = None
                return BytesIO(xpub_str.encode()), {}
            fingerprint = hexlify(self.keystore.fingerprint).decode()
            confirm = await show_screen(
                Prompt(
                    "Share Xpub?",
                    "A connected host wants the\nextended public key for:\n\n%s\n\n%s" % (
                        derivation, xpub_str,
                    ),
                    note="Device fingerprint %s" % fingerprint,
                )
            )
            if not confirm:
                return False
            # send back as base58
            return BytesIO(xpub_str.encode()), {}
        # xpubauth begin <scope> / xpubauth end -
        # one confirmation for a bounded, explicit set of paths, see scope.py
        elif prefix == b"xpubauth":
            # bound the request as it is read, before .decode()/parsing,
            # so a hostile host cannot force a huge string allocation
            # ahead of the MAX_SCOPE_LEN check inside parse_scope
            raw = stream.read(xpubauth_scope.MAX_SCOPE_COMMAND_LEN + 1)
            if len(raw) > xpubauth_scope.MAX_SCOPE_COMMAND_LEN:
                raise AppError("xpubauth request too large")
            data = raw.strip().decode()
            if data == "end":
                self._authorization = None
                return True
            if data == "begin" or data.startswith("begin "):
                scope_str = data[len("begin"):].strip()
                return await self.xpubauth_begin(scope_str, show_screen)
            raise AppError("Unknown xpubauth subcommand")
        raise AppError("Unknown command")

    async def xpubauth_begin(self, scope_str, show_screen):
        # Fail closed: a fresh "begin" revokes any prior authorization
        # up front, before the new scope is even parsed or displayed.
        # Whatever happens next - parse error, cancel, or a successful
        # confirm - the old scope is already gone, so a user who cancels
        # a suspicious new request is never silently left with a stale
        # (possibly broader) permission still active.
        self._authorization = None
        try:
            entries, total = xpubauth_scope.parse_scope(
                scope_str, self.network, NETWORKS[self.network]["bip32"]
            )
        except xpubauth_scope.ScopeError as e:
            raise AppError(str(e))
        net_name = NETWORKS[self.network]["name"]
        allowed = "\n".join(entry.format() for entry in entries)
        fingerprint = hexlify(self.keystore.fingerprint).decode()
        message = (
            "Connected software requests temporary\n"
            "access to multiple public account keys.\n\n"
            "Network: %s\n\n"
            "Allowed:\n%s\n\n"
            "Up to %d extended public keys.\n\n"
            "Private keys are not shared." % (net_name, allowed, total)
        )
        confirm = await show_screen(
            Prompt(
                "Share multiple XPUBs?",
                message,
                confirm_text="Allow",
                cancel_text="Cancel",
                note="Device fingerprint %s" % fingerprint,
            )
        )
        if not confirm:
            # any prior authorization was already dropped at the top of
            # this method; nothing new is approved, so the device is now
            # left with no authorization at all
            return False
        # commit the freshly approved scope (any prior authorization was
        # already cleared above - begin never merges or falls back)
        self._authorization = xpubauth_scope.Authorization(entries, self.network)
        return True

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
            with platform.sdcard as sd:
                with sd.open(filename, "w") as f:
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
