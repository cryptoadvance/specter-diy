"""
Regression tests: saving over an existing key file must neither leave the
old one recoverable nor destroy it before the new one exists.

Two failure modes pull against each other here.

`save_aead()` opens the path "wb". On FAT that truncates the file, which
frees its cluster chain **without** overwriting it, and the new contents
are written wherever the allocator puts them - so the previous encrypted
mnemonic stays readable in free space, where a later secure delete can no
longer reach it and where the unrotated `enc_secret` still decrypts it.

Securely deleting the old file first fixes that and introduces the
opposite problem: the file being replaced may be the user's only
persistent copy, and a pulled card, a failed write or a power cut between
the delete and the new write leaves them with none at all.

`_save_key_file()` therefore writes and verifies the new copy under a
temporary name first, then overwrites the old file, then renames the
temporary file into place.
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import os
from unittest import TestCase

import platform
import keystore.flash as flash_module
import keystore.sdcard as sdcard_module
from keystore.core import KeyStoreError
from keystore.flash import FlashKeyStore, SAVE_TMP_SUFFIX, SAVE_OLD_SUFFIX
from keystore.sdcard import SDKeyStore
from tests.util import clear_testdir


class _FakePrompt:
    """The overwrite confirmation. The native GUI stub's Prompt takes no
    arguments, so stand in for it - self.ks.show() is what decides the
    answer here anyway."""

    def __init__(self, *args, **kwargs):
        pass


class PromptImportTest(TestCase):
    def test_flash_keystore_can_build_the_overwrite_prompt(self):
        """FlashKeyStore.save_mnemonic() referenced Prompt without importing
        it, so confirming an overwrite on internal flash raised NameError
        instead of asking. Nothing here reaches that branch unless the name
        resolves."""
        self.assertIsNotNone(flash_module.Prompt)


def _run(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _SaveMnemonicBase(TestCase):
    keystore_cls = None

    OLD = b"old-encrypted-key-material"

    def setUp(self):
        clear_testdir()
        platform.maybe_mkdir("testdir")
        self.calls = []
        self.ks = self._make_keystore()
        self.ks.path = "testdir"
        self.ks.pin = None  # not locked
        self.ks.mnemonic = "ability " * 11 + "acid"
        self.ks.enc_secret = b"\x00" * 32
        self.target = "testdir/reckless.mykey"
        self.tmp = "testdir/.reckless.mykey" + SAVE_TMP_SUFFIX
        self.old = "testdir/.reckless.mykey" + SAVE_OLD_SUFFIX
        self.plaintext = self.ks.mnemonic.encode()

        test = self

        async def get_input(*args, **kwargs):
            return "mykey"

        async def show(*args, **kwargs):
            return True

        async def load_mnemonic(path, *args, **kwargs):
            return None

        def save_aead(path, adata=b"", plaintext=b"", key=None, strict=False):
            # Stands in for the real AEAD: recognisable on disk, readable
            # by the load_aead() below, and it records the call order.
            test.calls.append(("save_aead", path, strict))
            with open(path, "wb") as f:
                f.write(b"enc:" + plaintext)

        def load_aead(path, key=None):
            test.calls.append(("load_aead", path))
            with open(path, "rb") as f:
                data = f.read()
            if not data.startswith(b"enc:"):
                raise ValueError("not an aead file: %s" % path)
            return b"", data[4:]

        self.ks.get_input = get_input
        self.ks.show = show
        self.ks.load_mnemonic = load_mnemonic
        self.ks.save_aead = save_aead
        self.ks.load_aead = load_aead

        self._real_prompts = (flash_module.Prompt, sdcard_module.Prompt)
        flash_module.Prompt = _FakePrompt
        sdcard_module.Prompt = _FakePrompt

        self._real_delete = platform.secure_delete_file

        def recording_delete(path):
            test.calls.append(("secure_delete", path))
            return test._real_delete(path)

        platform.secure_delete_file = recording_delete

    def tearDown(self):
        flash_module.Prompt, sdcard_module.Prompt = self._real_prompts
        platform.secure_delete_file = self._real_delete
        clear_testdir()

    def _make_keystore(self):
        return self.keystore_cls()

    def _write_existing(self):
        with open(self.target, "wb") as f:
            f.write(self.OLD)

    def _read(self, path):
        with open(path, "rb") as f:
            return f.read()

    def _kinds(self):
        return [(c[0], c[1]) for c in self.calls]

    def test_new_copy_is_written_and_verified_before_the_old_one_dies(self):
        self._write_existing()

        _run(self.ks.save_mnemonic())

        self.assertEqual(
            self._kinds(),
            [
                ("save_aead", self.tmp),
                ("load_aead", self.tmp),
                ("secure_delete", self.old),
            ],
        )
        self.assertEqual(self._read(self.target), b"enc:" + self.plaintext)
        self.assertFalse(platform.file_exists(self.tmp))
        self.assertFalse(platform.file_exists(self.old))

    def test_the_replacing_write_is_synced_strictly(self):
        """platform.sync() swallows every sync error. Losing this write
        means losing the only copy of a recovery phrase, so it is the one
        save that must hear about a failed sync."""
        self._write_existing()

        _run(self.ks.save_mnemonic())

        saves = [c for c in self.calls if c[0] == "save_aead"]
        self.assertTrue(all(c[2] for c in saves), saves)

    def test_a_new_file_is_saved_strictly_and_without_a_temp_file(self):
        self.assertFalse(platform.file_exists(self.target))

        _run(self.ks.save_mnemonic())

        self.assertEqual(self.calls, [("save_aead", self.target, True)])
        self.assertFalse(platform.file_exists(self.tmp))

    def test_a_failed_write_of_the_new_copy_keeps_the_old_file(self):
        """The exact case that makes destroying the old file first
        unacceptable: the replacement never reaches the medium."""
        self._write_existing()

        def failing_save(path, adata=b"", plaintext=b"", key=None, strict=False):
            self.calls.append(("save_aead", path, strict))
            raise OSError("simulated I/O failure")

        self.ks.save_aead = failing_save

        # Reported as a KeyStoreError rather than a bare OSError: the
        # device shows an unhandled exception as a raw traceback, and "the
        # write failed" is something the user can act on.
        with self.assertRaises(KeyStoreError):
            _run(self.ks.save_mnemonic())

        self.assertEqual(self._read(self.target), self.OLD)
        self.assertNotIn(("secure_delete", self.old), self._kinds())
        self.assertFalse(platform.file_exists(self.tmp))

    def test_a_new_copy_that_does_not_read_back_keeps_the_old_file(self):
        self._write_existing()

        def wrong_load(path, key=None):
            self.calls.append(("load_aead", path))
            return b"", b"something else entirely"

        self.ks.load_aead = wrong_load

        with self.assertRaises(KeyStoreError):
            _run(self.ks.save_mnemonic())

        self.assertEqual(self._read(self.target), self.OLD)
        self.assertNotIn(("secure_delete", self.old), self._kinds())
        self.assertFalse(platform.file_exists(self.tmp))

    def test_the_replacement_is_in_place_before_the_old_copy_dies(self):
        """The reason the swap renames instead of deleting: when the copy
        being replaced is destroyed, the new one must already be under the
        real name. Otherwise a fault in between leaves the key only under a
        scratch name that no picker shows."""
        self._write_existing()
        seen = {}

        real_delete = platform.secure_delete_file

        def watching_delete(path):
            if platform.file_exists(self.target):
                with open(self.target, "rb") as f:
                    seen[path] = f.read()
            else:
                seen[path] = None
            self.calls.append(("secure_delete", path))
            return self._real_delete(path)

        platform.secure_delete_file = watching_delete
        try:
            _run(self.ks.save_mnemonic())
        finally:
            platform.secure_delete_file = real_delete

        self.assertEqual(seen.get(self.old), b"enc:" + self.plaintext)

    def test_a_failed_overwrite_of_the_old_file_still_stores_the_key(self):
        """Once the swap is done the save has succeeded. A failure to
        retire the replaced copy is a residue problem worth reporting, but
        it must not cost the user the key they just saved."""
        self._write_existing()

        def failing_delete(path):
            self.calls.append(("secure_delete", path))
            raise OSError("simulated I/O failure")

        platform.secure_delete_file = failing_delete

        with self.assertRaises(KeyStoreError):
            _run(self.ks.save_mnemonic())

        self.assertEqual(self._read(self.target), b"enc:" + self.plaintext)

    def test_a_failed_swap_rolls_the_existing_key_back(self):
        self._write_existing()

        real_rename = os.rename
        state = {"n": 0}

        def failing_rename(src, dst):
            state["n"] += 1
            if state["n"] == 2:  # tmp -> target
                raise OSError("simulated rename failure")
            return real_rename(src, dst)

        os.rename = failing_rename
        try:
            with self.assertRaises(KeyStoreError):
                _run(self.ks.save_mnemonic())
        finally:
            os.rename = real_rename

        self.assertEqual(self._read(self.target), self.OLD)
        self.assertFalse(platform.file_exists(self.tmp))
        self.assertFalse(platform.file_exists(self.old))

    def test_an_interrupted_swap_restores_the_only_surviving_copy(self):
        """Power cut between the two renames: the target is gone and .old
        is the only copy of the key. It has to come back, not be discarded."""
        with open(self.old, "wb") as f:
            f.write(b"enc:interrupted-key")
        self.assertFalse(platform.file_exists(self.target))

        _run(self.ks.save_mnemonic())

        self.assertEqual(self._read(self.target), b"enc:" + self.plaintext)
        self.assertFalse(platform.file_exists(self.old))
        self.assertFalse(platform.file_exists(self.tmp))

    def test_a_stale_old_copy_is_retired_when_the_target_survived(self):
        """Power cut after the swap but before the overwrite: the target is
        current, so .old is stale and gets overwritten, not restored."""
        self._write_existing()
        with open(self.old, "wb") as f:
            f.write(b"enc:stale-replaced-key")

        _run(self.ks.save_mnemonic())

        self.assertIn(("secure_delete", self.old), self._kinds())
        self.assertEqual(self._read(self.target), b"enc:" + self.plaintext)
        self.assertFalse(platform.file_exists(self.old))

    def test_a_leftover_temp_file_is_overwritten_not_truncated(self):
        """A save interrupted after the temp write leaves an encrypted
        phrase behind under the temp name. Truncating over it would free
        those clusters unoverwritten - the very thing this avoids."""
        self._write_existing()
        with open(self.tmp, "wb") as f:
            f.write(b"enc:leftover-from-an-interrupted-save")

        _run(self.ks.save_mnemonic())

        self.assertEqual(self._kinds()[0], ("secure_delete", self.tmp))
        self.assertEqual(self._read(self.target), b"enc:" + self.plaintext)
        self.assertFalse(platform.file_exists(self.tmp))

    def test_the_scratch_names_are_not_listed_as_keys(self):
        """A leftover scratch file must not show up in the key menus as
        something loadable."""
        prefix = self.ks.fileprefix(self.ks.flashpath)
        for path in (self.tmp, self.old):
            name = path.rsplit("/", 1)[1]
            self.assertFalse(name.lower().startswith(prefix), name)


class FlashSaveMnemonicTest(_SaveMnemonicBase):
    keystore_cls = FlashKeyStore


class SDSaveMnemonicTest(_SaveMnemonicBase):
    """SDKeyStore.save_mnemonic() has its own copy of the overwrite prompt,
    with the SD unmount bookkeeping around it - the same guarantees have to
    hold there. The target here is the internal-flash path, so the card
    handling is not involved."""

    keystore_cls = SDKeyStore

    def setUp(self):
        super().setUp()

        async def get_keypath(*args, **kwargs):
            return self.ks.flashpath

        self.ks.get_keypath = get_keypath
