from .core import Host, HostError
from platform import fpath
import os
import platform
from binascii import hexlify
from helpers import a2b_base64_stream
from gui.screens import Progress

# Menu values for the actions in the file picker. Strings rather than small
# integers so they can never collide with a file path, which is what every
# other button in that menu returns.
DELETE_ACTION = "__delete__"
FORMAT_ACTION = "__format__"
# The same red the rest of the GUI uses for destructive buttons.
DANGER_COLOR = 0x951E2D

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
            # self.fram is the copy of the previous transaction pulled off
            # the card into the SDRAM ramdisk - overwrite it, don't just
            # unlink it.
            platform.secure_delete_file(self.fram)
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

    def list_files(self, extensions):
        """Names (not paths) of the files on the card this host accepts."""
        files = sum([
            [
                f[0] for f in os.ilistdir(self.sdpath)
                if f[0].lower().endswith(ext)
                and f[1] == 0x8000
            ] for ext in extensions
        ], [])
        files.sort()
        return files

    def file_buttons(self, files, extensions):
        """The grouped-by-extension part of the file picker."""
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
        return buttons

    async def select_file(self, extensions):
        """
        Lets the user open a file, or manage the card. Card management is
        offered even when no file matches `extensions`: a card full of
        other files must still be deletable/formattable from the device.
        Returns the chosen file path, or None on cancel / after the last
        matching file was deleted.
        """
        while True:
            files = self.list_files(extensions)
            buttons = self.file_buttons(files, extensions)
            # Its own section, after a blank line and under a heading of
            # its own. Appended straight after the last extension group it
            # would read as one more entry of that group - exactly the
            # wrong thing for destructive actions to look like.
            buttons += [
                (None, None),
                (None, "Manage the card"),
                (DELETE_ACTION, "Delete files"),
            ]

            fname = await self.manager.gui.menu(buttons, title="Select a file", last=(None, "Cancel"))
            if fname != DELETE_ACTION:
                return fname
            if await self.delete_menu(files):
                # The card was formatted: it is empty and unmounted now, so
                # there is nothing left to pick and nothing left to list.
                return None
            if len(self.list_files(extensions)) == 0:
                # The user deleted the last usable file. That is not an
                # error - they did it on purpose - so leave quietly instead
                # of raising "no matching files" at them.
                return None

    async def delete_menu(self, files):
        """
        Offers deleting a single file, or erasing the whole card. Deleting
        single files only reaches the files this host can see; formatting
        clears everything - hence the confirmations on format_card().

        Returns True if the card was formatted, in which case the caller
        must not touch the filesystem again: erase_and_format() leaves the
        card unmounted and powered down.
        """
        buttons = [(None, "Delete a single file")]
        buttons += [(self.sdpath+"/"+f, self.truncate(f)) for f in files]
        buttons += [
            (None, None),
            (None, "Delete everything"),
            (FORMAT_ACTION, "Format entire SD card", True, DANGER_COLOR),
        ]
        choice = await self.manager.gui.menu(
            buttons, title="Delete from SD card", last=(None, "Cancel")
        )
        if choice is None:
            return False
        if choice == FORMAT_ACTION:
            return await self.format_card()
        await self.delete_file(choice)
        return False

    async def delete_file(self, path):
        """Best-effort logically overwrites and deletes one file."""
        shortname = path.split("/")[-1]
        confirm = await self.manager.gui.prompt(
            "Delete this file?",
            "\n\n%s\n\nSpecter-DIY attempts a best-effort logical "
            "overwrite before removing the file. Physical copies may remain "
            "and cannot be ruled out.\n\nThis cannot be undone. "
            "Continue?" % self.truncate(shortname)
        )
        if not confirm:
            return False
        try:
            platform.secure_delete_file(path)
        except Exception as e:
            print(e)
            raise HostError("Failed to delete file '%s':\n\n%s" % (shortname, e))
        await self.manager.gui.alert(
            "Deleted", "\n\n%s has been deleted." % self.truncate(shortname)
        )
        return True

    async def format_card(self):
        """
        Overwrites every block on the card and creates a fresh, empty
        filesystem. Returns True if that happened.

        Deleting single files only reaches the files this host can see.
        Formatting is what actually clears the card - including everything
        else on it, which is why it sits behind two confirmations.
        """
        if not await self.manager.gui.prompt(
            "Format the SD card?",
            "\n\nThis erases EVERYTHING on the card - not only the files "
            "Specter-DIY can see, all of it - and cannot be undone.\n\n"
            "Every block is best-effort overwritten before the card is "
            "reformatted. Physical copies may remain, and the current "
            "MicroPython runtime cannot guarantee that every physical I/O "
            "failure is reported.\n\n"
            "One honest limit: SD cards manage their own wear levelling, so "
            "a small amount of old data can in theory survive in space the "
            "card's controller never exposes. No software can rule that out "
            "on any SD card - only destroying it physically can.\n\n"
            "This runs block by block with a progress bar. On a large card, "
            "or if the device is low on free memory and has to fall back to "
            "small blocks, it can take many minutes - that is normal. Do "
            "NOT remove the card or power the device off until it "
            "finishes.\n\nAre you sure?"
        ):
            return False
        if not await self.manager.gui.prompt(
            "Last chance",
            "\n\nEverything on this card will be erased.\n\nFormat it now?"
        ):
            return False

        scr = Progress(
            "Formatting SD card",
            "Overwriting every block, then reformatting.\n"
            "This can take several minutes - please wait.\n"
            "Do NOT remove the card or power the device off.",
            button_text=None,
        )
        await self.manager.gui.load_screen(scr)

        async def update_progress(fraction):
            scr.set_progress(fraction)
            scr.tick(5)

        try:
            await platform.sdcard.erase_and_format(progress_cb=update_progress)
        except Exception as e:
            print(e)
            raise HostError("%s" % e)
        await self.manager.gui.alert(
            "Success!", "\n\nThe SD card has been erased and reformatted."
        )
        return True

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
