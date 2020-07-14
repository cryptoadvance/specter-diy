from .core import Host, HostError
from platform import fpath
from io import BytesIO
import os

class SDHost(Host):
    """
    SDHost class.
    Manages communication with SD card:
    - loading unsigned transaction and authentications
    - saving signed transaction to the card
    """
    button = "Load from SD card"
    def __init__(self, path, sdpath=fpath("/sd")):
        super().__init__(path)
        self.sdpath = sdpath

    async def get_data(self):
        """
        Loads psbt transaction from the SD card.
        """
        raise HostError("Not implemented")

    async def send_data(self, stream, *args, **kwargs):
        """
        Saves transaction in base64 encoding to SD card
        as psbt.signed.<suffix> file
        Returns a success message to display
        """
        raise HostError("Not implemented")
