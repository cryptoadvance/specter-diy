"""
Backup app - can load secrets from a text file or qr code that starts with
bip39: <recovery phrase>
"""
from app import BaseApp, AppError
from embit import bip39
from gui.screens import Prompt
from gui.components.mnemonic import MnemonicTable
import lvgl as lv

# Should be called App if you use a single file
class App(BaseApp):
    """Allows to load mnemonic from text file / QR code"""
    name = "backup"
    prefixes = [b"bip39:"]

    async def process_host_command(self, stream, show_fn):
        # reads prefix from the stream (until first space)
        prefix = self.get_prefix(stream)
        if prefix not in self.prefixes:
            # WTF? It's not our data...
            raise AppError("Prefix is not valid: %s" % prefix.decode())
        mnemonic = stream.read().strip().decode()
        if not bip39.mnemonic_is_valid(mnemonic):
            raise AppError("Invalid mnemonic!")
        scr = Prompt("Load this mnemonic to memory?", "Mnemonic:")
        table = MnemonicTable(scr)
        table.align_to(scr.message, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        table.set_mnemonic(mnemonic)
        confirm = await show_fn(scr)
        if confirm:
            self.keystore.set_mnemonic(mnemonic)
        return confirm
