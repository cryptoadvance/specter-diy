"""Tests for the SD key-presence probe.

The probe must not retain a list proportional to the number of files on an
untrusted card, and a failed SD probe must not be reported as a found key.
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import os
from unittest import TestCase

import platform
from keystore.sdcard import SDKeyStore
from tests.util import clear_testdir


class _FakeCard:
    is_present = True

    def __init__(self, mount_error=None, unmount_error=None):
        self.mount_error = mount_error
        self.unmount_error = unmount_error
        self.mount_calls = 0
        self.unmount_calls = 0

    def mount(self):
        self.mount_calls += 1
        if self.mount_error is not None:
            raise self.mount_error

    def unmount(self):
        self.unmount_calls += 1
        if self.unmount_error is not None:
            raise self.unmount_error


class _Entries:
    def __init__(self, entries):
        self.entries = iter(entries)
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.closed:
            raise AssertionError("directory iterator used after close")
        return next(self.entries)

    def close(self):
        self.closed = True


class SDKeySavedTest(TestCase):
    def setUp(self):
        clear_testdir()
        platform.maybe_mkdir("testdir")
        self.ks = SDKeyStore()
        self.ks.path = "testdir"
        self.ks.secret = b"s" * 32
        self.sdpath = self.ks.sdpath
        self.real_card = platform.sdcard
        self.real_ilistdir = os.ilistdir

    def tearDown(self):
        platform.sdcard = self.real_card
        os.ilistdir = self.real_ilistdir
        clear_testdir()

    def test_sd_probe_streams_and_closes_after_first_match(self):
        card = _FakeCard()
        prefix = self.ks.fileprefix(self.sdpath)
        entries = _Entries([
            ("unrelated", 0x8000, 0, 0),
            (prefix + ".key", 0x8000, 0, 0),
        ])

        def ilistdir(path):
            if path == self.sdpath:
                return entries
            return iter([])

        platform.sdcard = card
        os.ilistdir = ilistdir

        self.assertTrue(self.ks.is_key_saved)
        self.assertTrue(entries.closed)
        self.assertEqual(card.mount_calls, 1)
        self.assertEqual(card.unmount_calls, 1)

    def test_mount_failure_falls_back_to_flash_status(self):
        platform.sdcard = _FakeCard(mount_error=OSError("mount failed"))
        os.ilistdir = lambda path: iter([])

        self.assertFalse(self.ks.is_key_saved)

    def test_directory_read_failure_falls_back_to_flash_status(self):
        card = _FakeCard()

        def ilistdir(path):
            if path == self.sdpath:
                raise OSError("directory read failed")
            return iter([])

        platform.sdcard = card
        os.ilistdir = ilistdir

        self.assertFalse(self.ks.is_key_saved)

    def test_sd_error_preserves_a_known_flash_key(self):
        prefix = self.ks.fileprefix(self.ks.flashpath)
        platform.sdcard = _FakeCard(unmount_error=OSError("unmount failed"))

        def ilistdir(path):
            if path == self.ks.flashpath:
                return iter([(prefix + ".key", 0x8000, 0, 0)])
            return iter([])

        os.ilistdir = ilistdir

        self.assertTrue(self.ks.is_key_saved)
