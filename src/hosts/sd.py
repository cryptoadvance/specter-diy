from .core import Host, HostError
from platform import fpath
from io import BytesIO
import os
import platform
from binascii import b2a_base64

class SDHost(Host):
    """
    SDHost class.
    Manages communication with SD card:
    - loading unsigned transaction and authentications
    - saving signed transaction to the card
    """

    button = "Open SD card file"
    settings_button = "SD card"

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
            sd_file = await self.select_file([".psbt", ".txt"])
            if sd_file is None:
                return
            self.sd_file = sd_file
            with open(self.fram, "wb") as fout:
                with open(self.sd_file, "rb") as fin:
                    # check sign prefix for txs
                    start = fin.read(5)
                    if self.sd_file.endswith(".psbt") and start != b"sign ":
                        fout.write(b"sign ")
                    fout.write(start)
                    self.copy(fin, fout)
            self.f = open(self.fram,"rb")
        finally:
            platform.unmount_sdcard()
        return self.f

    def truncate(self, fname):
        if len(fname) <= 33:
            return fname
        return fname[:18]+"..."+fname[-12:]

    async def select_file(self, extensions):
        files = sum([[f[0] for f in os.ilistdir(self.sdpath) if f[0].lower().endswith(ext) and f[1] == 0x8000] for ext in extensions], [])
        
        if len(files) == 0:
            raise HostError("\n\nNo matching files found on the SD card\nAllowed: %s" % ", ".join(extensions))
        elif len(files) == 1:
            return self.sdpath+"/"+ files[0]
        
        files.sort()
        buttons = []
        for ext in extensions:
            title = [(None, ext+" files")]
            barr = [(self.sdpath+"/"+f, self.truncate(f)) for f in files if f.lower().endswith(ext)]
            if len(barr) == 0:
                buttons += [(None, "%s files - No files" % ext)]
            else:
                buttons += title + barr
        
        fname = await self.manager.gui.menu(buttons, title="Select a file", last=(None, "Cancel"))
        return fname

    async def send_data(self, stream, *args, **kwargs):
        """
        Saves transaction in base64 encoding to SD card
        as psbt.signed.<suffix> file
        Returns a success message to display
        """
        # only psbt files are coming from the device right now
        if self.sd_file.endswith(".psbt"):
            new_fname = self.sd_file.replace(".psbt", ".signed.psbt")
        else:
            arr = self.sd_file.split(".")
            if len(arr) == 1:
                arr.append("completed")
            else:
                arr = arr[:-1] + ["completed", arr[-1]]
            new_fname = ".".join(arr)
        self.reset_and_mount()
        try:
            if isinstance(stream, str):
                with open(stream, "rb") as fin:
                    with open(new_fname, "wb") as fout:
                        self.copy(fin, fout)
            else:
                with open(new_fname, "wb") as fout:
                    self.copy(stream, fout)
                stream.seek(0)
        finally:
            platform.unmount_sdcard()
        show_qr = await self.manager.gui.prompt("Success!", "\n\nProcessed request is saved to\n\n%s\n\nShow as QR code?" % new_fname.split("/")[-1])
        if show_qr:
            await self._show_qr(stream, *args, **kwargs)

    async def _show_qr(self, stream, meta, *args, **kwargs):
        # if it's str - it's a file
        if isinstance(stream, str):
            with open(stream, "rb") as f:
                response = f.read()
        else:
            response = stream.read()
        try:
            res = response.decode()
        except:
            res = b2a_base64(response).decode()
        title = "Your data:"
        note = None
        if "title" in meta:
            title = meta["title"]
        if "note" in meta:
            note = meta["note"]
        msg = res
        if "message" in meta:
            msg = meta["message"]
        await self.manager.gui.qr_alert(title, msg, res, note=note, qr_width=480)

