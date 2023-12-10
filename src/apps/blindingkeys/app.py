from app import BaseApp, AppError
from gui.screens import QRAlert, Prompt

from embit.liquid.networks import NETWORKS
from helpers import is_liquid
from io import BytesIO


class BlindingKeysApp(BaseApp):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    button = None
    BTNTEXT = "Blinding key"
    prefixes = [b"slip77"] # [b"bprv", b"bpub", b"slip77"]
    name = "blindingkeys"

    def __init__(self, path):
        pass

    def init(self, *args, **kwargs):
        super().init(*args, **kwargs)
        if is_liquid(self.network):
            self.button = self.BTNTEXT
        else:
            self.button = None

    async def menu(self, show_screen, show_all=False):
        await show_screen(QRAlert("Standard SLIP-77 blinding key",
                self.keystore.slip77_key.wif(NETWORKS[self.network]),
                note="Blinding private key allows your software wallet\nto track your balance."
                ))
        return False

    async def process_host_command(self, stream, show_screen):
        if self.keystore.is_locked:
            raise AppError("Device is locked")
        # reads prefix from the stream (until first space)
        prefix = self.get_prefix(stream)
        if prefix == b"slip77":
            if not await show_screen(Prompt("Confirm the action",
                       "Send master blinding private key\nto the host?\n\n"
                       "Host is requesting your\nSLIP-77 blinding key.\n\n"
                       "It will be able to watch your funds and unblind transactions.")):
                return False
            return BytesIO(self.keystore.slip77_key.wif(NETWORKS[self.network])), {}
        raise AppError("Unknown command")

    def wipe(self):
        # nothing to delete
        pass
