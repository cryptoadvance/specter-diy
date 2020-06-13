from .core import KeyStore, KeyStoreError, PinError
from platform import CriticalErrorWipeImmediately
from binascii import hexlify, unhexlify
from rng import get_random_bytes
import json, hashlib, hmac
from bitcoin import ec, bip39, bip32
import platform
from ucryptolib import aes
import os

AES_BLOCK = 16
IV_SIZE   = 16
AES_CBC   = 2

def derive_keys(secret, pin=None):
    """
    Derives application-specific keys from a secret.
    First series of keys are used to check PIN
    Second series uses PIN code as a part of secret material.
    Therefore if attacker bypasses PIN he still needs to find
    correct PIN code to decrypt data.
    """
    # internal secrets, before PIN code entry
    keys = {    "secret": secret,
                # to sign stuff
                "ecdsa": ec.PrivateKey(hashlib.sha256(b"ecdsa"+secret).digest()),
                # to hmac stuff
                "hmac": hashlib.sha256(b"hmac"+secret).digest(),
                "auth": hashlib.sha256(b"auth"+secret).digest(),
            }
    if pin is not None:
        # keys derived from secret and PIN code
        pin_key = hashlib.sha256(b"keys"+secret+pin).digest()
        # for encryption of stuff
        keys["pin_aes"] = hashlib.sha256(b"aes"+pin_key).digest()
        keys["pin_hmac"] = hashlib.sha256(b"hmac"+pin_key).digest()
        keys["pin_ecdsa"] = ec.PrivateKey(hashlib.sha256(b"ecdsa"+pin_key).digest())
    return keys

def sign_file(path, key):
    """Sign a file with a private key"""
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).digest()
    sig = key.sign(h)
    with open(path+".sig", "wb") as f:
        f.write(sig.serialize())

def verify_file(path, key):
    """
    Verify that the file is signed with the key
    Raises KeyStoreError if signature is invalid
    """
    with open(path, "rb") as f:
        h = hashlib.sha256(f.read()).digest()
    with open(path+".sig", "rb") as f:
        sig = ec.Signature.parse(f.read())
    pub = key.get_public_key()
    if not pub.verify(sig, h):
        raise KeyStoreError("Signature is invalid!")

def encrypt(data, key):
    """Encrypt data with AES_CBC 80... padding"""
    iv = get_random_bytes(IV_SIZE)
    crypto = aes(key, AES_CBC, iv)
    # encrypted data should be mod 16 (blocksize)
    # we do x80000.. padding
    data += b'\x80'
    if len(data) % AES_BLOCK != 0:
        data += b"\x00"*(AES_BLOCK-(len(data) % AES_BLOCK))
    return iv+crypto.encrypt(data)

def decrypt(data, key):
    """Decrypt data with AES_CBC 80... padding"""
    iv = data[:IV_SIZE]
    ct = data[IV_SIZE:]
    # 2 - MODE_CBC
    crypto = aes(key, AES_CBC, iv)
    plain = crypto.decrypt(ct)
    # remove padding
    d = b"\x80".join(plain.split(b"\x80")[:-1])
    return d

class FlashKeyStore(KeyStore):
    """
    KeyStore that stores secrets in Flash of the MCU
    """
    def __init__(self, path):
        self.path=path
        self._is_locked = True
        self.mnemonic = None
        self.root = None
        self.fingerprint = None
        self.idkey = None
        self.keys = {}

    def load_mnemonic(self, mnemonic=None, password=""):
        """Load mnemonic and password and create root key"""
        if mnemonic is not None:
            self.mnemonic = mnemonic
        seed = bip39.mnemonic_to_seed(self.mnemonic, password)
        self.root = bip32.HDKey.from_seed(seed)
        self.fingerprint = self.root.child(0).fingerprint
        # id key to sign wallet files stored on untrusted external chip
        self.idkey = self.root.child(0x1D, hardened=True)

    def init(self):
        """Load internal secret and PIN state"""
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)
        self.load_state()

    def wipe(self, path):
        """Delete everything in path"""
        platform.delete_recursively(path)

    def load_secret(self, path):
        """Try to load a secret from file,
        create new if doesn't exist"""
        try:
            # try to load secret
            with open(path+"/secret","rb") as f:
                secret = f.read()
        except:
            secret = self.create_new_secret(path)
        self.keys.update(derive_keys(secret))

    def load_state(self):
        """Verify file and load PIN state from it"""
        try:
            # verify that the pin file is ok
            verify_file(self.path+"/pin.json", self.keys["ecdsa"])
            # load pin object
            with open(self.path+"/pin.json","r") as f:
                self.state = json.load(f)
        except Exception as e:
            self.wipe(self.path)
            raise CriticalErrorWipeImmediately(
                "Something went terribly wrong!\nDevice is wiped!\n%s" % e
            )


    def create_new_secret(self, path):
        """Generate new secret and default PIN config"""
        # generate new and save
        secret = get_random_bytes(32)
        # save secret
        with open(path+"/secret","wb") as f:
            f.write(secret)
        # set pin object
        state = {
            "pin": None,
            "pin_attempts_left": 10,
            "pin_attempts_max": 10
        }
        # save and sign pin file
        with open(path+"/pin.json", "w") as f:
            json.dump(state, f)
        # derive signing key
        signing_key = derive_keys(secret)["ecdsa"]
        sign_file(path+"/pin.json", key=signing_key)
        return secret

    def get_status(self):
        """Check card status"""
        if not self.is_pin_set:
            self.status = (self.STATUS_SETUP, None)
        elif self._is_locked:
            if self.pin_attempts_left > 0:
                self.status = (self.STATUS_LOCKED, 
                    "%d of %d attempts left" % (
                        self.pin_attempts_left,
                        self.pin_attempts_max
                    )
                )
            else:
                self.status = (self.STATUS_BLOCKED, 
                               "No more PIN attempts left")
        else:
            self.status = (self.STATUS_UNLOCKED, None)
        return self.status

    @property
    def is_pin_set(self):
        return self.state["pin"] is not None

    @property
    def pin_attempts_left(self):
        return self.state["pin_attempts_left"]

    @property
    def pin_attempts_max(self):
        return self.state["pin_attempts_max"]

    @property
    def is_locked(self):
        return (self.is_pin_set and self._is_locked)

    def unlock(self, pin):
        """
        Unlock the keystore, raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
        # if not locked - we are good
        if not self.is_locked:
            return
        # decrease the counter
        self.state["pin_attempts_left"]-=1
        self.save_state()
        # check we have attempts
        if self.state["pin_attempts_left"] <= 0:
            self.wipe(self.path)
            raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
        # calculate hmac with entered PIN
        pin_hmac = hexlify(hmac.new(key=self.keys["hmac"],
                                msg=pin, digestmod="sha256").digest()).decode()
        # check hmac is the same
        if pin_hmac != self.state["pin"]:
            raise PinError("Invalid PIN!\n%d of %d attempts left..." % (
                self.state["pin_attempts_left"], self.state["pin_attempts_max"])
            )
        self.state["pin_attempts_left"] = self.state["pin_attempts_max"]
        self._is_locked = False
        self.save_state()
        # derive PIN keys for reckless storage
        self.keys.update(derive_keys(self.keys["secret"], pin))
        return self.get_status()

    def lock(self):
        """Locks the keystore, requires PIN to unlock"""
        self._is_locked = True
        return self.get_status()

    def unset_pin(self):
        self.state["pin"] = None
        self.save_state()

    def get_auth_word(self, pin_part):
        """
        Get anti-phishing word to check internal secret
        from part of the PIN so user can stop when he sees wrong words
        """
        h = hmac.new(self.keys["auth"], pin_part, digestmod="sha256").digest()
        # wordlist is 2048 long (11 bits) so
        # this modulo doesn't create an offset
        word_number = int.from_bytes(h[:2],'big') % len(bip39.WORDLIST)
        return bip39.WORDLIST[word_number]

    def save_state(self):
        """Saves PIN state to flash"""
        with open(self.path+"/pin.json","w") as f:
            json.dump(self.state, f)
        sign_file(self.path+"/pin.json", key=self.keys["ecdsa"])
        # check it loads
        self.load_state()

    def set_pin(self, pin):
        """Saves hmac of the PIN code for verification later"""
        # set up pin
        self.state["pin"] = hexlify(hmac.new(key=self.keys["hmac"],
                                msg=pin,digestmod="sha256").digest()).decode()
        self.save_state()
        # call unlock now
        self.unlock(pin)

    def save(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if self.mnemonic is None:
            raise KeyStoreError("Recovery phrase is not loaded")
        with open(self.path+"/reckless", "wb") as f:
            f.write(encrypt(self.mnemonic.encode(), self.keys["pin_aes"]))
        sign_file(self.path+"/reckless", self.keys["pin_ecdsa"])
        # check it's ok
        self.load()

    def load(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if not platform.file_exists(self.path+"/reckless"):
            raise KeyStoreError("Key is not saved")
        verify_file(self.path+"/reckless", self.keys["pin_ecdsa"])
        with open(self.path+"/reckless", "rb") as f:
            data = f.read()
        self.load_mnemonic(decrypt(data, self.keys["pin_aes"]).decode(),"")

    def delete_saved(self):
        if not platform.file_exists(self.path+"/reckless"):
            raise KeyStoreError("Secret is not saved. No need to delete anything.")
        try:
            os.remove(self.path+"/reckless")
            os.remove(self.path+"/reckless.sig")
        except:
            raise KeyStoreError("Failed to delete from memory")