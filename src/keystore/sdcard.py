from .core import KeyStoreError
from .flash import FlashKeyStore
import platform
import os
from gui.screens import Menu, Prompt
from helpers import tagged_hash
from binascii import hexlify


class SDKeyStore(FlashKeyStore):
    """KeyStore that can store secrets in internal flash or an SD card."""

    NAME = "Internal storage"
    NOTE = """Recovery phrase can be stored ecnrypted on the external SD card. Only this device will be able to read it."""
    storage_button = "Flash & SD card storage"
    load_button = "Load key"

    @property
    def sdpath(self):
        return platform.fpath("/sd")

    def fileprefix(self, path):
        if path == self.flashpath:
            return 'reckless'
        hexid = hexlify(tagged_hash("sdid", self.secret)[:4]).decode()
        return "specterdiy%s" % hexid

    async def get_keypath(self, title="Select media", only_if_exist=True, **kwargs):
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
        return await self.show(scr)

    async def save_mnemonic(self):
        """Save a mnemonic with the same non-transactional semantics as
        FlashKeyStore, including for SD-card files.

        Replacing a file best-effort logically overwrites and deletes it before
        writing the new encrypted file. A power interruption may cause loss of
        the local copy; an independent recovery backup is required.
        """
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
        on_sd = fullpath.startswith(self.sdpath)
        if on_sd:
            platform.sdcard.mount()
        cancelled = False
        save_error = None
        try:
            if platform.file_exists(fullpath):
                scr = Prompt(
                    "\n\nFile already exists: %s\n" % filename,
                    "Would you like to overwrite this file?",
                )
                res = await self.show(scr)
                if res is False:
                    cancelled = True
                else:
                    try:
                        platform.secure_delete_file(fullpath)
                    except Exception as e:
                        print(e)
                        raise KeyStoreError(
                            "Failed to replace file '%s'" % fullpath
                        ) from e
            if not cancelled:
                try:
                    self.save_aead(
                        fullpath,
                        plaintext=self.mnemonic.encode(),
                        key=self.enc_secret,
                        strict=True,
                    )
                except Exception as e:
                    print(e)
                    raise KeyStoreError(
                        "Failed to save key '%s'" % fullpath
                    ) from e
        except Exception as e:
            save_error = e
        finally:
            if on_sd:
                try:
                    platform.sdcard.unmount()
                except Exception as e:
                    # Preserve the save/replacement error if both the file
                    # operation and card cleanup fail. A successful save
                    # must still report an unmount failure.
                    if save_error is None:
                        raise
                    print(e)
        if save_error is not None:
            raise save_error
        if cancelled:
            return
        await self.load_mnemonic(fullpath)
        return fullpath.split("/")[-1] if on_sd else filename

    @property
    def is_key_saved(self):
        flash_exists = super().is_key_saved
        if not platform.sdcard.is_present:
            return flash_exists

        error = None
        sd_exists = False
        entries = None
        try:
            platform.sdcard.mount()
            prefix = self.fileprefix(self.sdpath)
            entries = os.ilistdir(self.sdpath)
            try:
                for entry in entries:
                    if entry[0].lower().startswith(prefix):
                        sd_exists = True
                        break
            finally:
                platform._close_entries(entries)
        except Exception as e:
            error = e
        finally:
            try:
                platform.sdcard.unmount()
            except Exception as e:
                if error is None:
                    error = e
                else:
                    print(e)
        if error is not None:
            print(error)
            return flash_exists
        return sd_exists or flash_exists

    async def load_mnemonic(self, file=None):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if file is None:
            file = await self.select_file()
            if file is None:
                return False

        on_sd = file.startswith(self.sdpath)
        mounted = on_sd and platform.sdcard.is_present
        if mounted:
            platform.sdcard.mount()
        try:
            if not platform.file_exists(file):
                raise KeyStoreError("Key is not saved")
            _, data = self.load_aead(file, self.enc_secret)
        except Exception:
            if mounted:
                try:
                    platform.sdcard.unmount()
                except Exception as e:
                    print(e)
            raise
        if mounted:
            platform.sdcard.unmount()
        self.set_mnemonic(data.decode(), "")
        return True

    async def select_file(self):
        buttons = [(None, 'Internal storage')]
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
        on_sd = file.startswith(self.sdpath)
        if on_sd and platform.sdcard.is_present:
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
            if on_sd:
                try:
                    platform.sdcard.unmount()
                except Exception as e:
                    print(e)
                    if delete_error is None:
                        delete_error = KeyStoreError("Failed to unmount SD card")
                        delete_cause = e
        if delete_error is not None:
            if delete_cause is not None:
                raise delete_error from delete_cause
            raise delete_error
        return True

    async def storage_menu(self):
        return await super().storage_menu(
            title="Manage keys on SD card and internal flash"
        )
