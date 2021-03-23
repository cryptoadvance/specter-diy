from .core import Host, HostError
from platform import fpath
from io import BytesIO
import os
import platform

class SDHost(Host):
    """
    SDHost class.
    Manages communication with SD card:
    - loading unsigned transaction and authentications
    - saving signed transaction to the card
    """

    button = "Sign from SD card"

    def __init__(self, path, sdpath=fpath("/sd")):
        super().__init__(path)
        self.sdpath = sdpath
        self.f = None
        self.fram = self.path + "/data"
        self.sd_file = self.sdpath + "/signed.psbt"

    def reset_and_mount(self):
        if self.f is not None:
            self.f.close()
            os.remove(self.fram)
            self.f = None
        if not platform.is_sd_present:
            raise HostError("SD card is not inserted")
        platform.mount_sdcard()

    def copy(self, fin, fout):
        b = bytearray(100)
        while True:
            l = fin.readinto(b)
            if l == 0:
                break
            fout.write(b, l)

    async def get_data(self):
        """
        Loads psbt transaction from the SD card.
        """
        self.reset_and_mount()
        try:
            sd_file = await self.select_file(".psbt")
            if sd_file is None:
                return
            self.sd_file = sd_file
            with open(self.fram, "wb") as fout:
                fout.write(b"sign ")
                with open(self.sd_file, "rb") as fin:
                    self.copy(fin, fout)
            self.f = open(self.fram,"rb")
        finally:
            platform.unmount_sdcard()
        return self.f

    def truncate(self, fname):
        if len(fname) <= 33:
            return fname
        return fname[:18]+"..."+fname[-12:]

    async def select_file(self, extension):
        buttons = [(self.sdpath+"/"+f[0], self.truncate(f[0])) for f in os.ilistdir(self.sdpath) if f[0].endswith(extension) and f[1] == 0x8000]
        if len(buttons) == 0:
            raise HostError("\n\nNo %s files found on the SD card" % extension)
        if len(buttons) == 1:
            return buttons[0][0]
        fname = await self.manager.gui.menu(buttons, title="Select a %s file" % extension, last=(None, "Cancel"))
        return fname

    async def send_data(self, stream, *args, **kwargs):
        """
        Saves transaction in base64 encoding to SD card
        as psbt.signed.<suffix> file
        Returns a success message to display
        """
        self.reset_and_mount()
        try:
            new_fname = self.sd_file.replace(".psbt", ".signed.psbt")
            with open(new_fname, "wb") as fout:
                self.copy(stream, fout)
        finally:
            platform.unmount_sdcard()
        await self.manager.gui.alert("Success!", "\n\nSigned transaction is saved to\n\n%s" % new_fname.split("/")[-1])
