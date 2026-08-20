import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import os
from unittest import TestCase

import platform
import bitbox_sd as sd
from tests_native.bitbox_test_helpers import make_valid_backup_bytes, backup_id_for

ENTROPY_16 = bytes(range(16))
ENTROPY_16_B = bytes(range(1, 17))


class BitboxSdDiscoveryTestBase(TestCase):
    def setUp(self):
        self.root = sd._bitbox_root()
        self._cleanup()
        os.mkdir(self.root)

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        try:
            platform.delete_recursively(self.root, include_self=True)
        except Exception:
            pass

    def _make_dir(self, name):
        path = self.root + "/" + name
        try:
            os.mkdir(path)
        except OSError:
            pass
        return path

    def _write_file(self, dirpath, filename, data):
        with open(dirpath + "/" + filename, "wb") as f:
            f.write(bytes(data))

    def _write_valid_backup_dir(self, entropy=ENTROPY_16, num_files=3, **kwargs):
        dir_id = backup_id_for(entropy)
        dirpath = self._make_dir(dir_id)
        buf = make_valid_backup_bytes(entropy, **kwargs)
        for i in range(num_files):
            self._write_file(dirpath, "backup_%d.bin" % i, buf)
        return dir_id


class ListBackupDirsTest(BitboxSdDiscoveryTestBase):
    def test_one_valid_directory(self):
        dir_id = self._write_valid_backup_dir()
        self.assertEqual(sd.list_backup_dirs(), [dir_id])

    def test_multiple_valid_directories(self):
        id1 = self._write_valid_backup_dir(ENTROPY_16)
        id2 = self._write_valid_backup_dir(ENTROPY_16_B)
        self.assertEqual(sorted(sd.list_backup_dirs()), sorted([id1, id2]))

    def test_no_backups_when_bitbox_dir_missing(self):
        self._cleanup()  # remove the bitbox02 dir entirely
        self.assertEqual(sd.list_backup_dirs(), [])
        os.mkdir(self.root)  # restore for tearDown

    def test_no_valid_directories(self):
        self._make_dir("not_a_backup")
        self.assertEqual(sd.list_backup_dirs(), [])

    def test_dirname_too_short_ignored(self):
        self._make_dir("a" * 63)
        self.assertEqual(sd.list_backup_dirs(), [])

    def test_dirname_too_long_ignored(self):
        self._make_dir("a" * 65)
        self.assertEqual(sd.list_backup_dirs(), [])

    def test_dirname_non_hex_ignored(self):
        self._make_dir("g" * 64)
        self.assertEqual(sd.list_backup_dirs(), [])

    def test_dirname_uppercase_ignored(self):
        # BitBox always writes lowercase hex; Specter intentionally does
        # not case-fold, to avoid ambiguity on case-insensitive FAT.
        self._make_dir("A" * 64)
        self.assertEqual(sd.list_backup_dirs(), [])

    def test_regular_file_with_hex_name_ignored(self):
        # A plain *file* (not a directory) named like a valid backup id
        # must not be treated as a backup directory.
        with open(self.root + "/" + "a" * 64, "wb") as f:
            f.write(b"not a directory")
        self.assertEqual(sd.list_backup_dirs(), [])

    def test_huge_number_of_entries_rejected_not_enumerated_unbounded(self):
        # An adversarial card could put far more than a handful of entries
        # in bitbox02/ - listing must fail closed with a bounded amount of
        # work/memory, not silently enumerate everything.
        for i in range(sd.MAX_LIST_ENTRIES + 5):
            self._make_dir("junk_%d" % i)
        with self.assertRaises(sd.BitboxSdError):
            sd.list_backup_dirs()


class ReadBackupFilesTest(BitboxSdDiscoveryTestBase):
    def test_reads_three_files(self):
        dir_id = self._write_valid_backup_dir()
        files = sd.read_backup_files(dir_id)
        self.assertEqual(len(files), 3)
        self.assertTrue(all(isinstance(f, bytearray) for f in files))

    def test_path_traversal_rejected(self):
        for attempt in ["../etc", "..\\etc", "a" * 64 + "/../x", "/etc/passwd"]:
            with self.assertRaises(sd.BitboxSdError):
                sd.read_backup_files(attempt)

    def test_extra_file_in_directory_rejected(self):
        dir_id = self._write_valid_backup_dir(num_files=3)
        self._write_file(self.root + "/" + dir_id, "extra.bin", b"unexpected")
        with self.assertRaises(sd.BitboxSdError):
            sd.read_backup_files(dir_id)

    def test_wrong_file_extension_still_counted(self):
        # BitBox itself doesn't filter by extension/name - only file count,
        # size and format validity matter.
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self._make_dir(dir_id)
        buf = make_valid_backup_bytes(ENTROPY_16)
        self._write_file(dirpath, "a.dat", buf)
        self._write_file(dirpath, "b.weird_ext", buf)
        self._write_file(dirpath, "c", buf)
        files = sd.read_backup_files(dir_id)
        self.assertEqual(len(files), 3)

    def test_oversized_file_rejected(self):
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self._make_dir(dir_id)
        oversized = b"\x00" * (1024 + 1)
        for i in range(3):
            self._write_file(dirpath, "backup_%d.bin" % i, oversized)
        with self.assertRaises(sd.BitboxSdError):
            sd.read_backup_files(dir_id)

    def test_file_exactly_at_size_limit_accepted(self):
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self._make_dir(dir_id)
        exactly_limit = b"\x00" * 1024
        for i in range(3):
            self._write_file(dirpath, "backup_%d.bin" % i, exactly_limit)
        files = sd.read_backup_files(dir_id)
        self.assertEqual(len(files), 3)
        self.assertEqual(len(files[0]), 1024)

    def test_only_two_files_rejected(self):
        dir_id = self._write_valid_backup_dir(num_files=2)
        with self.assertRaises(sd.BitboxSdError):
            sd.read_backup_files(dir_id)

    def test_four_files_rejected(self):
        dir_id = self._write_valid_backup_dir(num_files=4)
        with self.assertRaises(sd.BitboxSdError):
            sd.read_backup_files(dir_id)

    def test_subdirectory_inside_backup_dir_rejected(self):
        dir_id = self._write_valid_backup_dir(num_files=2)
        os.mkdir(self.root + "/" + dir_id + "/subdir")
        with self.assertRaises(sd.BitboxSdError):
            sd.read_backup_files(dir_id)

    def test_read_error_during_one_copy(self):
        dir_id = self._write_valid_backup_dir(num_files=3)
        dirpath = self.root + "/" + dir_id
        # simulate an unreadable/broken file by replacing it with a
        # sub-directory of the same name after listing has already
        # committed to it being a file is hard to arrange portably; instead
        # verify that a file that vanishes between stat and read (TOCTOU)
        # is surfaced as an error rather than silently skipped.
        real_open = open

        def flaky_open(path, mode="r", *a, **kw):
            if path.endswith("backup_1.bin") and "r" in mode:
                raise OSError("simulated read failure")
            return real_open(path, mode, *a, **kw)

        import builtins

        builtins.open = flaky_open
        try:
            with self.assertRaises(sd.BitboxSdError):
                sd.read_backup_files(dir_id)
        finally:
            builtins.open = real_open

    def test_no_write_operations_performed(self):
        """Reading a backup directory must not modify any file on the
        card - verified by hashing every file before and after."""
        import hashlib

        dir_id = self._write_valid_backup_dir(num_files=3)
        dirpath = self.root + "/" + dir_id

        def hashes():
            result = {}
            for name in sorted(os.listdir(dirpath)):
                with open(dirpath + "/" + name, "rb") as f:
                    result[name] = hashlib.sha256(f.read()).hexdigest()
            return result

        before = hashes()
        sd.read_backup_files(dir_id)
        after = hashes()
        self.assertEqual(before, after)


class InvalidDirnameGuardTest(TestCase):
    def test_is_valid_backup_dirname(self):
        self.assertTrue(sd.is_valid_backup_dirname("a" * 64))
        self.assertFalse(sd.is_valid_backup_dirname("A" * 64))
        self.assertFalse(sd.is_valid_backup_dirname("a" * 63))
        self.assertFalse(sd.is_valid_backup_dirname("a" * 65))
        self.assertFalse(sd.is_valid_backup_dirname("g" * 64))
        self.assertFalse(sd.is_valid_backup_dirname("a" * 62 + "/."))
        self.assertFalse(sd.is_valid_backup_dirname("a" * 60 + "/etc"))
        self.assertFalse(sd.is_valid_backup_dirname(".."))
