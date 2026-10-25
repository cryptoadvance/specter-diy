from .core import Host, HostError
from platform import fpath
import os
import platform
from binascii import hexlify
from helpers import a2b_base64_stream
import lvgl as lv

# Special values returned by the file picker instead of a file name.
# They can't collide with a real file, because the picker
# always returns a full path to a file on the SD card.
DELETE_FILE = "delete-file"
WIPE_SD_CARD = "wipe-sd-card"

class SDHost(Host):
    """
    SDHost class.
    Manages communication with SD card:
    - loading unsigned transaction and authentications
    - saving signed transaction to the card
    - deleting files from the card
    """

    button = "Open SD card file"
    settings_button = "SD card"

    # file types we can load from the SD card
    # (wallet descriptors are saved as .json,
    # signed transactions keep the extension of the source file)
    extensions = (".psbt", ".txt", ".json")

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
            while True:
                sd_file = await self.select_file(self.extensions)
                if sd_file is None:
                    return
                # the user picked an action instead of a file -
                # do it and show the picker again
                if sd_file == DELETE_FILE:
                    await self.delete_files()
                elif sd_file == WIPE_SD_CARD:
                    await self.wipe_sd_card()
                else:
                    break
                # nothing left to open - don't show an empty picker
                if len(self.list_files(self.extensions)) == 0:
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

    def list_files(self, extensions):
        """Returns a sorted list of files on the SD card with given extensions"""
        files = sum([
            [
                f[0] for f in os.ilistdir(self.sdpath)
                if f[0].lower().endswith(ext)
                and f[1] == 0x8000
            ] for ext in extensions
        ], [])
        files.sort()
        return files

    async def select_file(self, extensions, allow_delete=True):
        files = self.list_files(extensions)
        if len(files) == 0:
            raise HostError("\n\nNo matching files found on the SD card\nAllowed: %s" % ", ".join(extensions))
        # elif len(files) == 1:
        #     return self.sdpath+"/"+ files[0]

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

        # actions that don't open a file
        if allow_delete:
            buttons += [(None, None)]
            buttons += [(DELETE_FILE, lv.SYMBOL.TRASH + " Delete a file")]
            buttons += [(WIPE_SD_CARD, lv.SYMBOL.TRASH + " Delete ALL files")]

        fname = await self.manager.gui.menu(buttons, title="Select a file", last=(None, "Cancel"))
        return fname

    async def delete_files(self):
        """
        Lets the user delete files from the SD card one by one.
        SD card has to be mounted by the caller.
        """
        while True:
            if len(self.list_files(self.extensions)) == 0:
                await self.manager.gui.alert(
                    "Nothing to delete",
                    "\n\nThere are no files on the SD card\nthat can be deleted.",
                    button_text="Close",
                )
                return
            fname = await self.select_file(self.extensions, allow_delete=False)
            if fname is None:
                return
            short = self.truncate(fname.split("/")[-1])
            confirm = await self.manager.gui.prompt(
                "Delete file?",
                "\n\n%s\n\nThe file will be overwritten with random data "
                "and deleted from the SD card." % short,
            )
            if not confirm:
                continue
            try:
                platform.secure_delete_file(fname)
            except Exception as e:
                print(e)
                await self.manager.gui.alert(
                    "Error!",
                    "\n\nFailed to delete\n\n%s" % short,
                )
                continue
            await self.manager.gui.alert(
                "Success!",
                "\n\nFile deleted:\n\n%s" % short,
                button_text="Close",
            )

    async def wipe_sd_card(self):
        """
        Overwrites all files in the root folder of the SD card
        with random data and deletes them.
        SD card has to be mounted by the caller.
        """
        names = [
            f[0] for f in os.ilistdir(self.sdpath)
            if f[1] == 0x8000
        ]
        if len(names) == 0:
            await self.manager.gui.alert(
                "Nothing to delete",
                "\n\nThe SD card is already empty.",
                button_text="Close",
            )
            return
        confirm = await self.manager.gui.prompt(
            "Delete ALL files?",
            "\n\nAll %d files on the SD card will be overwritten "
            "with random data and deleted.\n\nThis cannot be undone!" % len(names),
        )
        if not confirm:
            return
        failed = 0
        for name in names:
            try:
                platform.secure_delete_file(self.sdpath + "/" + name)
            except Exception as e:
                print(e)
                failed += 1
        if failed > 0:
            await self.manager.gui.alert(
                "Error!",
                "\n\nFailed to delete %d of %d files." % (failed, len(names)),
            )
        else:
            await self.manager.gui.alert(
                "Success!",
                "\n\nAll %d files are deleted." % len(names),
                button_text="Close",
            )

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
