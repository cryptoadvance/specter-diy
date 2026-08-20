from .core import KeyStore, KeyStoreError
from platform import CriticalErrorWipeImmediately
import platform
import os
from rng import get_random_bytes
import hmac
from embit import ec, bip39, bip32
from embit.liquid import slip77
from embit.transaction import SIGHASH
from helpers import aead_encrypt, aead_decrypt, tagged_hash
import secp256k1
from gui.screens import Alert, PinScreen, Prompt, Menu, QRAlert, InputScreen
from gui.screens.mnemonic import ExportMnemonicScreen
from binascii import hexlify

# formats offered when exporting a recovery phrase to the SD card
SD_EXPORT_PLAIN = "plain"
SD_EXPORT_BITBOX = "bitbox"
SD_EXPORT_ENCRYPTED = "enc"

class RAMKeyStore(KeyStore):
    """
    KeyStore that doesn't store your keys.
    Don't use directly. It's a parent class for inheritance.
    For PIN verifiction implement
    _set_pin, _unlock, _change_pin and other pin-related methods.
    """

    storage_button = None

    def __init__(self):
        # bip39 mnemonic
        self.mnemonic = None
        # root xprv (derived from mnemonic, password)
        self.root = None
        # root fingerprint
        self.fingerprint = None
        # slip77 blinding key
        self.slip77_key = None
        # private key at path m/0x1D'
        # used to encrypt & authenticate data
        # specific to this root key
        self.idkey = None
        # unique secret for a device
        # used to show anti-phishing words
        self.secret = None
        # encryption secret for untrusted data storage
        # stored encrypted with PIN secret
        # if PIN changed we only need to re-encrypt
        # this secret, all the data remains the same
        self.enc_secret = None
        # user key - same for RAM / SDCard keystore
        # but different for smartcards
        # to isolate card owners from each other
        self._userkey = None
        self.initialized = False
        # show function for menus and stuff
        self.show = None

    def set_mnemonic(self, mnemonic=None, password=""):
        if mnemonic == self.mnemonic and password != "":
            # probably checking mnemonic after saving
            self.show_loader()
        else:
            self.show_loader(title="Generating keys...")
        """Load mnemonic and password and create root key"""
        if mnemonic is not None:
            self.mnemonic = mnemonic.strip()
            if not bip39.mnemonic_is_valid(self.mnemonic):
                raise KeyStoreError("Invalid mnemonic")
        seed = bip39.mnemonic_to_seed(self.mnemonic, password)
        self.root = bip32.HDKey.from_seed(seed)
        self.fingerprint = self.root.child(0).fingerprint
        # slip 77 blinding key
        self.slip77_key = slip77.master_blinding_from_seed(seed)
        # id key to sign and encrypt wallet files
        # stored on untrusted external chip
        self.idkey = self.root.child(0x1D, hardened=True).key.serialize()

    def sign_psbt(self, psbt, sighash=SIGHASH.ALL):
        psbt.sign_with(self.root, sighash)

    def sign_input(self, psbtv, i, sig_stream, sighash=SIGHASH.ALL, extra_scope_data=None):
        return psbtv.sign_input(i, self.root, sig_stream, sighash=sighash, extra_scope_data=extra_scope_data)

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
            with open(path + "/secret", "rb") as f:
                self.secret = f.read()
        except:
            self.secret = self.create_new_secret(path)

    @property
    def userkey(self):
        if self._userkey is None:
            self._userkey = tagged_hash("userkey", self.secret)
        return self._userkey

    @property
    def uid(self):
        """Uniquie identifier for the user (unique for card / device)"""
        return hexlify(tagged_hash("uid", self.userkey)[:4]).decode()

    @property
    def settings_key(self):
        return tagged_hash("settings key", self.secret)

    def create_new_secret(self, path):
        """Generate new secret and default PIN config"""
        # generate new and save
        secret = get_random_bytes(32)
        # save secret
        with open(path + "/secret", "wb") as f:
            f.write(secret)
        self.secret = secret
        return secret

    def get_auth_word(self, pin_part):
        """
        Get anti-phishing word to check internal secret
        from part of the PIN so user can stop when he sees wrong words
        """
        key = tagged_hash("auth", self.secret)
        h = hmac.new(key, pin_part, digestmod="sha256").digest()
        # wordlist is 2048 long (11 bits) so
        # this modulo doesn't create an offset
        word_number = int.from_bytes(h[:2], "big") % len(bip39.WORDLIST)
        return bip39.WORDLIST[word_number]

    def app_secret(self, app):
        return tagged_hash(app, self.secret)

    @property
    def is_ready(self):
        return (
            (not self.is_locked)
            and (self.fingerprint is not None)
        )

    @property
    def is_locked(self):
        """
        Override this method!!!
        with your locking check function
        """
        # hack: we don't support PIN but
        # we need enc_secret, so let's do it here.
        # DONT USE THIS IF YOU HAVE PIN SUPPORT!
        if self.enc_secret is None and self.secret is not None:
            self.enc_secret = tagged_hash("enc", self.secret)
        return False

    @property
    def is_key_saved(self):
        """
        Override this method
        to detect if the key is stored
        """
        return False

    @property
    def pin_attempts_left(self):
        """
        Override this property
        with a function to get number of attempts left.
        """
        return self.pin_attempts_max

    @property
    def pin_attempts_max(self):
        """
        Override this property
        with a function to get max number of attempts.
        """
        return 10

    @property
    def is_pin_set(self):
        """
        Override this property
        with a function to get PIN state.
        """
        return True

    def lock(self):
        """Locks the keystore"""
        pass

    def _unlock(self, pin):
        """
        Implement this.
        Unlock the keystore, raises PinError if PIN is invalid.
        Raises CriticalErrorWipeImmediately if no attempts left.
        """
        # check we have attempts
        if self.pin_attempts_left <= 0:
            # wipe is happening automatically on this error
            raise CriticalErrorWipeImmediately("No more PIN attempts!\nWipe!")
        # check PIN code somehow, raise PinError if it's incorrect
        # for reference - first decrease PIN counter, then check PIN
        # raise PIN Error if it's invalid like this:
        # if pin == "INVALID PIN":
        #     raise PinError("Invalid PIN!\n%d of %d attempts left..." % (
        #         self._pin_attempts_left, self._pin_attempts_max)
        #     )
        # reset PIN counter here and unlock

        # set encryption secret somehow mb save it
        # don't use this approach, it's just for reference
        self.enc_secret = tagged_hash("enc", self.secret)

    def _change_pin(self, old_pin, new_pin):
        """Implement PIN change function"""
        self._unlock(old_pin)

    def _set_pin(self, pin):
        """Implement PIN set function"""
        self._unlock(pin)

    async def init(self, show_fn, show_loader):
        """
        Waits for keystore media
        and loads internal secret and PIN state
        """
        self.show_loader = show_loader
        self.show = show_fn
        platform.maybe_mkdir(self.path)
        self.load_secret(self.path)
        # check if init is called for the first time
        # and we have less than max PIN attempts
        if not self.initialized and self.pin_attempts_left != self.pin_attempts_max:
            scr = Alert(
                "Warning!",
                "You only have %d of %d attempts\n"
                "to enter correct PIN code!"
                % (self.pin_attempts_left, self.pin_attempts_max),
                button_text="OK",
            )
            await self.show(scr)
        self.initialized = True

    async def unlock(self):
        # pin is not set - choose one
        if not self.is_pin_set:
            pin = await self.setup_pin()
            self.show_loader("Setting up PIN code...")
            self._set_pin(pin)

        # if keystore is locked - ask for PIN code
        while self.is_locked:
            pin = await self.get_pin()
            self.show_loader("Verifying PIN code...")
            self._unlock(pin)

    async def get_pin(self, title="Enter your PIN code", with_cancel=False):
        """
        Async version of the PIN screen.
        Waits for an event that is set in the callback.
        """

        scr = PinScreen(
            title=title,
            note="Do you recognize these words?",
            get_word=self.get_auth_word,
            subtitle=self.pin_subtitle,
            with_cancel=with_cancel
        )
        return await self.show(scr)

    @property
    def pin_subtitle(self):
        return "using #%s %s #" % (type(self).COLOR, type(self).NAME.lower())


    async def setup_pin(self, get_word=None):
        """
        PIN setup screen - first choose, then confirm
        If PIN codes are the same -> return the PIN
        If not -> try again
        """
        scr = PinScreen(
            title="Choose your PIN code",
            note="Remember these words," "they will stay the same on this device.",
            get_word=self.get_auth_word,
            subtitle=self.pin_subtitle,
        )
        pin1 = await self.show(scr)

        scr = PinScreen(
            title="Confirm your PIN code",
            note="Remember these words," "they will stay the same on this device.",
            get_word=self.get_auth_word,
            subtitle=self.pin_subtitle,
        )
        pin2 = await self.show(scr)

        # check if PIN is the same
        if pin1 == pin2:
            return pin1
        # if not - show an error
        await self.show(Alert("Error!", "PIN codes are different!"))
        return await self.setup_pin(get_word)

    async def change_pin(self):
        # get_auth_word function can generate words from part of the PIN
        old_pin = await self.get_pin(title="First enter your old PIN code", with_cancel=True)
        if old_pin is None:
            return

        # check pin - will raise if not valid
        self.show_loader("Verifying PIN code...")
        self._unlock(old_pin)
        new_pin = await self.setup_pin()
        self.show_loader("Setting new PIN code...")
        self._change_pin(old_pin, new_pin)
        await self.show(
            Alert("Success!", "PIN code is successfully changed!", button_text="OK")
        )

    async def show_mnemonic(self):
        if not await self.show(Prompt("Warning",
                                  "You need to confirm your PIN code "
                                  "to display your recovery phrase.\n\n"
                                  "Continue?")):
            return
        self.lock()
        await self.unlock()
        while True:
            v = await self.show(ExportMnemonicScreen(self.mnemonic))
            if v == ExportMnemonicScreen.QR:
                v = await self.show(
                        Menu([(1, "SeedQR (digits)"), (2, "Compact SeedQR (binary)"), (3, "Plaintext")],
                        last=(255, None),
                        title="Select encoding format",
                        note="Compact QR is smaller but not human-readable\n")
                    )
                if v == 255:
                    return
                elif v == 1:
                    nums = [bip39.WORDLIST.index(w) for w in self.mnemonic.split()]
                    qr_msg = "".join([("000"+str(n))[-4:] for n in nums])
                    msg = qr_msg
                elif v == 2:
                    qr_msg = bip39.mnemonic_to_bytes(self.mnemonic)
                    msg = hexlify(qr_msg).decode()
                elif v == 3:
                    qr_msg = self.mnemonic
                    msg = self.mnemonic
                await self.show(QRAlert(title="Your mnemonic as QR code", message=msg, qr_message=qr_msg, transcribe=True))
            elif v == ExportMnemonicScreen.SD:
                await self.export_mnemonic_to_sd()
            else:
                return

    @property
    def can_encrypt_for_sd(self):
        """
        Whether this keystore can encrypt SD card backups with a secret
        unique to this device. Only true for SDKeyStore - a smartcard
        keystore has no such device-bound secret to use for this.
        """
        return hasattr(self, "sdpath")

    async def export_mnemonic_to_sd(self):
        """
        Saves the currently loaded mnemonic to the SD card, letting the
        user choose between two unencrypted, portable formats and - when
        this keystore supports it - a copy encrypted with this device's
        own secret.
        """
        if not platform.sdcard.is_present:
            raise KeyStoreError("SD card is not present")

        can_encrypt = self.can_encrypt_for_sd
        buttons = [
            (None, "Choose a format"),
            (SD_EXPORT_PLAIN, "Plain text (Specter format)"),
            (SD_EXPORT_BITBOX, "Bitbox format"),
            (
                SD_EXPORT_ENCRYPTED,
                "Encrypted (this device only)",
                can_encrypt,
            ),
        ]
        note = None
        if not can_encrypt:
            note = (
                "Encrypted storage needs \"Flash & SD card storage\" mode - "
                "restart the device with the smartcard removed to use it."
            )
        fmt = await self.show(
            Menu(
                buttons=buttons,
                title="Save recovery phrase to SD card",
                note=note,
                last=(None, "Cancel"),
            )
        )
        if fmt is None:
            return

        if fmt == SD_EXPORT_ENCRYPTED:
            confirmed = await self.show(
                Prompt(
                    "Encrypted with this device",
                    "\n\nThis copy will be encrypted with a secret unique to "
                    "this device - only this exact device will be able to "
                    "read it back.\n\n"
                    "That's more convenient than plain text, but still not "
                    "as safe as keeping your key on a PIN-protected "
                    "smartcard (Secure Element): if this device is lost, "
                    "damaged or wiped, this backup alone won't protect "
                    "your funds.\n\n"
                    "Continue?",
                )
            )
        elif fmt == SD_EXPORT_BITBOX:
            confirmed = await self.show(
                Prompt(
                    "This will NOT be encrypted!",
                    "\n\nThis writes a native BitBox02-format backup (three "
                    "redundant copies) to the SD card, exactly like a real "
                    "BitBox02 would.\n\n"
                    "Anyone who gets hold of this SD card will have full "
                    "access to your funds.\n\n"
                    "Store and protect it exactly as carefully as a "
                    "handwritten recovery phrase, and never plug it into a "
                    "computer or any other untrusted device.\n\n"
                    "Continue?",
                    warning="Recovery phrase will be stored unencrypted",
                )
            )
        else:
            confirmed = await self.show(
                Prompt(
                    "This will NOT be encrypted!",
                    "\n\nAnyone who gets hold of this SD card will have "
                    "full access to your funds.\n\n"
                    "Store and protect it exactly as carefully as a "
                    "handwritten recovery phrase, and never plug it into a "
                    "computer or any other untrusted device.\n\n"
                    "Continue?",
                    warning="Recovery phrase will be stored unencrypted",
                )
            )
        if not confirmed:
            return

        label = await self.get_input(suggestion=self.mnemonic.split()[0])
        if label is None:
            return
        if not await self.check_label(label):
            return

        platform.sdcard.mount()
        try:
            if fmt == SD_EXPORT_BITBOX:
                display_name, verified = self._write_bitbox_backup(label)
            else:
                sdpath = platform.fpath("/sd")
                if fmt == SD_EXPORT_ENCRYPTED:
                    fullpath = "%s/%s.%s" % (sdpath, self.fileprefix(sdpath), label)
                else:
                    fullpath = "%s/%s.specter.txt" % (sdpath, label)

                if platform.file_exists(fullpath):
                    confirm = await self.show(
                        Prompt(
                            "\n\nFile already exists: %s\n" % fullpath.split("/")[-1],
                            "Would you like to overwrite this file?",
                        )
                    )
                    if not confirm:
                        return

                if fmt == SD_EXPORT_ENCRYPTED:
                    self.save_aead(
                        fullpath, plaintext=self.mnemonic.encode(), key=self.enc_secret
                    )
                    _, check = self.load_aead(fullpath, self.enc_secret)
                    verified = check.decode() == self.mnemonic
                else:
                    with open(fullpath, "w") as f:
                        f.write(self.mnemonic)
                    with open(fullpath, "r") as f:
                        verified = f.read() == self.mnemonic
                display_name = fullpath.split("/")[-1]

            if not verified:
                raise KeyStoreError(
                    "Failed to verify the file that was just saved"
                )
        finally:
            platform.sdcard.unmount()

        await self.show(
            Alert(
                "Success!",
                "Your recovery phrase is saved to\n\n%s\n\nPlease keep it safe."
                % display_name,
            )
        )

    def _write_bitbox_backup(self, label):
        """
        Encodes the current mnemonic as a native BitBox02 microSD backup
        (bitbox_backup.build_backup) and writes it as three redundant
        copies under bitbox02/<backup id>/ on the SD card, the same
        layout a real BitBox02 device uses - readable both by this
        device's own "BitBox microSD backup" import and, in principle, by
        a real BitBox02 (untested on real hardware, see docs/security-model.md).

        Refuses to write if the backup directory already exists and
        contains anything: mixing our three copies with files already
        there (e.g. the timestamped files a real BitBox02 writes for the
        same seed) would leave more than three files in the directory,
        and both this device and real BitBox02 firmware only ever load a
        backup directory containing exactly three files - so "merging"
        would silently corrupt the backup for both.

        The SD card must already be mounted by the caller. Returns
        (display_path, verified), where verified confirms the written
        copies parse back (via bitbox_backup/bitbox_sd, the same code the
        import path uses) to the exact mnemonic that was just encoded.
        """
        import bitbox_backup
        import bitbox_sd

        # NOTE: mnemonic_to_bytes() returns immutable bytes - that one
        # copy of the entropy cannot be zeroized (same documented limit
        # as the mnemonic string itself). Everything derived from it here
        # stays in wipeable bytearrays instead.
        entropy = bip39.mnemonic_to_bytes(self.mnemonic)
        backup_id, encoded = bitbox_backup.build_backup(entropy, name=label)
        written_files = []
        dir_path = None
        try:
            bitbox_root = "%s/%s" % (platform.fpath("/sd"), bitbox_sd.BITBOX_ROOT_DIRNAME)
            dir_path = "%s/%s" % (bitbox_root, backup_id)
            try:
                existing = [
                    e for e in os.ilistdir(dir_path)
                    if e[0] not in (".", "..")
                ]
            except OSError:
                # directory doesn't exist yet - the normal case
                existing = []
            if existing:
                raise KeyStoreError(
                    "A BitBox backup of this key already exists on the "
                    "card.\n\nDelete it first (Device settings -> SD card "
                    "-> Delete data) if you want to replace it."
                )
            platform.maybe_mkdir(bitbox_root)
            platform.maybe_mkdir(dir_path)
            for i in range(bitbox_sd.EXPECTED_FILE_COUNT):
                fname = "%s/%d.bin" % (dir_path, i)
                with open(fname, "wb") as f:
                    f.write(encoded)
                written_files.append(fname)

            raw_files = bitbox_sd.read_backup_files(backup_id)
            try:
                parsed, _, _ = bitbox_backup.load_backup(backup_id, raw_files)
                try:
                    verified = parsed.mnemonic() == self.mnemonic
                finally:
                    parsed.zeroize()
            finally:
                for buf in raw_files:
                    bitbox_backup.zeroize(buf)
        except Exception:
            # Rollback: a failed write (card pulled mid-backup, write
            # error, verification failure, ...) must not leave a partial
            # backup directory on the card. A directory with fewer or
            # more than exactly 3 files is rejected by both this device
            # and real BitBox02 firmware, and the already-written copies
            # contain the plaintext seed - so remove them and the now-
            # empty directory. rmdir only succeeds on empty dirs, so it
            # is safe even if the directory pre-existed (an empty
            # pre-existing dir is harmless to remove here).
            for fname in written_files:
                try:
                    # These files contain the recovery phrase in plaintext.
                    # Unlinking would leave the old sectors recoverable on
                    # FAT/SD, so use the same secure deletion path as the
                    # explicit SD-card delete menu.
                    platform.secure_delete_file(fname)
                except Exception:
                    pass
            if dir_path is not None:
                try:
                    os.rmdir(dir_path)
                except OSError:
                    pass
            raise
        finally:
            bitbox_backup.zeroize(encoded)

        return "%s/%s/" % (bitbox_sd.BITBOX_ROOT_DIRNAME, backup_id), verified

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

    # Characters a user-typed label must not contain when it is used as
    # (part of) a file name: path separators would let it escape the
    # intended directory (traversal), the rest are invalid in FAT file
    # names anyway. Control characters are rejected as well.
    _LABEL_FORBIDDEN_CHARS = '/\\:*?"<>|'

    async def check_label(self, label):
        """Validates a user-typed label before it becomes part of a file
        name on flash or SD card. Shows an error screen and returns False
        if the label can't be used; returns True otherwise."""
        ok = bool(label) and not any(
            (c in self._LABEL_FORBIDDEN_CHARS) or (ord(c) < 32) or (ord(c) == 127)
            for c in label
        )
        if not ok:
            await self.show(Alert(
                "Invalid name",
                "The name is empty or contains characters that are not "
                "allowed in file names.\n\n"
                "Not allowed: / \\ : * ? \" < > | and control characters.\n\n"
                "Please choose a different name.",
                button_text="OK",
            ))
        return ok
