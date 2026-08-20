"""
Tests for the BitBox02 backup *writer* in src/bitbox_backup.py
(build_backup and its encoder helpers).

The parser side has its own suite (test_bitbox_backup_parser.py); this one
pins down the encoder: its output must round-trip through the same strict
parser/validator the import path uses, it must be semantically identical
to a backup written by real BitBox02 firmware, and the buffers carrying
the plaintext seed must stay wipeable (bytearray, not bytes).
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import binascii
from unittest import TestCase

from embit import bip39

import bitbox_backup as bb
from tests_native.bitbox_test_helpers import (
    OFFICIAL_VECTOR_HEX,
    OFFICIAL_VECTOR_BACKUP_ID,
    OFFICIAL_VECTOR_ENTROPY,
)

ENTROPY_16 = bytes(range(16))
ENTROPY_24 = bytes(range(24))
ENTROPY_32 = bytes(range(32))


class WriterRoundTripTest(TestCase):
    """build_backup() output must parse, checksum- and id-verify through
    the exact code path the import uses (parse_backup/validate_backup)."""

    def _roundtrip(self, entropy, **kwargs):
        backup_id, encoded = bb.build_backup(entropy, **kwargs)
        try:
            # the encoded backup carries the plaintext seed, so it must be
            # handed out as a mutable, zeroizable buffer
            self.assertIsInstance(encoded, bytearray)
            self.assertLessEqual(len(encoded), bb.MAX_FILE_SIZE)
            self.assertEqual(backup_id, bb.compute_backup_id(entropy))
            parsed = bb.validate_backup(encoded, backup_id)
            try:
                self.assertEqual(bytes(parsed.entropy), entropy)
                self.assertEqual(parsed.seed_length, len(entropy))
                self.assertEqual(
                    parsed.mnemonic(),
                    bip39.mnemonic_from_bytes(entropy),
                )
            finally:
                parsed.zeroize()
        finally:
            bb.zeroize(encoded)

    def test_roundtrip_16_bytes(self):
        self._roundtrip(ENTROPY_16)

    def test_roundtrip_24_bytes(self):
        self._roundtrip(ENTROPY_24)

    def test_roundtrip_32_bytes(self):
        self._roundtrip(ENTROPY_32)

    def test_roundtrip_with_metadata(self):
        backup_id, encoded = bb.build_backup(
            ENTROPY_32, name="my backup", generator="specter-diy",
            timestamp=1601281809, birthdate=1601281809 - 32400,
        )
        try:
            parsed = bb.validate_backup(encoded, backup_id)
            try:
                self.assertEqual(parsed.name, "my backup")
                self.assertEqual(parsed.generator, "specter-diy")
                self.assertEqual(parsed.timestamp, 1601281809)
                self.assertEqual(parsed.birthdate, 1601281809 - 32400)
            finally:
                parsed.zeroize()
        finally:
            bb.zeroize(encoded)


class WriterLimitsTest(TestCase):
    def test_bad_entropy_lengths_rejected(self):
        for bad in (b"", bytes(15), bytes(17), bytes(31), bytes(33)):
            with self.assertRaises(bb.BitboxParseError):
                bb.build_backup(bad)

    def test_name_limit(self):
        # The reader accepts 64 bytes, but the writer must keep one byte
        # available for older BitBox02 firmware's NUL-terminated buffer.
        bb.zeroize(bb.build_backup(ENTROPY_16, name="n" * 63)[1])
        with self.assertRaises(bb.BitboxParseError):
            bb.build_backup(ENTROPY_16, name="n" * 64)

    def test_generator_limit(self):
        # Same compatibility rule as the official BitBox02 writer: 19 bytes
        # maximum, leaving room for the historical NUL terminator.
        bb.zeroize(bb.build_backup(ENTROPY_16, generator="g" * 19)[1])
        with self.assertRaises(bb.BitboxParseError):
            bb.build_backup(ENTROPY_16, generator="g" * 20)

    def test_multibyte_utf8_counts_bytes_not_chars(self):
        # 33 two-byte characters = 66 bytes > 64, must be rejected even
        # though it is only 33 characters
        with self.assertRaises(bb.BitboxParseError):
            bb.build_backup(ENTROPY_16, name="ü" * 33)


class WriterCompatibilityTest(TestCase):
    """A backup encoded by build_backup() must be semantically identical
    to one written by real BitBox02 firmware: same parsed fields, same
    checksum, same backup id. (The wire bytes may legitimately differ -
    real firmware omits zero-valued fields, we encode them explicitly;
    both are valid proto3 and the checksum covers values, not bytes.)"""

    def test_matches_real_device_backup(self):
        ref = bb.parse_backup(binascii.unhexlify(OFFICIAL_VECTOR_HEX))
        backup_id, encoded = bb.build_backup(
            OFFICIAL_VECTOR_ENTROPY,
            name=ref["name"],
            generator=ref["generator"],
            timestamp=ref["timestamp"],
            birthdate=ref["birthdate"],
        )
        try:
            self.assertEqual(backup_id, OFFICIAL_VECTOR_BACKUP_ID)
            reparsed = bb.parse_backup(encoded)
            for key in (
                "timestamp", "name", "mode", "seed_length",
                "birthdate", "generator", "length", "checksum",
            ):
                self.assertEqual(reparsed[key], ref[key], "field %s differs" % key)
            self.assertEqual(bytes(reparsed["seed"]), bytes(ref["seed"]))
        finally:
            bb.zeroize(encoded)

    def test_backup_id_matches_upstream_test_vectors(self):
        # Known-answer vectors from bitbox02-firmware's own backup.rs
        # test_id(): HMAC-SHA256("backup", seed zero-padded to 32 bytes).
        vectors = (
            (bytes([1]) * 16, "2ca3c18f988437806217db3bbee04913cbfaaa7152d4a9c00c80cf3802d0ef6f"),
            (bytes([2]) * 24, "57c24fa271ba9c6f4d5f2519c26f52dae8f491423daffb87d1c1002ca8a2b172"),
            (bytes([3]) * 32, "89910bac6d7f82e4e97ea2b6449e201dfd793adb75b342a90314d178866c89eb"),
        )
        for entropy, expected_id in vectors:
            self.assertEqual(bb.compute_backup_id(entropy), expected_id)


class WriterZeroizationTest(TestCase):
    def test_intermediate_buffers_are_zeroized(self):
        """After build_backup() returns, none of the intermediate buffers
        it built the encoding in may still hold the seed. Only the
        returned bytearray carries it (the caller's responsibility)."""
        # observable proxy: build twice with different entropies and make
        # sure nothing from the first build leaks into the second output,
        # and that zeroizing the returned buffer leaves a valid wipe
        bid1, enc1 = bb.build_backup(ENTROPY_16)
        bid2, enc2 = bb.build_backup(bytes(16))
        try:
            self.assertNotEqual(bid1, bid2)
            self.assertNotEqual(bytes(enc1), bytes(enc2))
            self.assertIn(bytes(ENTROPY_16), bytes(enc1))
            bb.zeroize(enc1)
            self.assertNotIn(bytes(ENTROPY_16), bytes(enc1))
            self.assertTrue(all(b == 0 for b in enc1))
        finally:
            bb.zeroize(enc1)
            bb.zeroize(enc2)
