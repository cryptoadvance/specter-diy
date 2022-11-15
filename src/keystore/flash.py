import os
import sys
import json
import hmac
import hashlib
import platform

from .core import KeyStoreError, PinError
from .ram import RAMKeyStore
from platform import CriticalErrorWipeImmediately
from binascii import hexlify, unhexlify
from rng import get_random_bytes
from embit import ec, bip39, bip32
from helpers import tagged_hash
from gui.screens import Alert, PinScreen, Menu, MnemonicScreen, InputScreen


class FlashKeyStore(RAMKeyStore):
    """
    KeyStore that stores secrets in Flash of the MCU.
    By default the bitcoin secret is not stored in Flash,
    so the device operates in amnesic mode.
    To save the key on the flash
    you need to call `save_mnemonic` method.
    At most one mnemonic can be stored.
    Trezor's security model.
    """

    NAME = "Internal storage"
    NOTE = "Uses internal memory of the microcontroller for all keys."
    # Button to go to storage menu
    # Menu is implemented in async storage_menu function
    storage_button = "Flash storage"
    load_button = "Load key from internal memory"

    def __init__(self):
        super().__init__()
        self._is_locked = True
        # PIN is not the user PIN itself
        # but a hmac of internal secret with user's PIN
        # see _unlock() method for details
        self.pin = None
        self._pin_attempts_max = 10
        self._pin_attempts_left = 10
        # PIN secret derived from PIN and internal secret
        # tagged_hash("pin", self.secret+pin.encode())
        self.pin_secret = None

    def load_state(self):
        """Verify file and load PIN state from it"""
        # If PIN file doesn't exist - create it
        # This can happen if the device was initialized with the smartcard
        if not platform.file_exists(self.path + "/pin"):
            self.create_empty_pin_file()
            return
        try:
            # verify that the pin file is ok
            _, data = self.load_aead(self.path + "/pin", self.secret)
            # load pin object
            data = json.loads(data.decode())
            self.pin = unhexlify(data["pin"]) if data["pin"] is not None else None
            self._pin_attempts_max = data["pin_attempts_max"]
            self._pin_attempts_left = data["pin_attempts_left"]
        except Exception as e:
            # this happens if someone tries to change PIN file
            self.wipe(self.path)
            raise CriticalErrorWipeImmediately(
                "Something went terribly wrong!\nDevice is wiped!\n%s" % e
            )

    def create_empty_pin_file(self):
        self.pin = None
        self._pin_attempts_max = 10
        self._pin_attempts_left = 10
        self.save_state()

    def create_new_secret(self, path):
        """Generate new secret and default PIN config"""
        super().create_new_secret(path)
        # set pin object
        self.create_empty_pin_file()
        return self.secret

    @property
    def is_pin_set(self):
        return self.pin is not None

    @property
    def pin_attempts_left(self):
        return self._pin_attempts_left

    @property
    def pin_attempts_max(self):
        return self._pin_attempts_max

    @property
    def is_locked(self):
        return self.is_pin_set and self._is_locked

    @property
    def is_ready(self):
        return (
            (self.pin_secret is not None)
            and (self.enc_secret is not None)
            and (not self.is_locked)
            and (self.fingerprint is not None)
        )

    def _unlock(self, pin):
        """
        Unlock the keystore, raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
        # if anything goes wrong here - wipe
        try:
            # decrease the counter
            self._pin_attempts_left -= 1
            self.save_state()
            # check we have attempts
            if self._pin_attempts_left <= 0:
                self.wipe(self.path)
                raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
        except Exception as e:
            # convert any error to a critical error to wipe the device
            raise CriticalErrorWipeImmediately(str(e))
        # calculate hmac with entered PIN
        key = tagged_hash("pin", self.secret)
        pin_hmac = hmac.new(key=key, msg=pin.encode(), digestmod="sha256").digest()
        # check hmac is the same
        if pin_hmac != self.pin:
            raise PinError(
                "Invalid PIN!\n%d of %d attempts left..."
                % (self._pin_attempts_left, self._pin_attempts_max)
            )
        self._pin_attempts_left = self._pin_attempts_max
        self._is_locked = False
        self.save_state()
        # derive PIN keys for reckless storage
        self.pin_secret = tagged_hash("pin", self.secret + pin.encode())
        self.load_enc_secret()

    def load_enc_secret(self):
        fpath = self.path + "/enc_secret"
        if platform.file_exists(fpath):
            _, secret = self.load_aead(fpath, self.pin_secret)
        else:
            # create new key if it doesn't exist
            secret = get_random_bytes(32)
            self.save_aead(fpath, plaintext=secret, key=self.pin_secret)
        self.enc_secret = secret

    def lock(self):
        """Locks the keystore, requires PIN to unlock"""
        self._is_locked = True
        return self.is_locked

    def _change_pin(self, old_pin, new_pin):
        self._unlock(old_pin)
        self._set_pin(new_pin)

    def save_state(self):
        """Saves PIN state to flash"""
        pin = hexlify(self.pin).decode() if self.pin is not None else None
        obj = {
            "pin": pin,
            "pin_attempts_max": self._pin_attempts_max,
            "pin_attempts_left": self._pin_attempts_left,
        }
        data = json.dumps(obj).encode()
        self.save_aead(self.path + "/pin", plaintext=data, key=self.secret)
        # check it loads
        self.load_state()

    def _set_pin(self, pin):
        """Saves hmac of the PIN code for verification later"""
        # set up pin
        key = tagged_hash("pin", self.secret)
        self.pin = hmac.new(key=key, msg=pin, digestmod="sha256").digest()
        self.pin_secret = tagged_hash("pin", self.secret + pin.encode())
        self.save_state()
        # update encryption secret
        if self.enc_secret is None:
            self.enc_secret = get_random_bytes(32)
        self.save_aead(
            self.path + "/enc_secret", plaintext=self.enc_secret, key=self.pin_secret
        )
        # call unlock now
        self._unlock(pin)

    @property
    def flashpath(self):
        """Path to store bitcoin key"""
        return self.path

    async def init(self, show_fn, show_loader):
        """
        Waits for keystore media
        and loads internal secret and PIN state
        """
        self.show = show_fn
        self.show_loader = show_loader
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)
        self.load_state()
        # the rest we can get from parent
        await super().init(show_fn, show_loader)

    def fileprefix(self, path):
        if path is self.flashpath:
            return 'reckless'

        hexid = hexlify(tagged_hash("sdid", self.secret)[:4]).decode()
        return "specterdiy%s" % hexid


    async def save_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if self.mnemonic is None:
            raise KeyStoreError("Recovery phrase is not loaded")

        path = self.flashpath
        filename = await self.get_input(suggestion=self.mnemonic.split()[0])
        if filename is None:
            return

        fullpath = "%s/%s.%s" % (path, self.fileprefix(path), filename)

        if platform.file_exists(fullpath):
            scr = Prompt(
                "\n\nFile already exists: %s\n" % filename,
                "Would you like to overwrite this file?",
            )
            res = await self.show(scr)
            if res is False:
                return

        self.save_aead(fullpath, plaintext=self.mnemonic.encode(),
                       key=self.enc_secret)
        # check it's ok
        await self.load_mnemonic(fullpath)
        # return the full file name incl. prefix if saved to SD card, just the name if on flash
        return filename

    @property
    def is_key_saved(self):
        flash_files = [
            f[0] for f in os.ilistdir(self.flashpath)
            if f[0].lower().startswith(self.fileprefix(self.flashpath))
        ]
        flash_exists = (len(flash_files) > 0)
        return flash_exists

    async def load_mnemonic(self, file=None):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")

        if file is None:
            file = await self.select_file()
            if file is None:
                return False

        if not platform.file_exists(file):
            raise KeyStoreError("Key is not saved")
        _, data = self.load_aead(file, self.enc_secret)

        self.set_mnemonic(data.decode(), "")
        return True

    async def select_file(self):

        buttons = [(None, 'Internal storage')]
        buttons += self.load_files(self.flashpath)

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
        if not platform.file_exists(file):
            raise KeyStoreError("File not found.")
        try:
            os.remove(file)
        except Exception as e:
            print(e)
            raise KeyStoreError("Failed to delete file '%s'" % file)
        finally:
            return True

    async def get_input(
            self,
            title="Enter a name for this seed",
            note="Naming your seeds allows you to store multiple.\n"
                 "Give each seed a unique name!",
            suggestion="",
    ):
        scr = InputScreen(title, note, suggestion, min_length=1, strip=True)
        await self.show(scr)
        return scr.get_value()


    async def storage_menu(self, title="Manage keys on internal flash"):
        """Manage storage, return True if new key was loaded"""
        buttons = [
            # id, text
            (None, title),
            (0, "Save key"),
            (1, "Load key"),
            (2, "Delete key"),
        ]

        # we stay in this menu until back is pressed
        while True:
            # wait for menu selection
            menuitem = await self.show(Menu(buttons, last=(255, None)))
            # process the menu button:
            # back button
            if menuitem == 255:
                return False
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
                return True
            elif menuitem == 2:
                if await self.delete_mnemonic():
                    await self.show(
                        Alert("Success!", "Your key is deleted.", button_text="OK")
                    )
