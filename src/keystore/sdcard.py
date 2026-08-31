from .core import KeyStoreError
from .flash import FlashKeyStore
import platform
from gui.screens import Menu, Prompt
from helpers import tagged_hash
from binascii import hexlify
import os


class SDKeyStore(FlashKeyStore):
    """
    KeyStore that can store secrets
    in internal flash or on a removable SD card.
    SD card is required to unlock the device.
    Bitcoin key is encrypted with internal MCU secret,
    so the attacker needs to get both the device and the SD card.
    When correct PIN is entered the key can be loaded
    from SD card to the RAM of the MCU.
    """

    NAME = "Internal storage"
    NOTE = """Recovery phrase can be stored ecnrypted on the external SD card. Only this device will be able to read it."""
    # Button to go to storage menu
    # Menu is implemented in async storage_menu function
    storage_button = "Flash & SD card storage"
    load_button = "Load key"

    @property
    def sdpath(self):
        return platform.fpath("/sd")

    def fileprefix(self, path):
        if path is self.flashpath:
            return 'reckless'

        hexid = hexlify(tagged_hash("sdid", self.secret)[:4]).decode()
        return "specterdiy%s" % hexid

    async def get_keypath(self, title="Select media", only_if_exist=True, **kwargs):
        # enable / disable buttons
        enable_flash = (not only_if_exist) or platform.file_exists(self.flashpath)
        enable_sd = False
        if platform.sdcard.is_present:
            with platform.sdcard:
                enable_sd = (not only_if_exist) or platform.file_exists(self.sdpath)
        buttons = [
            (None, "Make your choice"),
            (self.flashpath, "Internal flash", enable_flash),
            (self.sdpath, "SD card", enable_sd),
        ]
        scr = Menu(buttons, title=title, last=(None,), **kwargs)
        res = await self.show(scr)
        return res

    async def save_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if self.mnemonic is None:
            raise KeyStoreError("Recovery phrase is not loaded")

        path = await self.get_keypath(
            title="Where to save?", only_if_exist=False, note="Select media"
        )
        if path is None:
            return
        filename = await self.get_input(suggestion=self.mnemonic.split()[0])
        if filename is None:
            return

        fullpath = "%s/%s.%s" % (path, self.fileprefix(path), filename)

        if fullpath.startswith(self.sdpath):
            platform.sdcard.mount()

        # Recover from a save of this name that a power cut left half done,
        # before asking whether there is anything to replace. After the
        # mount, so the card's own scratch files are visible.
        self.reconcile_scratch(fullpath)

        replacing = False
        if platform.file_exists(fullpath):
            scr = Prompt(
                "\n\nFile already exists: %s\n" % filename,
                "Would you like to overwrite this file?",
            )
            res = await self.show(scr)
            if res is False:
                if fullpath.startswith(self.sdpath):
                    platform.sdcard.unmount()
                return
            replacing = True

        # See FlashKeyStore._save_key_file(): replacing a key file writes
        # and verifies the new one before the old one is destroyed.
        try:
            self._save_key_file(fullpath, replacing)
        except Exception:
            # The card must not stay mounted just because the save failed.
            if fullpath.startswith(self.sdpath):
                try:
                    platform.sdcard.unmount()
                except Exception as e:
                    print(e)
            raise
        if fullpath.startswith(self.sdpath):
            platform.sdcard.unmount()
        # check it's ok
        await self.load_mnemonic(fullpath)
        # return the full file name incl. prefix if saved to SD card, just the name if on flash
        return fullpath.split("/")[-1] if fullpath.startswith(self.sdpath) else filename

    @property
    def is_key_saved(self):
        flash_exists = super().is_key_saved

        if not platform.sdcard.is_present:
            return flash_exists

        with platform.sdcard:
            sd_files = [
                f[0] for f in os.ilistdir(self.sdpath)
                if f[0].lower().startswith(self.fileprefix(self.sdpath))
            ]
        sd_exists = (len(sd_files) > 0)
        return sd_exists or flash_exists

    async def load_mnemonic(self, file=None):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")

        if file is None:
            file = await self.select_file()
            if file is None:
                return False

        if file.startswith(self.sdpath) and platform.sdcard.is_present:
            platform.sdcard.mount()

        if not platform.file_exists(file):
            raise KeyStoreError("Key is not saved")
        _, data = self.load_aead(file, self.enc_secret)

        if file.startswith(self.sdpath) and platform.sdcard.is_present:
            platform.sdcard.unmount()
        self.set_mnemonic(data.decode(), "")
        return True

    async def select_file(self):

        buttons = []

        buttons += [(None, 'Internal storage')]
        buttons += self.load_files(self.flashpath)

        buttons += [(None, 'SD card')]
        if platform.sdcard.is_present:
            with platform.sdcard:
                buttons += self.load_files(self.sdpath)
        else:
            buttons += [(None, 'No SD card present')]

        return await self.show(Menu(buttons, title="Select a file", last=(None, "Cancel")))

    async def delete_mnemonic(self):

        file = await self.select_file()
        if file is None:
            return False
        # mount sd before check
        if platform.sdcard.is_present and file.startswith(self.sdpath):
            platform.sdcard.mount()
        delete_error = None
        delete_cause = None
        try:
            if not platform.file_exists(file):
                delete_error = KeyStoreError("File not found.")
            else:
                try:
                    platform.secure_delete_file(file)
                except Exception as e:
                    print(e)
                    delete_error = KeyStoreError(
                        "Failed to delete file '%s'" % file
                    )
                    delete_cause = e
        finally:
            # The card may have been removed while the overwrite was in
            # progress. Cleanup must still be attempted so SDCard's internal
            # mounted state is not left stale.
            if file.startswith(self.sdpath):
                try:
                    platform.sdcard.unmount()
                except Exception as e:
                    print(e)
                    # Never let secondary cleanup failure hide the primary
                    # deletion error. If deletion did succeed, report the
                    # cleanup failure instead of claiming overall success.
                    if delete_error is None:
                        delete_error = KeyStoreError(
                            "Failed to unmount SD card"
                        )
                        delete_cause = e
        if delete_error is not None:
            if delete_cause is not None:
                raise delete_error from delete_cause
            raise delete_error
        # NOTE: this return must stay OUTSIDE the finally block - a return
        # inside finally executes while an exception is propagating and
        # silently discards it, so a failed delete would still report
        # success. The unmount above belongs to the finally (it must run
        # on every path); the success return does not.
        return True

    async def storage_menu(self):
        """Manage storage, return True if new key was loaded"""
        return await super().storage_menu(title="Manage keys on SD card and internal flash")
