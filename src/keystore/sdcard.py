from .core import KeyStoreError, PinError
from .flash import FlashKeyStore
from platform import CriticalErrorWipeImmediately
import platform
from rng import get_random_bytes
from bitcoin import bip39
from gui.screens import Alert, Progress, Menu, MnemonicScreen
import asyncio
from io import BytesIO
from helpers import tagged_hash
from binascii import hexlify


class SDKeyStore(FlashKeyStore):
    """
    KeyStore that stores secrets
    in Flash AND on a removable SD card.
    SD card is required to unlock the device.
    Bitcoin key is encrypted with internal MCU secret,
    so the attacker needs to get both the device and the SD card.
    When correct PIN is entered the key can be loaded
    from SD card to the RAM of the MCU.
    """
    # Button to go to storage menu
    # Menu should be implemented in async storage_menu function
    # Here we only have a single option - to show mnemonic
    storage_button = "SD secret storage"

    @property
    def sdpath(self):
        hexid = hexlify(tagged_hash("sdid", self.secret)[:4]).decode()
        return platform.fpath("/sd/specterdiy%s" % hexid)

    def save_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if self.mnemonic is None:
            raise KeyStoreError("Recovery phrase is not loaded")
        if not platform.is_sd_present():
            raise KeyStoreError("SD card is not present")
        platform.mount_sdcard()
        self.save_aead(self.sdpath,
                       plaintext=self.mnemonic.encode(),
                       key=self.enc_secret)
        platform.unmount_sdcard()
        # check it's ok
        self.load_mnemonic()

    @property
    def is_key_saved(self):
        if not platform.is_sd_present():
            raise KeyStoreError("SD card is not present")
        platform.mount_sdcard()
        exists = platform.file_exists(self.sdpath)
        platform.unmount_sdcard()
        return exists

    def load_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if not platform.is_sd_present():
            raise KeyStoreError("SD card is not present")
        platform.mount_sdcard()
        if not platform.file_exists(self.sdpath):
            raise KeyStoreError("Key is not saved")
        _, data = self.load_aead(self.sdpath, self.enc_secret)
        platform.unmount_sdcard()
        self.set_mnemonic(data.decode(), "")

    def delete_mnemonic(self):
        if not platform.is_sd_present():
            raise KeyStoreError("SD card is not present")
        platform.mount_sdcard()
        if not platform.file_exists(self.sdpath):
            raise KeyStoreError(
                "Secret is not saved. No need to delete anything.")
        try:
            os.remove(self.sdpath)
        except:
            raise KeyStoreError("Failed to delete file from SD card")
        finally:
            platform.unmount_sdcard()

    async def wait_for_card(self, scr):
        while not platform.is_sd_present():
            await asyncio.sleep_ms(30)
            scr.tick(5)
        if scr.waiting:
            scr.waiting = False

    async def init(self, show_fn):
        """
        Waits for keystore media (SD card)
        and loads internal secret and PIN state
        """
        self.show = show_fn
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)

        if not platform.is_sd_present():
            # wait for card
            scr = Progress("SD card is not inserted",
                           "Please insert the SD card...",
                           button_text=None) # no button
            asyncio.create_task(self.wait_for_card(scr))
            await show_fn(scr)
        # the rest can be done with parent
        await super().init(show_fn)

    async def storage_menu(self):
        """Manage storage and display of the recovery phrase"""
        buttons = [
            # id, text
            (None, "SD card storage"),
            (0, "Save key to the SD card"),
            (1, "Load key from the SD card"),
            (2, "Delete key from the SD card"),
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
                self.save_mnemonic()
                await self.show(Alert("Success!",
                                     "Your key is stored on the SD card now.",
                                     button_text="OK"))
            elif menuitem == 1:
                self.load_mnemonic()
                await self.show(Alert("Success!",
                                     "Your key is loaded.",
                                     button_text="OK"))
            elif menuitem == 2:
                self.delete_mnemonic()
                await self.show(Alert("Success!",
                                     "Your key is deleted from the SD card.",
                                     button_text="OK"))
            elif menuitem == 3:
                await self.show(MnemonicScreen(self.mnemonic))
