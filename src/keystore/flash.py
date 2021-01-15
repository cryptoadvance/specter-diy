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
from bitcoin import ec, bip39, bip32
from helpers import tagged_hash
from gui.screens import Alert, PinScreen, Menu, MnemonicScreen


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
    storage_button = "Reckless"
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
        try:
            # verify that the pin file is ok
            _, data = self.load_aead(self.path + "/pin", self.secret)
            # load pin object
            data = json.loads(data.decode())
            self.pin = unhexlify(data["pin"]) if data["pin"] is not None else None
            self._pin_attempts_max = data["pin_attempts_max"]
            self._pin_attempts_left = data["pin_attempts_left"]
        except Exception as e:
            self.wipe(self.path)
            sys.print_exception(e)
            raise CriticalErrorWipeImmediately(
                "Something went terribly wrong!\nDevice is wiped!\n%s" % e
            )

    def create_new_secret(self, path):
        """Generate new secret and default PIN config"""
        super().create_new_secret(path)
        # set pin object
        self.pin = None
        self._pin_attempts_max = 10
        self._pin_attempts_left = 10
        self.save_state()
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
        # decrease the counter
        self._pin_attempts_left -= 1
        self.save_state()
        # check we have attempts
        if self._pin_attempts_left <= 0:
            self.wipe(self.path)
            raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
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

    async def save_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if self.mnemonic is None:
            raise KeyStoreError("Recovery phrase is not loaded")
        self.save_aead(
            self.flashpath, plaintext=self.mnemonic.encode(), key=self.enc_secret
        )
        # check it's ok
        await self.load_mnemonic()

    @property
    def flashpath(self):
        """Path to store bitcoin key"""
        return self.path + "/reckless"

    @property
    def is_key_saved(self):
        return platform.file_exists(self.flashpath)

    async def load_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if not platform.file_exists(self.flashpath):
            raise KeyStoreError("Key is not saved")
        _, data = self.load_aead(self.flashpath, self.enc_secret)
        self.set_mnemonic(data.decode(), "")
        return True

    async def delete_mnemonic(self):
        if not platform.file_exists(self.flashpath):
            raise KeyStoreError("Secret is not saved. No need to delete anything.")
        try:
            os.remove(self.flashpath)
        except:
            raise KeyStoreError("Failed to delete from memory")

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

    async def storage_menu(self):
        """Manage storage and display of the recovery phrase"""
        buttons = [
            # id, text
            (None, "Key management"),
            (0, "Save key to flash"),
            (1, "Load key from flash"),
            (2, "Delete key from flash"),
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
                await self.save_mnemonic()
                await self.show(
                    Alert(
                        "Success!", "Your key is stored in flash now.", button_text="OK"
                    )
                )
            elif menuitem == 1:
                await self.load_mnemonic()
                await self.show(
                    Alert("Success!", "Your key is loaded.", button_text="OK")
                )
            elif menuitem == 2:
                await self.delete_mnemonic()
                await self.show(
                    Alert(
                        "Success!", "Your key is deleted from flash.", button_text="OK"
                    )
                )
            elif menuitem == 3:
                await self.show_mnemonic()
