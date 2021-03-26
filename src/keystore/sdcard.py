from .core import KeyStoreError, PinError
from .flash import FlashKeyStore
import platform
from rng import get_random_bytes
from bitcoin import bip39
from gui.screens import Alert, Progress, Menu, MnemonicScreen
import asyncio
from io import BytesIO
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
        hexid = hexlify(tagged_hash("sdid", self.secret)[:4]).decode()
        return platform.fpath("/sd/specterdiy%s" % hexid)

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

    async def save_mnemonic(self, path=None):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if self.mnemonic is None:
            raise KeyStoreError("Recovery phrase is not loaded")
        if path is None:
            path = await self.get_keypath(
                title="Where to save?", only_if_exist=False, note="Select media"
            )
            if path is None:
                return False
        if path == self.sdpath:
            if not platform.is_sd_present():
                raise KeyStoreError("SD card is not present")
            platform.mount_sdcard()
        self.save_aead(path, plaintext=self.mnemonic.encode(), key=self.enc_secret)
        if path == self.sdpath:
            platform.unmount_sdcard()
        # check it's ok
        await self.load_mnemonic(path)
        return True

    @property
    def is_key_saved(self):
        flash_exists = platform.file_exists(self.flashpath)
        if not platform.is_sd_present():
            return flash_exists
        platform.mount_sdcard()
        sd_exists = platform.file_exists(self.sdpath)
        platform.unmount_sdcard()
        return sd_exists or flash_exists

    async def load_mnemonic(self, path=None):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if path is None:
            path = await self.get_keypath(
                title="From where to load?", note="Select media"
            )
            if path is None:
                return False
        if path == self.sdpath:
            if not platform.is_sd_present():
                raise KeyStoreError("SD card is not present")
            platform.mount_sdcard()

        if not platform.file_exists(path):
            raise KeyStoreError("Key is not saved")
        _, data = self.load_aead(path, self.enc_secret)

        if path == self.sdpath:
            platform.unmount_sdcard()
        self.set_mnemonic(data.decode(), "")
        return True

    async def delete_mnemonic(self, path=None):
        if path is None:
            path = await self.get_keypath(title="From where to delete?")
            if path is None:
                return False
        if path == self.sdpath:
            if not platform.is_sd_present():
                raise KeyStoreError("SD card is not present")
            platform.mount_sdcard()
        if not platform.file_exists(path):
            raise KeyStoreError("Secret is not saved. No need to delete anything.")
        try:
            os.remove(path)
        except Exception as e:
            print(e)
            raise KeyStoreError("Failed to delete file at " + path)
        finally:
            if path == self.sdpath:
                platform.unmount_sdcard()
            return True

    async def storage_menu(self):
        """Manage storage and display of the recovery phrase"""
        buttons = [
            # id, text
            (None, "Manage keys on SD card and internal flash"),
            (0, "Save key"),
            (1, "Load key"),
            (2, "Delete key"),
            (None, "Other"),
            (3, "Show recovery phrase"),
        ]

        # we stay in this menu until back is pressed
        while True:
            # wait for menu selection
            menuitem = await self.show(Menu(buttons, last=(255, None)))
            # process the menu button:
            # back button
            if menuitem == 255:
                return
            elif menuitem == 0:
                if await self.save_mnemonic():
                    await self.show(
                        Alert("Success!", "Your key is stored now.", button_text="OK")
                    )
            elif menuitem == 1:
                if await self.load_mnemonic():
                    await self.show(
                        Alert("Success!", "Your key is loaded.", button_text="OK")
                    )
            elif menuitem == 2:
                if await self.delete_mnemonic():
                    await self.show(
                        Alert("Success!", "Your key is deleted.", button_text="OK")
                    )
            elif menuitem == 3:
                await self.show_mnemonic()
