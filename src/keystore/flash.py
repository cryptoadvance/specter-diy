from .core import KeyStore, KeyStoreError, PinError
from platform import CriticalErrorWipeImmediately
from binascii import hexlify, unhexlify
from rng import get_random_bytes
import os, json, hashlib, hmac
from bitcoin import ec, bip39, bip32
import platform
from helpers import encrypt, decrypt

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
        self.state = None
        self.keys = {}

    def load_mnemonic(self, mnemonic=None, password=""):
        """Load mnemonic and password and create root key"""
        if mnemonic is not None:
            self.mnemonic = mnemonic.strip()
            if not bip39.mnemonic_is_valid(self.mnemonic):
                raise KeyStoreError("Invalid mnemonic")
        seed = bip39.mnemonic_to_seed(self.mnemonic, password)
        self.root = bip32.HDKey.from_seed(seed)
        self.fingerprint = self.root.child(0).fingerprint
        # id key to sign wallet files stored on untrusted external chip
        self.idkey = self.root.child(0x1D, hardened=True).key

    def sign_to_file(self, data, path, key=None):
        """Sign a file with a private key"""
        if key is None:
            key = self.idkey
        if key is None:
            raise KeyStoreError("Pass the key please")
        h = hashlib.sha256(data).digest()
        sig = key.sign(h)
        with open(path, "wb") as f:
            f.write(sig.serialize())

    def verify_file(self, path, key=None):
        """
        Verify that the file is signed with the key
        Raises KeyStoreError if signature is invalid
        Returns content of the file if it's ok
        """
        if key is None:
            key = self.idkey
        if key is None:
            raise KeyStoreError("Pass the key please")
        with open(path, "rb") as f:
            data = f.read()
            h = hashlib.sha256(data).digest()
        with open(path+".sig", "rb") as f:
            sig = ec.Signature.parse(f.read())
        pub = key.get_public_key()
        if not pub.verify(sig, h):
            raise KeyStoreError("Signature is invalid!")
        return data

    def get_xpub(self, path):
        if self.is_locked or self.root is None:
            raise KeyStoreError("Keystore is not ready")
        return self.root.derive(path).to_public()

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
            data = self.verify_file(self.path+"/pin.json", self.keys["ecdsa"])
            # load pin object
            self.state = json.loads(data.decode())
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
        data = json.dumps(state)
        # derive signing key
        signing_key = derive_keys(secret)["ecdsa"]
        self.sign_to_file(data, path+"/pin.json.sig", key=signing_key)
        # now we save file itseld
        with open(path+"/pin.json", "w") as f:
            f.write(data)
        return secret

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

    @property
    def is_ready(self):
        return (self.state is not None) and \
               (not self.is_locked) and \
               (self.fingerprint is not None)
    
    def unlock(self, pin):
        """
        Unlock the keystore, raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
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

    def lock(self):
        """Locks the keystore, requires PIN to unlock"""
        self._is_locked = True
        return self.is_locked

    def unset_pin(self):
        self.state["pin"] = None
        self.save_state()

    def change_pin(self, old_pin, new_pin):
        self.unlock(old_pin)
        data = None
        if platform.file_exists(self.path+"/reckless"):
            data = self.verify_file(self.path+"/reckless", self.keys["pin_ecdsa"])
            data = decrypt(data, self.keys["pin_aes"])
        self.set_pin(new_pin)
        if data is not None:
            ct = encrypt(data, self.keys["pin_aes"])
            with open(self.path+"/reckless", "wb") as f:
                f.write(ct)
            self.sign_to_file(ct, self.path+"/reckless.sig", self.keys["pin_ecdsa"])


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
        data = json.dumps(self.state)
        with open(self.path+"/pin.json","w") as f:
            f.write(data)
        self.sign_to_file(data, self.path+"/pin.json.sig", key=self.keys["ecdsa"])
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
        ct = encrypt(self.mnemonic.encode(), self.keys["pin_aes"])
        with open(self.path+"/reckless", "wb") as f:
            f.write(ct)
        self.sign_to_file(ct, self.path+"/reckless.sig", self.keys["pin_ecdsa"])
        # check it's ok
        self.load()

    def load(self):
        if self.is_locked:
            raise KeyStoreError("Keystore is locked")
        if not platform.file_exists(self.path+"/reckless"):
            raise KeyStoreError("Key is not saved")
        data = self.verify_file(self.path+"/reckless", self.keys["pin_ecdsa"])
        self.load_mnemonic(decrypt(data, self.keys["pin_aes"]).decode(),"")

    def delete_saved(self):
        if not platform.file_exists(self.path+"/reckless"):
            raise KeyStoreError("Secret is not saved. No need to delete anything.")
        try:
            os.remove(self.path+"/reckless")
            os.remove(self.path+"/reckless.sig")
        except:
            raise KeyStoreError("Failed to delete from memory")