"""Tests for the deliberately non-transactional mnemonic save model.

Replacing a saved mnemonic securely deletes the old file first and then
writes the new encrypted file. There is no .old/.tmp recovery protocol: a
power interruption may lose the local copy, so users need an independent
recovery backup.
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


class _FakePrompt:
    def __init__(self, *args, **kwargs):
        pass


class _SaveMnemonicBase(TestCase):
    keystore_cls = FlashKeyStore

    def setUp(self):
        clear_testdir()
        platform.maybe_mkdir("testdir")
        self.ks = self.keystore_cls()
        self.ks.path = "testdir"
        self.ks.pin = None
        self.ks.mnemonic = "ability " * 11 + "acid"
        self.ks.enc_secret = b"e" * 32
        self.target = "testdir/reckless.mykey"
        self.calls = []
        test = self

        async def get_input(*args, **kwargs):
            return "mykey"

        async def show(*args, **kwargs):
            return True

        async def load_mnemonic(path, *args, **kwargs):
            return None

        def save_aead(path, adata=b"", plaintext=b"", key=None, strict=False):
            test.calls.append(("save", path, strict))
            with open(path, "wb") as f:
                f.write(b"encrypted:" + plaintext)

        self.ks.get_input = get_input
        self.ks.show = show
        self.ks.load_mnemonic = load_mnemonic
        self.ks.save_aead = save_aead

        self._real_prompt = flash_module.Prompt
        self._real_sd_prompt = sdcard_module.Prompt
        flash_module.Prompt = _FakePrompt
        sdcard_module.Prompt = _FakePrompt
        self._real_delete = platform.secure_delete_file

        def secure_delete(path):
            test.calls.append(("delete", path))
            return test._real_delete(path)

        platform.secure_delete_file = secure_delete

    def tearDown(self):
        flash_module.Prompt = self._real_prompt
        sdcard_module.Prompt = self._real_sd_prompt
        platform.secure_delete_file = self._real_delete
        clear_testdir()

    def _write(self, path, data):
        with open(path, "wb") as f:
            f.write(data)

    def _read(self, path):
        with open(path, "rb") as f:
            return f.read()

    def test_new_mnemonic_is_saved_with_strict_sync(self):
        _run(self.ks.save_mnemonic())

        self.assertEqual(self.calls, [("save", self.target, True)])
        self.assertEqual(
            self._read(self.target),
            b"encrypted:" + self.ks.mnemonic.encode(),
        )

    def test_replacement_securely_deletes_before_writing(self):
        self._write(self.target, b"old encrypted mnemonic")

        _run(self.ks.save_mnemonic())

        self.assertEqual(
            self.calls,
            [("delete", self.target), ("save", self.target, True)],
        )
        self.assertEqual(
            self._read(self.target),
            b"encrypted:" + self.ks.mnemonic.encode(),
        )
        self.assertFalse(platform.file_exists("testdir/.reckless.mykey.old"))
        self.assertFalse(platform.file_exists("testdir/.reckless.mykey.tmp"))

    def test_replacement_delete_failure_is_reported_and_old_file_remains(self):
        self._write(self.target, b"old encrypted mnemonic")
        real_delete = platform.secure_delete_file

        def fail_delete(path):
            raise OSError("simulated delete failure")

        platform.secure_delete_file = fail_delete
        try:
            with self.assertRaises(KeyStoreError):
                _run(self.ks.save_mnemonic())
        finally:
            platform.secure_delete_file = real_delete

        self.assertEqual(self._read(self.target), b"old encrypted mnemonic")
        self.assertEqual([c[0] for c in self.calls], [])

    def test_save_failure_is_reported_after_old_file_was_deleted(self):
        self._write(self.target, b"old encrypted mnemonic")

        def fail_save(*args, **kwargs):
            self.calls.append(("save", args[0], kwargs.get("strict")))
            raise OSError("simulated save failure")

        self.ks.save_aead = fail_save
        with self.assertRaises(KeyStoreError):
            _run(self.ks.save_mnemonic())

        self.assertEqual(
            self.calls,
            [("delete", self.target), ("save", self.target, True)],
        )
        self.assertFalse(platform.file_exists(self.target))

    def test_corrupt_file_load_fails_without_recovery(self):
        self._write(self.target, b"not an encrypted mnemonic")

        def fail_load(*args, **kwargs):
            raise ValueError("invalid encrypted mnemonic")

        self.ks.load_aead = fail_load

        with self.assertRaises(Exception):
            loader = (SDKeyStore.load_mnemonic
                      if isinstance(self.ks, SDKeyStore)
                      else FlashKeyStore.load_mnemonic)
            _run(loader(self.ks, self.target))

        self.assertTrue(platform.file_exists(self.target))
        self.assertFalse(platform.file_exists("testdir/.reckless.mykey.old"))
        self.assertFalse(platform.file_exists("testdir/.reckless.mykey.tmp"))

    def test_dot_suffix_files_are_not_listed_as_keys_or_recovered(self):
        self._write("testdir/.reckless.mykey.old", b"old")
        self._write("testdir/.reckless.mykey.tmp", b"tmp")

        buttons = self.ks.load_files("testdir")

        self.assertEqual(buttons, [(None, "No files found")])
        self.assertTrue(platform.file_exists("testdir/.reckless.mykey.old"))
        self.assertTrue(platform.file_exists("testdir/.reckless.mykey.tmp"))


class FlashSaveMnemonicTest(_SaveMnemonicBase):
    keystore_cls = FlashKeyStore


class SDSaveMnemonicTest(_SaveMnemonicBase):
    keystore_cls = SDKeyStore

    def setUp(self):
        super().setUp()

        async def get_keypath(*args, **kwargs):
            return self.ks.flashpath

        self.ks.get_keypath = get_keypath
