from app import BaseApp, AppError
from gui.screens import Menu, DerivationScreen, NumericScreen, QRAlert, Prompt
from .screens import BlindingKeysScreen

from binascii import hexlify
from bitcoin.liquid.networks import NETWORKS
from helpers import is_liquid
from bitcoin import bip32
from io import BytesIO


class BlindingKeysApp(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = None
    BTNTEXT = "Blinding keys"
    prefixes = [b"bprv", b"bpub", b"slip77"]

    def __init__(self, path):
        self.account = 0
        pass

    def init(self, *args, **kwargs):
        super().init(*args, **kwargs)
        if is_liquid(self.network):
            self.button = self.BTNTEXT
        else:
            self.button = None

    async def menu(self, show_screen, show_all=False):
        net = NETWORKS[self.network]
        coin = net["bip32"]
        buttons = [
            (77, "Standard SLIP-77 key"),
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
            buttons += [(0, "Show more keys"), (2, "Change account number"), (1, "Enter custom derivation")]
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
                await self.show_blinding_key(der, show_screen)
                return True
        elif menuitem == 2:
            account = await show_screen(NumericScreen(current_val=str(self.account)))
            if account and int(account) > 0x80000000:
                    raise AppError('Account number too large')
            try:
                self.account = int(account)
            except:
                self.account = 0
            return await self.menu(show_screen)
        elif menuitem == 77:
            await show_screen(QRAlert("Standard SLIP-77 blinding key",
                    self.keystore.slip77_key.wif(NETWORKS[self.network]),
                    note="Blinding private key allow your software wallet\nto track your balance."
                    ))
        else:
            await self.show_blinding_key(menuitem, show_screen)
            return True
        return False

    async def process_host_command(self, stream, show_screen):
        if self.keystore.is_locked:
            raise AppError("Device is locked")
        # reads prefix from the stream (until first space)
        prefix = self.get_prefix(stream)
        if prefix in [b"bprv", b"bpub"]:
            # get blinding xprv,
            # data: derivation path in human-readable form like m/44h/1h/0
            try:
                path = stream.read().strip()
                # convert to list of indexes to check that it's valid
                path = bip32.parse_path(path.decode())
            except:
                raise AppError('Invalid path: "%s"' % path.decode())
            if prefix == b"bprv":
                if not await show_screen(Prompt("Confirm the action",
                           ("Send blinding private key\nto the host?\n\n"
                           "Host is requesting your\nblinding private key at path %s\n\n"
                           "It will be able to watch your funds and unblind transactions.") % bip32.path_to_str(path))):
                    return
            # get xprv
            xprv = self.keystore.get_blinding_xprv(bip32.path_to_str(path))
            if prefix == b"bprv":
                return BytesIO(xprv.to_base58(NETWORKS[self.network]["xprv"]).encode()), {}
            else:
                return BytesIO(xprv.to_public().to_base58(NETWORKS[self.network]["xpub"]).encode()), {}
        elif prefix == b"slip77":
            if not await show_screen(Prompt("Confirm the action",
                       "Send master blinding private key\nto the host?\n\n"
                       "Host is requesting your\nSLIP-77 blinding key.\n\n"
                       "It will be able to watch your funds and unblind transactions.")):
                return
            return BytesIO(self.keystore.slip77_key.wif(NETWORKS[self.network])), {}
        raise AppError("Unknown command")

    async def show_blinding_key(self, derivation, show_screen):
        self.show_loader(title="Deriving the key...")
        derivation = derivation.rstrip("/")
        net = NETWORKS[self.network]
        xprv = self.keystore.get_blinding_xprv(derivation)
        prefix = "[%s%s]" % (
            hexlify(self.keystore.fingerprint).decode(),
            derivation[1:],
        )
        await show_screen(BlindingKeysScreen(xprv=xprv.to_base58(net["xprv"]),
                                             xpub=xprv.to_public().to_base58(net["xpub"]),
                                             prefix=prefix))

    def wipe(self):
        # nothing to delete
        pass
