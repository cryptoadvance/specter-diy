from .core import KeyStore, KeyStoreError, PinError
from platform import CriticalErrorWipeImmediately
import platform
from binascii import hexlify, unhexlify
from rng import get_random_bytes
import os
import json
import hashlib
import hmac
from bitcoin import ec, bip39, bip32
import platform
from helpers import encrypt, decrypt, aead_encrypt, aead_decrypt, tagged_hash
import sys
import secp256k1
from gui.screens import Alert, PinScreen


class FlashKeyStore(KeyStore):
    """
    KeyStore that stores secrets in Flash of the MCU
    """

    def __init__(self, path):
        self.path = path
        self._is_locked = True
        self.mnemonic = None
        self.root = None
        self.fingerprint = None
        self.idkey = None
        self.pin = None
        self._pin_attempts_max = 10
        self._pin_attempts_left = 10
        self.pin_secret = None
        self.enc_secret = None
        self.initialized = False
        self.show = None

    def set_mnemonic(self, mnemonic=None, password=""):
        """Load mnemonic and password and create root key"""
        if mnemonic is not None:
            self.mnemonic = mnemonic.strip()
            if not bip39.mnemonic_is_valid(self.mnemonic):
                raise KeyStoreError("Invalid mnemonic")
        seed = bip39.mnemonic_to_seed(self.mnemonic, password)
        self.root = bip32.HDKey.from_seed(seed)
        self.fingerprint = self.root.child(0).fingerprint
        # id key to sign and encrypt wallet files
        # stored on untrusted external chip
        self.idkey = self.root.child(0x1D, hardened=True).key.serialize()

    def sign_psbt(self, psbt):
        psbt.sign_with(self.root)

    def sign_hash(self, derivation, msghash: bytes):
        return self.root.derive(derivation).key.sign(msghash)

    def sign_recoverable(self, derivation, msghash: bytes):
        """Returns a signature and a recovery flag"""
        prv = self.root.derive(derivation).key
        sig = secp256k1.ecdsa_sign_recoverable(msghash, prv._secret)
        flag = sig[64]
        return ec.Signature(sig[:64]), flag

    def save_aead(self, path, adata=b"", plaintext=b"", key=None):
        """Encrypts and saves plaintext and associated data to file"""
        if key is None:
            key = self.idkey
        if key is None:
            raise KeyStoreError("Pass the key please")
        d = aead_encrypt(key, adata, plaintext)
        with open(path, "wb") as f:
            f.write(d)
        platform.sync()

    def load_aead(self, path, key=None):
        """
        Loads data saved with save_aead,
        returns a tuple (associated data, plaintext)
        """
        if key is None:
            key = self.idkey
        if key is None:
            raise KeyStoreError("Pass the key please")
        with open(path, "rb") as f:
            data = f.read()
        return aead_decrypt(data, key)

    def get_xpub(self, path):
        if self.is_locked or self.root is None:
            raise KeyStoreError("Keystore is not ready")
        return self.root.derive(path).to_public()

    def owns(self, key):
        if key.fingerprint is not None and key.fingerprint != self.fingerprint:
            return False
        if key.derivation is None:
            return key.key == self.root.to_public()
        return key.key == self.root.derive(key.derivation).to_public()

    def wipe(self, path):
        """Delete everything in path"""
        platform.delete_recursively(path)

    def load_secret(self, path):
        """Try to load a secret from file,
        create new if doesn't exist"""
        try:
            # try to load secret
            with open(path+"/secret", "rb") as f:
                self.secret = f.read()
        except:
            self.secret = self.create_new_secret(path)

    def load_state(self):
        """Verify file and load PIN state from it"""
        try:
            # verify that the pin file is ok
            _, data = self.load_aead(self.path+"/pin", self.secret)
            # load pin object
            data = json.loads(data.decode())
            self.pin = unhexlify(
                data["pin"]) if data["pin"] is not None else None
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
        # generate new and save
        secret = get_random_bytes(32)
        # save secret
        with open(path+"/secret", "wb") as f:
            f.write(secret)
        # set pin object
        self.pin = None
        self._pin_attempts_max = 10
        self._pin_attempts_left = 10
        self.secret = secret
        self.save_state()
        return secret

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
        return (self.is_pin_set and self._is_locked)

    @property
    def is_ready(self):
        return (self.pin_secret is not None) and \
               (self.enc_secret is not None) and \
               (not self.is_locked) and \
               (self.fingerprint is not None)

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
        pin_hmac = hmac.new(key=key,
                            msg=pin.encode(), digestmod="sha256").digest()
        # check hmac is the same
        if pin_hmac != self.pin:
            raise PinError("Invalid PIN!\n%d of %d attempts left..." % (
                self._pin_attempts_left, self._pin_attempts_max)
            )
        self._pin_attempts_left = self._pin_attempts_max
        self._is_locked = False
        self.save_state()
        # derive PIN keys for reckless storage
        self.pin_secret = tagged_hash("pin", self.secret+pin.encode())
        self.load_enc_secret()

    def load_enc_secret(self):
        fpath = self.path+"/enc_secret"
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

    def get_auth_word(self, pin_part):
        """
        Get anti-phishing word to check internal secret
        from part of the PIN so user can stop when he sees wrong words
        """
        key = tagged_hash("auth", self.secret)
        h = hmac.new(key, pin_part, digestmod="sha256").digest()
        # wordlist is 2048 long (11 bits) so
        # this modulo doesn't create an offset
        word_number = int.from_bytes(h[:2], 'big') % len(bip39.WORDLIST)
        return bip39.WORDLIST[word_number]

    def save_state(self):
        """Saves PIN state to flash"""
        pin = hexlify(self.pin).decode() if self.pin is not None else None
        obj = {
            "pin": pin,
            "pin_attempts_max":  self._pin_attempts_max,
            "pin_attempts_left": self._pin_attempts_left,
        }
        data = json.dumps(obj).encode()
        self.save_aead(self.path+"/pin", plaintext=data, key=self.secret)
        # check it loads
        self.load_state()

    def _set_pin(self, pin):
        """Saves hmac of the PIN code for verification later"""
        # set up pin
        key = tagged_hash("pin", self.secret)
        self.pin = hmac.new(key=key,
                            msg=pin, digestmod="sha256").digest()
        self.pin_secret = tagged_hash("pin", self.secret+pin.encode())
        self.save_state()
        # update encryption secret
        if self.enc_secret is None:
            self.enc_secret = get_random_bytes(32)
        self.save_aead(self.path+"/enc_secret",
                       plaintext=self.enc_secret, key=self.pin_secret)
        # call unlock now
        self._unlock(pin)

    def save_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if self.mnemonic is None:
            raise KeyStoreError("Recovery phrase is not loaded")
        self.save_aead(self.path+"/reckless",
                       plaintext=self.mnemonic.encode(),
                       key=self.pin_secret)
        # check it's ok
        self.load_mnemonic()

    @property
    def is_key_saved(self):
        return platform.file_exists(self.path+"/reckless")

    def load_mnemonic(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if not platform.file_exists(self.path+"/reckless"):
            raise KeyStoreError("Key is not saved")
        _, data = self.load_aead(self.path+"/reckless", self.pin_secret)
        self.set_mnemonic(data.decode(), "")

    def delete_mnemonic(self):
        if not platform.file_exists(self.path+"/reckless"):
            raise KeyStoreError(
                "Secret is not saved. No need to delete anything.")
        try:
            os.remove(self.path+"/reckless")
        except:
            raise KeyStoreError("Failed to delete from memory")

    async def init(self, show_fn):
        """
        Waits for keystore media 
        and loads internal secret and PIN state
        """
        self.show = show_fn
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)
        self.load_state()
        # check if init is called for the first time
        # and we have less than max PIN attempts
        if (not self.initialized 
            and self.pin_attempts_left != self.pin_attempts_max):
            scr = Alert("Warning!",
                        "You only have %d of %d attempts\n"
                        "to enter correct PIN code!" % (
                        self.pin_attempts_left, self.pin_attempts_max),
                        button_text="OK")
            await self.show(scr)
        self.initialized = True

    async def unlock(self):
        # pin is not set - choose one
        if not self.is_pin_set:
            pin = await self.setup_pin()
            self._set_pin(pin)

        # if keystore is locked - ask for PIN code
        while self.is_locked:
            pin = await self.get_pin()
            self._unlock(pin)

    async def get_pin(self, title="Enter your PIN code"):
        """
        Async version of the PIN screen.
        Waits for an event that is set in the callback.
        """
        scr = PinScreen(title=title,
                        note="Do you recognize these words?",
                        get_word=self.get_auth_word)
        return await self.show(scr)

    async def setup_pin(self, get_word=None):
        """
        PIN setup screen - first choose, then confirm
        If PIN codes are the same -> return the PIN
        If not -> try again
        """
        scr = PinScreen(title="Choose your PIN code",
                        note="Remember these words,"
                             "they will stay the same on this device.",
                        get_word=self.get_auth_word)
        pin1 = await self.show(scr)

        scr = PinScreen(title="Confirm your PIN code",
                        note="Remember these words,"
                             "they will stay the same on this device.",
                        get_word=self.get_auth_word)
        pin2 = await self.show(scr)

        # check if PIN is the same
        if pin1 == pin2:
            return pin1
        # if not - show an error
        await self.show(Alert("Error!", "PIN codes are different!"))
        return await self.setup_pin(get_word)

    async def change_pin(self):
        # get_auth_word function can generate words from part of the PIN
        old_pin = await self.get_pin(title="First enter your old PIN code")
        # check pin - will raise if not valid
        self._unlock(old_pin)
        new_pin = await self.setup_pin()
        self._change_pin(old_pin, new_pin)
        await self.show(Alert("Success!",
                              "PIN code is sucessfully changed!",
                              button_text="OK"))
