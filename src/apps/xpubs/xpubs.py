from app import BaseApp, AppError
from gui.screens import Menu, DerivationScreen
from .screens import XPubScreen

from binascii import hexlify
from bitcoin.networks import NETWORKS
from bitcoin import bip32
from io import BytesIO


class XpubApp(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = "Master public keys"
    prefixes = [
        b"fingerprint",
        b"xpub",
    ]

    def __init__(self, path):
        # we don't need to store anything
        pass

    async def menu(self, show_screen, show_all=False):
        net = NETWORKS[self.network]
        buttons = [
            (None, "Recommended"),
            ("m/84h/%dh/0h" % net["bip32"], "Single key"),
            ("m/48h/%dh/0h/2h" % net["bip32"], "Multisig"),
            (None, "Other keys"),
        ]
        if show_all:
            coin = net["bip32"]
            buttons += [
                ("m/84h/%dh/0h" % coin, "Single Native Segwit\nm/84h/%dh/0h" % coin),
                ("m/49h/%dh/0h" % coin, "Single Nested Segwit\nm/49h/%dh/0h" % coin),
                (
                    "m/48h/%dh/0h/2h" % coin,
                    "Multisig Native Segwit\nm/48h/%dh/0h/2h" % coin,
                ),
                (
                    "m/48h/%dh/0h/1h" % coin,
                    "Multisig Nested Segwit\nm/48h/%dh/0h/1h" % coin,
                ),
            ]
        else:
            buttons += [(0, "Show more keys"), (1, "Enter custom derivation")]
        # wait for menu selection
        menuitem = await show_screen(Menu(buttons, last=(255, None)))

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
            return BytesIO(xpub.to_base58().encode()), {}
        raise AppError("Unknown command")

    async def show_xpub(self, derivation, show_screen):
        derivation = derivation.rstrip("/")
        net = NETWORKS[self.network]
        xpub = self.keystore.get_xpub(derivation)
        ver = bip32.detect_version(derivation, default="xpub", network=net)
        canonical = xpub.to_base58(net["xpub"])
        slip132 = xpub.to_base58(ver)
        if slip132 == canonical:
            slip132 = None
        prefix = "[%s%s]" % (
            hexlify(self.keystore.fingerprint).decode(),
            derivation[1:],
        )
        await show_screen(XPubScreen(xpub=canonical, slip132=slip132, prefix=prefix))

    def wipe(self):
        # nothing to delete
        pass
