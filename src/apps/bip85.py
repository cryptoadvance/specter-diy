import lvgl as lv
from binascii import hexlify
from io import BytesIO

from app import BaseApp, AppError
from embit import bip85
from gui.common import add_button, add_button_pair, align_button_pair
from gui.decorators import on_release
from gui.screens import Menu, NumericScreen, QRAlert, Alert
from gui.screens.mnemonic import MnemonicScreen
from helpers import SDCardFile

class QRWithSD(QRAlert):
    SAVE = 1
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # add save button
        btn = add_button("Save to SD card", on_release(self.save), scr=self)
        btn.align(self.close_button, lv.ALIGN.OUT_TOP_MID, 0, -20)

    def save(self):
        self.set_value(self.SAVE)

class Bip85MnemonicScreen(MnemonicScreen):
    QR = 1
    SD = 2
    LOAD = 3
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_btn = add_button(
            text="Use now (load to device)",
            scr=self,
            callback=on_release(self.load)
        )
        self.load_btn.align(self.table, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        self.show_qr_btn, self.save_sd_btn = add_button_pair(
            text1="Show QR code",
            callback1=on_release(self.show_qr),
            text2="Save to SD card",
            callback2=on_release(self.save_sd),
            scr=self,
        )
        self.show_qr_btn.align(self.load_btn, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        self.save_sd_btn.align(self.load_btn, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        align_button_pair(self.show_qr_btn, self.save_sd_btn)

    def show_qr(self):
        self.set_value(self.QR)

    def save_sd(self):
        self.set_value(self.SD)

    def load(self):
        self.set_value(self.LOAD)

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

        fgp = hexlify(self.keystore.fingerprint).decode()
        # mnemonic menu items
        if menuitem >= 0 and menuitem <=2:
            num_words = 12+6*menuitem
            mnemonic = bip85.derive_mnemonic(
                self.keystore.root, num_words=num_words, index=index
            )
            title = "Derived %d-word mnemonic" % num_words
            action = await show_screen(
                Bip85MnemonicScreen(mnemonic=mnemonic, title=title, note=note)
            )
            if action == Bip85MnemonicScreen.QR:
                await show_screen(
                    QRAlert(title=title, message=mnemonic, note=note)
                )
            elif action == Bip85MnemonicScreen.SD:
                fname = "bip85-%s-mnemonic-%d-%d.txt" % (
                    fgp, num_words, index
                )
                with SDCardFile(fname, "w") as f:
                    f.write(mnemonic)
                await show_screen(
                    Alert(
                        title="Success",
                        message="Mnemonic is saved as\n\n%s" % fname,
                        button_text="Close",
                    )
                )
            elif action == Bip85MnemonicScreen.LOAD:
                await self.communicate(
                    BytesIO(b"set_mnemonic "+mnemonic.encode()), app="",
                )
                return False
            return True
        # other stuff
        if menuitem == 3:
            title = "Derived private key"
            res = bip85.derive_wif(self.keystore.root, index)
            file_suffix = "wif"
        elif menuitem == 4:
            title = "Derived master private key"
            res = bip85.derive_xprv(self.keystore.root, index)
            file_suffix = "xprv"
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
            file_suffix = "hex-%d" % num_bytes
        else:
            raise NotImplementedError("Not implemented")
        res = str(res)
        action = await show_screen(
            QRWithSD(title=title, message=res, note=note)
        )
        if action == QRWithSD.SAVE:
            fname = "bip85-%s-%s-%d.txt" % (fgp, file_suffix, index)
            with SDCardFile(fname, "w") as f:
                f.write(res)
            await show_screen(
                Alert(
                    title="Success",
                    message="Data is saved as\n\n%s" % fname,
                    button_text="Close",
                )
            )
        return True

