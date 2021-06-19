from .core import KeyStoreError, PinError
from .flash import FlashKeyStore
import platform
from rng import get_random_bytes
from bitcoin import bip39
from gui.screens import Alert, Progress, Menu, MnemonicScreen, InputScreen, Prompt
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
        flash_files = [
            f[0] for f in os.ilistdir(self.flashpath)
            if f[0].lower().startswith(self.fileprefix(self.flashpath))
        ]
        flash_exists = (len(flash_files) > 0)
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

    def load_files(self, path):
        buttons = []
        files = [f[0] for f in os.ilistdir(path) if f[0].startswith(self.fileprefix(path))]

        if len(files) == 0:
            buttons += [(None, 'No files found')]
        else:
            files.sort()
            for file in files:
                displayname = file.replace(self.fileprefix(path), "")
                if displayname is "":
                    displayname = "Default"
                else:
                    displayname = displayname[1:]  # strip first character
                buttons += [("%s/%s" % (path, file), displayname)]
        return buttons

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

    async def get_input(
            self,
            title="Enter a name for this seed",
            note="Naming your seeds allows you to store multiple.\n"
                 "Give each seed a unique name!",
            suggestion="",
    ):
        scr = InputScreen(title, note, suggestion)
        await self.show(scr)
        return scr.get_value()

    async def export_mnemonic(self):
        if await self.show(Prompt("Warning",
                                  "You need to confirm your PIN code "
                                  "to export your recovery phrase.\n\n"
                                  "Your recovery phrase will be saved "
                                  "to the SD card as plain text.\n\n"
                                  "Anybody who has access to this SD card "
                                  "will be able to read your recovery phrase!\n\n"
                                  "Continue?")):
            self.lock()
            await self.unlock()

            filename = "seed-export-%s.txt" % self.mnemonic.split()[0]
            filepath = "%s/%s" % (self.sdpath, filename)

            if not platform.is_sd_present():
                raise KeyStoreError("SD card is not present")

            platform.mount_sdcard()

            with open(filepath, "w") as f:
                f.write("bip39: ")
                f.write(self.mnemonic)

            platform.unmount_sdcard()

            await self.show(
                Alert("Success!", "Your seed is exported.\n\nName: %s" % filename, button_text="OK")
            )


    async def storage_menu(self):
        """Manage storage"""
        buttons = [
            # id, text
            (None, "Manage keys on SD card and internal flash"),
            (0, "Save key"),
            (1, "Load key"),
            (2, "Delete key"),
        ]

        # disabled if SD card is not present
        buttons.append((3, "Export recovery phrase to SD", platform.is_sd_present()))

        # we stay in this menu until back is pressed
        while True:
            # wait for menu selection
            menuitem = await self.show(Menu(buttons, last=(255, None)))
            # process the menu button:
            # back button
            if menuitem == 255:
                return
            elif menuitem == 0:
                filename = await self.save_mnemonic()
                if filename:
                    await self.show(
                        Alert("Success!", "Your key is stored now.\n\nName: %s" % filename, button_text="OK")
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
                await self.export_mnemonic()
