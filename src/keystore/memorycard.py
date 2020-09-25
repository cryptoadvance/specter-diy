from .core import KeyStoreError, PinError
from .ram import RAMKeyStore
from .javacard.applets.memorycard import MemoryCardApplet, SecureError
from .javacard.util import get_connection
from platform import CriticalErrorWipeImmediately
import platform
from rng import get_random_bytes
from bitcoin import bip39
from helpers import tagged_hash, aead_encrypt, aead_decrypt
import hmac
from gui.screens import Alert, Progress, Menu, MnemonicScreen
import asyncio
from io import BytesIO
from uscard import SmartcardException

class MemoryCard(RAMKeyStore):
    """
    KeyStore that stores secrets on a smartcard
    using MemoryCard Java applet.
    Secret is secured by the PIN code,
    when PIN is entered the secret is moved to
    RAM of the MCU.
    ColdCard's security model.
    """
    NAME = "Smartcard"
    NOTE = """Saves encryption key and Bitcoin key on a PIN-protected external smartcard (requires devkit).
In this mode device can only operate when the smartcard is inserted!"""
    # constants for secret storage
    MAGIC = b"sdiy\x00" # specter-DIY version 0
    KEYS = {
        b"\x01": "enc",
        b"\x02": "entropy",
    }
    # Button to go to storage menu
    # Menu should be implemented in async storage_menu function
    # Here we only have a single option - to show mnemonic
    storage_button = "Smartcard storage"
    load_button = "Load key from smartcard"

    def __init__(self):
        super().__init__()
        # javacard connection
        self.connection = get_connection()
        # applet
        self.applet = MemoryCardApplet(self.connection)
        self._is_key_saved = False
        self.connected = False

    def get_auth_word(self, pin_part):
        """
        Get anti-phishing word to check
        integrity of the device and the card.
        Internal secret, verified card's pubkey and PIN part
        are used to generate the words.
        The user should stop entering the PIN if he sees wrong words.
        It can happen if the device or the card is different.
        """
        # check if secure channel is already open
        # so the card can't lie about it's pubkey
        if not self.applet.is_secure_channel_open:
            raise KeyStoreError("Secure channel is closed.")
        # use both internal secret and card's key to generate
        # anti-phishing words
        key = tagged_hash("auth", self.secret+self.applet.card_pubkey)
        h = hmac.new(key, pin_part, digestmod="sha256").digest()
        # wordlist is 2048 long (11 bits) so
        # this modulo doesn't create an offset
        word_number = int.from_bytes(h[:2], 'big') % len(bip39.WORDLIST)
        return bip39.WORDLIST[word_number]

    @property
    def is_pin_set(self):
        return self.applet.is_pin_set

    @property
    def pin_attempts_left(self):
        return self.applet.pin_attempts_left

    @property
    def pin_attempts_max(self):
        return self.applet.pin_attempts_max

    @property
    def is_locked(self):
        return self.applet.is_locked

    def _unlock(self, pin):
        """
        Unlock the keystore, raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
        try:
            self.applet.unlock(pin)
        except SecureError as e:
            if str(e) == "0502": # wrong PIN
                raise PinError("Invalid PIN!\n%d of %d attempts left..." % (
                    self.pin_attempts_left, self.pin_attempts_max)
                )
            elif str(e) == "0503": # bricked
                self.wipe(self.path)
                raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
            else:
                raise e
        self.load_enc_secret()

    def load_enc_secret(self):
        data = self.applet.get_secret()
        # no data yet
        if len(data) == 0:
            # create new key if it doesn't exist
            secret = get_random_bytes(32)
            # format: magic, 01 len enc_secret, 02 len entropy
            d = self.serialize_data({
                "enc": secret
            })
            self.applet.save_secret(d)
            self._is_key_saved = False
        else:
            try:
                d = self.parse_data(data)
                secret = d["enc"]
                if "entropy" in d:
                    self._is_key_saved = True
            except KeyStoreError as e:
                # wrong data on the card - not a big deal
                # just generate a new key
                self.enc_secret = get_random_bytes(32)
                self._is_key_saved = False
                # notify the user about the error
                raise e
        self.enc_secret = secret

    def serialize_data(self, obj):
        """Serialize secrets for storage on the card"""
        r = b""
        for k in self.KEYS:
            v = self.KEYS[k]
            if v in obj:
                r += k + bytes([len(obj[v])]) + obj[v]
        # smartcard encryption key
        key = tagged_hash("scenc", self.secret)
        # smartcard id to understand it's our data
        fingerprint = tagged_hash("scid", self.secret)[:4]
        res = aead_encrypt(key, self.MAGIC+fingerprint, r)
        print(res)
        return res

    def parse_data(self, data):
        """Parse data stored on the card"""
        s = BytesIO(data)
        # smartcard id to understand it's our data
        fingerprint = tagged_hash("scid", self.secret)[:4]
        l = len(self.MAGIC)+4
        if s.read(l+1) != bytes([l])+self.MAGIC+fingerprint:
            raise KeyStoreError("Looks like stored data is created on a different device.")
        # smartcard encryption key
        key = tagged_hash("scenc", self.secret)
        adata, plaintext = aead_decrypt(data, key=key)
        s = BytesIO(plaintext)
        o = {}
        while True:
            k = s.read(1)
            if len(k) == 0:
                break
            l = s.read(1)[0]
            v = s.read(l)
            assert len(v) == l
            if k in self.KEYS:
                o[self.KEYS[k]] = v
        return o

    def lock(self):
        """Locks the keystore, requires PIN to unlock"""
        self.applet.lock()
        return self.is_locked

    def _change_pin(self, old_pin, new_pin):
        # lock-unlock then change
        # so if we've got wrong PIN
        # we remain is_locked
        self.lock()
        self._unlock(old_pin)
        self.applet.change_pin(old_pin, new_pin)
        self._unlock(new_pin)

    def _set_pin(self, pin):
        """Sets PIN code for verification later"""
        if self.is_pin_set:
            raise KeyStoreError("PIN is already set")
        self.applet.set_pin(pin)
        # call unlock now
        self._unlock(pin)

    async def save_mnemonic(self):
        await self.check_card(check_pin=True)
        d = self.serialize_data({
            "enc": self.enc_secret,
            "entropy": bip39.mnemonic_to_bytes(self.mnemonic)
        })
        self.applet.save_secret(d)
        self._is_key_saved = True
        # check it's ok
        await self.load_mnemonic()

    @property
    def is_key_saved(self):
        return self._is_key_saved

    async def load_mnemonic(self):
        await self.check_card(check_pin=True)
        if not self._is_key_saved:
            raise KeyStoreError("Key is not saved")
        data = self.applet.get_secret()
        entropy = self.parse_data(data)["entropy"]
        mnemonic = bip39.mnemonic_from_bytes(entropy)
        self.set_mnemonic(mnemonic, "")
        return True

    async def delete_mnemonic(self):
        await self.check_card(check_pin=True)
        d = self.serialize_data({
            "enc": self.enc_secret
        })
        self.applet.save_secret(d)
        self._is_key_saved = False

    async def check_card(self, check_pin=False):
        if not self.connection.isCardInserted():
            # wait for card
            scr = Progress("Smartcard is not inserted",
                           "Please insert the smartcard...",
                           button_text=None) # no button
            asyncio.create_task(self.wait_for_card(scr))
            await self.show(scr)
        try:
            self.applet.ping()
        except Exception as e:
            print(e)
            self.connected = False
        # only required if not connected yet
        if not self.connected:
            # connect and select applet
            self.connection.connect(self.connection.T1_protocol)
            try:
                self.applet.select()
            except:
                raise KeyStoreError("Failed to select MemoryCardApplet")
            self.applet.open_secure_channel()
            self.connected = True
        self.applet.get_pin_status()
        if check_pin and self.is_locked:
            pin = await self.get_pin()
            self._unlock(pin)

    async def wait_for_card(self, scr):
        while not self.connection.isCardInserted():
            await asyncio.sleep_ms(30)
            scr.tick(5)
        if scr.waiting:
            scr.waiting = False

    async def init(self, show_fn):
        """
        Waits for keystore media 
        and loads internal secret and PIN state
        """
        self.show = show_fn
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)

        await self.check_card()
        # the rest can be done with parent
        await super().init(show_fn)

    async def storage_menu(self):
        """Manage storage and display of the recovery phrase"""
        enabled = self.connection.isCardInserted()
        buttons = [
            # id, text
            (None, "Smartcard storage"),
            (0, "Save key to the card", enabled),
            (1, "Load key from the card", enabled),
            (2, "Delete key from the card", enabled),
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
                await self.show(Alert("Success!",
                                     "Your key is stored on the smartcard now.",
                                     button_text="OK"))
            elif menuitem == 1:
                await self.load_mnemonic()
                await self.show(Alert("Success!",
                                     "Your key is loaded.",
                                     button_text="OK"))
            elif menuitem == 2:
                await self.delete_mnemonic()
                await self.show(Alert("Success!",
                                     "Your key is deleted from the smartcard.",
                                     button_text="OK"))
            elif menuitem == 3:
                await self.show(MnemonicScreen(self.mnemonic))
