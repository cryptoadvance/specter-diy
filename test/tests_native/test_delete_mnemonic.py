"""
Regression tests: delete_mnemonic() must not swallow deletion failures.

Both FlashKeyStore.delete_mnemonic() and SDKeyStore.delete_mnemonic() had
their `return True` inside the `finally` block of the delete path. A
return inside finally executes while the KeyStoreError raised in the
except block is propagating - and silently discards it. The UI therefore
reported "Your key is deleted." even when the deletion had failed and
the file was still sitting on the internal flash or the SD card.

These tests fail against the old structure (the exception never reaches
the caller) and pass with the fix (success return moved out of finally).
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import os
from unittest import TestCase

import platform
from keystore.core import KeyStoreError
from keystore.flash import FlashKeyStore
from keystore.sdcard import SDKeyStore
from tests.util import clear_testdir


def _run(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _DeleteMnemonicBase(TestCase):
    keystore_cls = None

    def _target_path(self):
        raise NotImplementedError

    def setUp(self):
        clear_testdir()
        platform.maybe_mkdir("testdir")
        self.ks = self.keystore_cls()
        self.target = self._target_path()
        with open(self.target, "wb") as f:
            f.write(b"encrypted-key-material")

        async def fake_select_file():
            return self.target

        self.ks.select_file = fake_select_file

    def tearDown(self):
        if platform.file_exists(self.target):
            os.remove(self.target)
        clear_testdir()

    def test_failed_delete_raises_instead_of_reporting_success(self):
        # Patch platform.secure_delete_file (what delete_mnemonic actually
        # calls) to simulate an I/O failure during the overwrite.
        real_fn = platform.secure_delete_file
        calls = []

        def failing_delete(path, passes=3):
            calls.append(path)
            raise OSError("simulated I/O failure")

        platform.secure_delete_file = failing_delete
        try:
            with self.assertRaises(KeyStoreError):
                _run(self.ks.delete_mnemonic())
        finally:
            platform.secure_delete_file = real_fn
        self.assertEqual(calls, [self.target])
        # the file must provably still be there
        self.assertTrue(platform.file_exists(self.target))

    def test_successful_delete_returns_true_and_removes_file(self):
        res = _run(self.ks.delete_mnemonic())
        self.assertIs(res, True)
        self.assertFalse(platform.file_exists(self.target))

    def test_cancelled_selection_returns_false(self):
        async def cancel_select_file():
            return None

        self.ks.select_file = cancel_select_file
        res = _run(self.ks.delete_mnemonic())
        self.assertIs(res, False)
        self.assertTrue(platform.file_exists(self.target))


class FlashDeleteMnemonicTest(_DeleteMnemonicBase):
    keystore_cls = FlashKeyStore

    def _target_path(self):
        return "testdir/reckless.mykey"


class SDDeleteMnemonicTest(_DeleteMnemonicBase):
    keystore_cls = SDKeyStore

    def _target_path(self):
        return "testdir/specterdiaaaa.mykey"