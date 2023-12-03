from app import BaseApp, AppError
from embit import bip85
from gui.screens import Menu, NumericScreen, QRAlert
from gui.screens.mnemonic import ExportMnemonicScreen
from binascii import hexlify

# TODO
# - load this mnemonic to device
# - save with SDCardFile
# - next/prev index buttons

class App(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = "Deterministic derivation (BIP-85)"
    name = "bip85"

    async def menu(self, show_screen):
        buttons = [
            (None, "Mnemonics"),
            (0, "12-word mnemonic"),
            (1, "18-word mnemonic"),
            (2, "24-word mnemonic"),
            (None, "Other stuff"),
            (3, "WIF key (single private key)"),
            (4, "Master private key (xprv)"),
            (5, "Raw entropy (16-64 bytes)"),
        ]

        # wait for menu selection
        menuitem = await show_screen(
            Menu(
                buttons,
                last=(255, None),
                title="What do you want to derive?",
                note="",
            )
        )

        # process the menu button:
        # back button
        if menuitem == 255:
            return False
        # get derivation index
        index = await show_screen(
            NumericScreen(title="Enter derivation index", note="Default: 0")
        )
        if index is None:
            return True # stay in the menu
        if index == "":
            index = 0
        index = int(index)
        note = "index: %d" % index

        # mnemonic menu items
        if menuitem >= 0 and menuitem <=2:
            num_words = 12+6*menuitem
            mnemonic = bip85.derive_mnemonic(
                self.keystore.root, num_words=num_words, index=index
            )
            title = "Derived %d-word mnemonic" % num_words
            action = await show_screen(
                ExportMnemonicScreen(mnemonic=mnemonic, title=title, note=note)
            )
            if action == ExportMnemonicScreen.QR:
                await show_screen(
                    QRAlert(title=title, message=mnemonic, note=note)
                )
            elif action == ExportMnemonicScreen.SD:
                raise NotImplementedError()
            return True
        # other stuff
        if menuitem == 3:
            title = "Derived private key"
            res = bip85.derive_wif(self.keystore.root, index)
        elif menuitem == 4:
            title = "Derived master private key"
            res = bip85.derive_xprv(self.keystore.root, index)
        elif menuitem == 5:
            num_bytes = await show_screen(
                NumericScreen(
                    title="Number of bytes to generate",
                    note="16 <= N <= 64. Default: 32",
                )
            )
            if num_bytes is None:
                return True
            if num_bytes == "":
                num_bytes = 32
            num_bytes = int(num_bytes)
            if num_bytes < 16 or num_bytes > 64:
                raise AppError("Only 16-64 bytes can be generated with BIP-85")
            title = "Derived %d-byte entropy" % num_bytes
            raw = bip85.derive_hex(self.keystore.root, num_bytes, index)
            res = hexlify(raw).decode()
        else:
            raise NotImplementedError("Not implemented")
        await show_screen(QRAlert(title=title, message=str(res), note=note))
        return True

