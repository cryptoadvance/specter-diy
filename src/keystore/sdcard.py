from .core import KeyStoreError, PinError
from .flash import FlashKeyStore
import platform
from rng import get_random_bytes
from embit import bip39
from gui.screens import Alert, Progress, Menu, MnemonicScreen, Prompt
import asyncio
from io import BytesIO
from helpers import tagged_hash
from binascii import hexlify
import os
from hashlib import sha256


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
        if platform.is_sd_present():
            platform.mount_sdcard()
            enable_sd = (not only_if_exist) or platform.file_exists(self.sdpath)
            platform.unmount_sdcard()
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
            if not platform.is_sd_present():
                raise KeyStoreError("SD card is not present")
            platform.mount_sdcard()

        if platform.file_exists(fullpath):
            scr = Prompt(
                "\n\nFile already exists: %s\n" % filename,
                "Would you like to overwrite this file?",
            )
            res = await self.show(scr)
            if res is False:
                if fullpath.startswith(self.sdpath):
                    platform.unmount_sdcard()
                return

        self.save_aead(fullpath, plaintext=self.mnemonic.encode(),
                       key=self.enc_secret)
        if fullpath.startswith(self.sdpath):
            platform.unmount_sdcard()
        # check it's ok
        await self.load_mnemonic(fullpath)
        # return the full file name incl. prefix if saved to SD card, just the name if on flash
        return fullpath.split("/")[-1] if fullpath.startswith(self.sdpath) else filename

    @property
    def is_key_saved(self):
        flash_exists = super().is_key_saved

        if not platform.is_sd_present():
            return flash_exists

        platform.mount_sdcard()
        sd_files = [
            f[0] for f in os.ilistdir(self.sdpath)
            if f[0].lower().startswith(self.fileprefix(self.sdpath))
        ]
        sd_exists = (len(sd_files) > 0)
        platform.unmount_sdcard()
        return sd_exists or flash_exists

    async def load_mnemonic(self, file=None):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")

        if file is None:
            file = await self.select_file()
            if file is None:
                return False

        if file.startswith(self.sdpath) and platform.is_sd_present():
            platform.mount_sdcard()

        if not platform.file_exists(file):
            raise KeyStoreError("Key is not saved")
        _, data = self.load_aead(file, self.enc_secret)

        if file.startswith(self.sdpath) and platform.is_sd_present():
            platform.unmount_sdcard()
        self.set_mnemonic(data.decode(), "")
        return True

    async def select_file(self):

        buttons = []

        buttons += [(None, 'Internal storage')]
        buttons += self.load_files(self.flashpath)

        buttons += [(None, 'SD card')]
        if platform.is_sd_present():
            platform.mount_sdcard()
            buttons += self.load_files(self.sdpath)
            platform.unmount_sdcard()
        else:
            buttons += [(None, 'No SD card present')]

        return await self.show(Menu(buttons, title="Select a file", last=(None, "Cancel")))

    async def delete_mnemonic(self):

        file = await self.select_file()
        if file is None:
            return False
        # mount sd before check
        if platform.is_sd_present() and file.startswith(self.sdpath):
            platform.mount_sdcard()
        if not platform.file_exists(file):
            raise KeyStoreError("File not found.")
        try:
            os.remove(file)
        except Exception as e:
            print(e)
            raise KeyStoreError("Failed to delete file '%s'" % file)
        finally:
            if platform.is_sd_present() and file.startswith(self.sdpath):
                platform.unmount_sdcard()
            return True

    async def storage_menu(self):
        """Manage storage, return True if new key was loaded"""
        return await super().storage_menu(title="Manage keys on SD card and internal flash")
