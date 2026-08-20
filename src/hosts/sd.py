from .core import Host, HostError
from platform import fpath
import os
import platform
from binascii import hexlify
from helpers import a2b_base64_stream
from keystore.flash import SD_FILE_PREFIX

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
        if not platform.sdcard.is_present:
            raise HostError("SD card is not inserted")
        platform.sdcard.mount()

    def copy(self, fin, fout):
        b = bytearray(100)
        while True:
            l = fin.readinto(b)
            if l == 0:
                break
            fout.write(b, l)

    async def get_data(self, raw=False, chunk_timeout=0.1):
        """
        Loads host command from the SD card.
        """
        self.reset_and_mount()
        try:
            sd_file = await self.select_file([".psbt", ".txt", ".json"])
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
            platform.sdcard.unmount()
        return self.f

    def truncate(self, fname):
        if len(fname) <= 33:
            return fname
        return fname[:18]+"..."+fname[-12:]

    async def warn_about_encrypted_files(self):
        """
        Recovery phrases saved via "Flash & SD card storage" are encrypted
        with the device's internal secret and don't show up in the file
        picker. If the current keystore already is SDKeyStore, those files
        are reachable from its own "Load key" menu, so there is nothing to
        warn about - only warn when they'd otherwise be invisible, e.g.
        when a smartcard is currently in use.

        This is a best-effort hint for the "Import recovery phrase" flow
        (the only place it is called from) - it manages its own short
        mount window, unmounts before showing the alert, and never
        raises: any reason the card can't be read here just means no
        hint; the actual file load in get_data() reports real errors.
        """
        keystore = self.parent.keystore if self.parent is not None else None
        if keystore is not None and hasattr(keystore, "sdpath"):
            return
        if not platform.sdcard.is_present:
            return
        found = False
        try:
            platform.sdcard.mount()
            try:
                found = any(
                    f[0].lower().startswith(SD_FILE_PREFIX) and f[1] == 0x8000
                    for f in os.ilistdir(self.sdpath)
                )
            finally:
                platform.sdcard.unmount()
        except OSError:
            # Card unreadable, not present, or the SD root directory
            # doesn't exist - no hint to show. The actual file load in
            # get_data() reports real errors; this best-effort hint must
            # never mask them. Only OSError is expected here (mount,
            # ilistdir and unmount all raise OSError subclasses); any
            # other exception indicates a bug and should propagate.
            return
        if found:
            await self.manager.gui.alert(
                "Encrypted recovery phrase found",
                "\n\nThis SD card also contains a recovery phrase encrypted "
                "by this device's \"Flash & SD card storage\" mode.\n\n"
                "It won't show up in this file list. To open it, restart "
                "the device with the smartcard removed, then use "
                "\"Load key\" from the Flash & SD card storage menu.",
            )

    async def select_file(self, extensions):
        files = sum([
            [
                f[0] for f in os.ilistdir(self.sdpath)
                if f[0].lower().endswith(ext)
                and f[1] == 0x8000
            ] for ext in extensions
        ], [])

        if len(files) == 0:
            raise HostError("\n\nNo matching files found on the SD card\nAllowed: %s" % ", ".join(extensions))
        # elif len(files) == 1:
        #     return self.sdpath+"/"+ files[0]
        
        files.sort()
        buttons = []
        for ext in extensions:
            title = [(None, ext+" files")]
            barr = [
                (self.sdpath+"/"+f, self.truncate(f))
                for f in files
                if f.lower().endswith(ext)
            ]
            if len(barr) == 0:
                buttons += [(None, "%s files - No files" % ext)]
            else:
                buttons += title + barr
        
        fname = await self.manager.gui.menu(buttons, title="Select a file", last=(None, "Cancel"))
        return fname

    def completed_filename(self, filename):
        suffix = "" if self.parent is None else ("."+hexlify(self.parent.fingerprint).decode())
        if filename.endswith(".psbt"):
            return filename.replace(".psbt", ".signed%s.psbt" % suffix)
        arr = filename.split(".")
        if len(arr) == 1:
            arr.append("completed%s" % suffix)
        else:
            arr = arr[:-1] + ["completed%s" % suffix, arr[-1]]
        return ".".join(arr)


    async def send_data(self, stream, *args, **kwargs):
        """
        Saves transaction in base64 encoding to SD card
        as psbt.signed.<suffix> file
        Returns a success message to display
        """
        new_fname = self.completed_filename(self.sd_file)
        self.reset_and_mount()
        try:
            if platform.file_exists(new_fname):
                confirm = await self.manager.gui.prompt("Overwrite?",
                    "File %s exists. Overwrite?" % new_fname.split("/")[-1]
                )
                if not confirm:
                    platform.sdcard.unmount()
                    return
            if isinstance(stream, str):
                with open(stream, "rb") as fin:
                    with open(new_fname, "wb") as fout:
                        self.copy(fin, fout)
            else:
                with open(new_fname, "wb") as fout:
                    self.copy(stream, fout)
                stream.seek(0)
        finally:
            platform.sdcard.unmount()
        show_qr = await self.manager.gui.prompt("Success!", "\n\nProcessed request is saved to\n\n%s\n\nShow as QR code?" % new_fname.split("/")[-1])
        if show_qr:
            await self._show_qr(stream, *args, **kwargs)

    @property
    def tmpfile(self):
        return self.path+"/tmp"

    async def _show_qr(self, stream, meta, *args, **kwargs):
        # if it's str - it's a file
        if isinstance(stream, str):
            with open(stream, "rb") as f:
                await self._show_qr(f, meta, *args, **kwargs)
            return
        qrfmt = 1 # always offer simple text animation for qr codes
        start = stream.read(4)
        stream.seek(-len(start), 1)
        if start in [b"cHNi", b"cHNl"]: # convert from base64 for QR encoder
            with open(self.tmpfile, "wb") as f:
                a2b_base64_stream(stream, f)
            with open(self.tmpfile, "rb") as f:
                await self._show_qr(f, meta, *args, **kwargs)
                return
        if start in [b"psbt", b"pset"]:
            # psbt has more options for QR format
            qrfmt = await self.manager.gui.menu(buttons=[
                (1, "Text"),
                (2, "Crypto-psbt"),
                (3, "Legacy BCUR"),
            ], title="What format to use?")

        title = meta.get("title", "Your data:")
        note = meta.get("note")
        msg = ""
        # if qrfmt == 0: # not psbt
        #     res = stream.read().decode()
        #     msg = meta.get("message", res)
        #     await self.manager.gui.qr_alert(title, msg, res, note=note, qr_width=480)
        EncoderCls = None
        if qrfmt == 1:
            from qrencoder import Base64QREncoder as EncoderCls
        elif qrfmt == 2: # we need binary
            from qrencoder import CryptoPSBTEncoder as EncoderCls
        elif qrfmt == 3:
            from qrencoder import LegacyBCUREncoder as EncoderCls
        if EncoderCls is not None:
            with EncoderCls(stream, tempfile=self.path+"/qrtmp") as enc:
                await self.manager.gui.qr_alert(title, msg, enc, note=note, qr_width=480)
