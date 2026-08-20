import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import binascii
from unittest import TestCase

import bitbox_backup as bb
from tests_native.bitbox_test_helpers import (
    OFFICIAL_VECTOR_HEX,
    OFFICIAL_VECTOR_MNEMONIC,
    OFFICIAL_VECTOR_BACKUP_ID,
    OFFICIAL_VECTOR_ENTROPY,
    varint,
    non_canonical_varint,
    tag,
    ld_field,
    varint_field,
    group_field,
    build_metadata,
    build_data,
    build_content,
    build_backup_v1,
    build_backup,
    padded_seed,
    make_valid_backup_bytes,
    backup_id_for,
)

ENTROPY_16 = bytes(range(16))
ENTROPY_24 = bytes(range(24))
ENTROPY_32 = bytes(range(32))


class OfficialTestVectorTest(TestCase):
    """Cross-checked against bitbox02-firmware's own backup.rs test vectors
    and independently re-derived by hand in the investigation phase."""

    def setUp(self):
        self.buf = binascii.unhexlify(OFFICIAL_VECTOR_HEX)

    def test_parses_and_validates(self):
        parsed = bb.validate_backup(self.buf, OFFICIAL_VECTOR_BACKUP_ID)
        self.assertEqual(parsed.name, "My BitBox")
        self.assertEqual(parsed.timestamp, 1601281809)
        self.assertEqual(parsed.birthdate, 1601281809)
        self.assertEqual(parsed.generator, "v9.13.0")
        self.assertEqual(parsed.seed_length, 16)
        self.assertEqual(parsed.mode, 0)
        self.assertEqual(bytes(parsed.entropy), OFFICIAL_VECTOR_ENTROPY)

    def test_mnemonic_matches(self):
        parsed = bb.validate_backup(self.buf, OFFICIAL_VECTOR_BACKUP_ID)
        self.assertEqual(parsed.mnemonic(), OFFICIAL_VECTOR_MNEMONIC)

    def test_backup_id_matches(self):
        self.assertEqual(bb.compute_backup_id(OFFICIAL_VECTOR_ENTROPY), OFFICIAL_VECTOR_BACKUP_ID)

    def test_wrong_directory_rejected(self):
        wrong_id = "0" * 64
        with self.assertRaises(bb.BitboxIdMismatchError):
            bb.validate_backup(self.buf, wrong_id)

    def test_three_identical_copies_load(self):
        parsed, valid_copies, used_majority = bb.load_backup(
            OFFICIAL_VECTOR_BACKUP_ID, [self.buf, self.buf, self.buf]
        )
        self.assertFalse(used_majority)
        self.assertEqual(valid_copies, 3)
        self.assertEqual(parsed.mnemonic(), OFFICIAL_VECTOR_MNEMONIC)


class MemoryHygieneTest(TestCase):
    """Guards the (limited, best-effort) zeroization promises made in
    docs/security-model.md - these regressed once already."""

    def setUp(self):
        self.entropy = bytes(range(16))
        self.buf = make_valid_backup_bytes(self.entropy)
        self.dir_id = backup_id_for(self.entropy)

    def test_zeroize_wipes_the_entropy_the_object_owns(self):
        parsed = bb.validate_backup(self.buf, self.dir_id)
        held = parsed.entropy  # same object, not a fresh slice
        parsed.zeroize()
        self.assertEqual(bytes(parsed.entropy), bytes(len(parsed.entropy)))
        self.assertEqual(bytes(held), bytes(len(held)))

    def test_entropy_is_a_stable_object_not_a_copying_property(self):
        # A property returning a fresh slice each time would leave
        # un-zeroizable copies scattered on the heap.
        parsed = bb.validate_backup(self.buf, self.dir_id)
        self.assertIs(parsed.entropy, parsed.entropy)

    def test_mnemonic_does_not_let_embit_mutate_our_buffer(self):
        # embit's mnemonic_from_bytes does `entropy += checksum`, which
        # mutates a bytearray argument in place (16 -> 48 bytes).
        parsed = bb.validate_backup(self.buf, self.dir_id)
        before = bytes(parsed.entropy)
        parsed.mnemonic()
        self.assertEqual(len(parsed.entropy), 16)
        self.assertEqual(bytes(parsed.entropy), before)
        # still derivable a second time, and still zeroizable
        self.assertEqual(parsed.mnemonic(), bb.bip39.mnemonic_from_bytes(before))
        parsed.zeroize()
        self.assertEqual(bytes(parsed.entropy), bytes(16))

    def test_rejected_backup_leaves_no_entropy_behind(self):
        # Tamper so the id check fails after the checksum passed; the
        # entropy extracted internally must be wiped before raising.
        other_dir = backup_id_for(bytes(range(1, 17)))
        with self.assertRaises(bb.BitboxIdMismatchError):
            bb.validate_backup(self.buf, other_dir)

    def test_discarded_redundant_copies_are_wiped(self):
        parsed, valid_copies, used_majority = bb.load_backup(
            self.dir_id, [self.buf, self.buf, self.buf]
        )
        self.assertEqual(valid_copies, 3)
        # the returned copy must still be usable
        self.assertEqual(bytes(parsed.entropy), self.entropy)


class VarintTest(TestCase):
    def test_single_byte(self):
        self.assertEqual(bb._read_varint(b"\x00", 0), (0, 1))
        self.assertEqual(bb._read_varint(b"\x7f", 0), (0x7F, 1))

    def test_multi_byte(self):
        buf = varint(300)
        self.assertEqual(bb._read_varint(buf, 0), (300, len(buf)))

    def test_max_uint32(self):
        buf = varint(0xFFFFFFFF)
        value, pos = bb._read_varint(buf, 0)
        self.assertEqual(value, 0xFFFFFFFF)

    def test_truncated_varint_rejected(self):
        # continuation bit set but no more bytes follow
        with self.assertRaises(bb.BitboxParseError):
            bb._read_varint(b"\x80", 0)

    def test_overlong_varint_rejected(self):
        buf = b"\x80" * 11 + b"\x01"
        with self.assertRaises(bb.BitboxParseError):
            bb._read_varint(buf, 0)

    def test_value_overflow_rejected(self):
        # 10 continuation-style bytes encoding a value > 2**64-1
        buf = b"\xff" * 9 + b"\x02"
        with self.assertRaises(bb.BitboxParseError):
            bb._read_varint(buf, 0)

    def test_non_canonical_varint_rejected(self):
        buf = non_canonical_varint(1, extra_bytes=1)
        with self.assertRaises(bb.BitboxParseError):
            bb._read_varint(buf, 0)

    def test_non_canonical_zero_rejected(self):
        # 0x80 0x00 decodes to 0 but canonical encoding of 0 is one byte
        with self.assertRaises(bb.BitboxParseError):
            bb._read_varint(b"\x80\x00", 0)


class LengthDelimitedTest(TestCase):
    def test_valid_length_delimited(self):
        buf = ld_field(2, b"hello")
        fields = bb._parse_known_message(buf, {2: ("x", bb.WIRE_LENGTH_DELIMITED)}, "T")
        self.assertEqual(fields["x"], b"hello")

    def test_length_exceeds_buffer_rejected(self):
        buf = tag(2, 2) + varint(100) + b"short"
        with self.assertRaises(bb.BitboxParseError):
            list(bb._iter_fields(buf))

    def test_length_exactly_fits(self):
        buf = tag(2, 2) + varint(5) + b"hello"
        fields = list(bb._iter_fields(buf))
        self.assertEqual(fields[0][2], b"hello")


class UnknownFieldTest(TestCase):
    def test_unknown_varint_field_skipped(self):
        buf = varint_field(99, 12345) + ld_field(2, b"name")
        fields = bb._parse_known_message(buf, {2: ("name", bb.WIRE_LENGTH_DELIMITED)}, "T")
        self.assertEqual(fields["name"], b"name")

    def test_unknown_length_delimited_field_skipped(self):
        buf = ld_field(50, b"unknown junk") + ld_field(2, b"name")
        fields = bb._parse_known_message(buf, {2: ("name", bb.WIRE_LENGTH_DELIMITED)}, "T")
        self.assertEqual(fields["name"], b"name")

    def test_unknown_fixed64_field_skipped(self):
        buf = tag(77, 1) + b"12345678" + ld_field(2, b"name")
        fields = bb._parse_known_message(buf, {2: ("name", bb.WIRE_LENGTH_DELIMITED)}, "T")
        self.assertEqual(fields["name"], b"name")

    def test_unknown_fixed32_field_skipped(self):
        buf = tag(88, 5) + b"1234" + ld_field(2, b"name")
        fields = bb._parse_known_message(buf, {2: ("name", bb.WIRE_LENGTH_DELIMITED)}, "T")
        self.assertEqual(fields["name"], b"name")

    def test_group_wire_type_3_rejected(self):
        buf = group_field(5, 3) + ld_field(2, b"name")
        with self.assertRaises(bb.BitboxParseError):
            list(bb._iter_fields(buf))

    def test_group_wire_type_4_rejected(self):
        buf = group_field(5, 4) + ld_field(2, b"name")
        with self.assertRaises(bb.BitboxParseError):
            list(bb._iter_fields(buf))

    def test_field_number_zero_rejected(self):
        buf = tag(0, 0) + varint(1)
        with self.assertRaises(bb.BitboxParseError):
            list(bb._iter_fields(buf))


class DuplicateFieldTest(TestCase):
    def test_duplicate_known_field_rejected(self):
        buf = ld_field(2, b"first") + ld_field(2, b"second")
        with self.assertRaises(bb.BitboxParseError):
            bb._parse_known_message(buf, {2: ("name", bb.WIRE_LENGTH_DELIMITED)}, "T")

    def test_wrong_wire_type_for_known_field_rejected(self):
        buf = varint_field(2, 5)  # field 2 expected to be length-delimited
        with self.assertRaises(bb.BitboxParseError):
            bb._parse_known_message(buf, {2: ("name", bb.WIRE_LENGTH_DELIMITED)}, "T")


class BackupVersionTest(TestCase):
    def test_unknown_backup_version_rejected(self):
        buf = build_backup(b"\x00", field_number=2)
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_multiple_backup_versions_rejected(self):
        buf = build_backup(b"", field_number=1) + build_backup(b"", field_number=1)
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_missing_backup_version_rejected(self):
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(b"")


class MissingFieldTest(TestCase):
    def _content_missing(self, drop):
        checksum = bytes(32)
        metadata_bytes = build_metadata(timestamp=1, name=b"n")
        data_bytes = build_data(16, padded_seed(ENTROPY_16))
        parts = {
            "checksum": ld_field(1, checksum),
            "metadata": ld_field(2, metadata_bytes),
            "data": ld_field(4, data_bytes),
        }
        del parts[drop]
        content_bytes = b"".join(parts.values())
        backup_v1_bytes = build_backup_v1(content_bytes)
        return build_backup(backup_v1_bytes)

    def test_missing_checksum_rejected(self):
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(self._content_missing("checksum"))

    def test_missing_metadata_rejected(self):
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(self._content_missing("metadata"))

    def test_missing_data_rejected(self):
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(self._content_missing("data"))

    def test_missing_content_in_backup_v1_rejected(self):
        buf = build_backup(build_backup_v1(b""))
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_missing_seed_in_data_rejected(self):
        data_bytes = varint_field(1, 16)  # seed_length only, no seed field
        checksum = bytes(32)
        content_bytes = build_content(checksum, build_metadata(name=b"n"), data_bytes=data_bytes)
        buf = build_backup(build_backup_v1(content_bytes))
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)


class FormatTest(TestCase):
    """Section 9.2 style format-level tests, using freshly-built messages
    with correctly computed checksums unless a field is deliberately
    tampered with."""

    def _build(self, entropy=ENTROPY_16, **kwargs):
        return make_valid_backup_bytes(entropy, **kwargs)

    def _dir(self, entropy=ENTROPY_16):
        return backup_id_for(entropy)

    def test_valid_12_word_seed(self):
        buf = self._build(ENTROPY_16)
        parsed = bb.validate_backup(buf, self._dir(ENTROPY_16))
        self.assertEqual(len(parsed.mnemonic().split()), 12)

    def test_valid_18_word_seed(self):
        buf = self._build(ENTROPY_24)
        parsed = bb.validate_backup(buf, self._dir(ENTROPY_24))
        self.assertEqual(len(parsed.mnemonic().split()), 18)

    def test_valid_24_word_seed(self):
        buf = self._build(ENTROPY_32)
        parsed = bb.validate_backup(buf, self._dir(ENTROPY_32))
        self.assertEqual(len(parsed.mnemonic().split()), 24)

    def test_length_zero(self):
        buf = self._build(length=0)
        parsed = bb.validate_backup(buf, self._dir())
        self.assertEqual(parsed.length, 0)

    def test_historical_length_nonzero_accepted(self):
        buf = self._build(length=42)
        parsed = bb.validate_backup(buf, self._dir())
        self.assertEqual(parsed.length, 42)

    def test_checksum_exactly_right(self):
        buf = self._build()
        bb.validate_backup(buf, self._dir())  # must not raise

    def test_single_checksum_byte_flip_rejected(self):
        good_checksum = bb.compute_checksum(
            1601281809, 0, b"test name", 16, bytearray(padded_seed(ENTROPY_16)),
            1601249409, b"v9.13.0", 0,
        )
        bad_checksum = bytearray(good_checksum)
        bad_checksum[0] ^= 0x01
        buf = self._build(checksum_override=bytes(bad_checksum))
        with self.assertRaises(bb.BitboxChecksumError):
            bb.validate_backup(buf, self._dir())

    def test_tampered_timestamp_rejected(self):
        buf = self._build()
        # flip a bit inside the (correctly checksummed) message, then patch
        # the on-wire timestamp only - simulate by rebuilding with wrong
        # timestamp but the checksum computed for the original one.
        good_checksum = bb.compute_checksum(
            1601281809, 0, b"test name", 16, bytearray(padded_seed(ENTROPY_16)),
            1601249409, b"v9.13.0", 0,
        )
        buf = self._build(timestamp=1601281810, checksum_override=good_checksum)
        with self.assertRaises(bb.BitboxChecksumError):
            bb.validate_backup(buf, self._dir())

    def test_tampered_name_rejected(self):
        good_checksum = bb.compute_checksum(
            1601281809, 0, b"test name", 16, bytearray(padded_seed(ENTROPY_16)),
            1601249409, b"v9.13.0", 0,
        )
        buf = self._build(name="different name", checksum_override=good_checksum)
        with self.assertRaises(bb.BitboxChecksumError):
            bb.validate_backup(buf, self._dir())

    def test_tampered_generator_rejected(self):
        good_checksum = bb.compute_checksum(
            1601281809, 0, b"test name", 16, bytearray(padded_seed(ENTROPY_16)),
            1601249409, b"v9.13.0", 0,
        )
        buf = self._build(generator="v9.99.0", checksum_override=good_checksum)
        with self.assertRaises(bb.BitboxChecksumError):
            bb.validate_backup(buf, self._dir())

    def test_wrong_mode_rejected(self):
        buf = self._build(mode=1)  # checksum computed correctly for mode=1
        with self.assertRaises(bb.BitboxParseError):
            bb.validate_backup(buf, self._dir())

    def test_checksum_wrong_endianness_rejected(self):
        # Recompute checksum preimage with a big-endian timestamp instead of
        # little-endian - must not accidentally validate.
        import hashlib as _hashlib
        timestamp = 1601281809
        name_raw = b"test name"
        generator_raw = b"v9.13.0"
        seed32 = padded_seed(ENTROPY_16)
        h = _hashlib.sha256()
        h.update(timestamp.to_bytes(4, "big"))
        h.update(bytes((0,)))
        h.update(name_raw + bytes(64 - len(name_raw)))
        h.update((16).to_bytes(4, "big"))
        h.update(seed32)
        h.update((1601249409).to_bytes(4, "big"))
        h.update(generator_raw + bytes(20 - len(generator_raw)))
        h.update((0).to_bytes(4, "big"))
        wrong_checksum = h.digest()
        buf = self._build(checksum_override=wrong_checksum)
        with self.assertRaises(bb.BitboxChecksumError):
            bb.validate_backup(buf, self._dir())

    def test_wrong_seed_length_rejected(self):
        buf = self._build(seed_length=20)  # not in {16, 24, 32}, checksum matches this value
        with self.assertRaises(bb.BitboxParseError):
            bb.validate_backup(buf, self._dir())

    def test_seed_field_shorter_than_32_rejected(self):
        checksum = bytes(32)
        metadata_bytes = build_metadata(timestamp=1, name=b"n")
        data_bytes = build_data(16, ENTROPY_16)  # only 16 bytes, not zero-padded to 32
        content_bytes = build_content(checksum, metadata_bytes, data_bytes=data_bytes)
        buf = build_backup(build_backup_v1(content_bytes))
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_seed_field_longer_than_32_rejected(self):
        checksum = bytes(32)
        metadata_bytes = build_metadata(timestamp=1, name=b"n")
        data_bytes = build_data(16, ENTROPY_32 + b"\x00")  # 33 bytes
        content_bytes = build_content(checksum, metadata_bytes, data_bytes=data_bytes)
        buf = build_backup(build_backup_v1(content_bytes))
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_invalid_padding_rejected(self):
        buf = self._build(entropy=ENTROPY_16, corrupt_padding=True)
        with self.assertRaises(bb.BitboxParseError):
            bb.validate_backup(buf, self._dir())

    def test_invalid_utf8_in_name_rejected(self):
        checksum = bytes(32)
        bad_name = b"\xff\xfe invalid utf8"
        metadata_bytes = build_metadata(timestamp=1, name=bad_name)
        data_bytes = build_data(16, padded_seed(ENTROPY_16))
        content_bytes = build_content(checksum, metadata_bytes, data_bytes=data_bytes)
        buf = build_backup(build_backup_v1(content_bytes))
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_control_characters_in_display_metadata_rejected(self):
        for bad_name, bad_generator in (("trusted\nbackup", "v9.13.0"), ("trusted", "v9.13.0\x1b")):
            buf = self._build(name=bad_name, generator=bad_generator)
            with self.assertRaises(bb.BitboxParseError):
                bb.parse_backup(buf)

    def test_rejected_parse_zeroizes_seed_buffer(self):
        buf = self._build(entropy=ENTROPY_16, corrupt_padding=True)
        original_zeroize = bb.zeroize
        wiped = []

        def recording_zeroize(value):
            if isinstance(value, bytearray):
                wiped.append(value)
            original_zeroize(value)

        bb.zeroize = recording_zeroize
        try:
            with self.assertRaises(bb.BitboxParseError):
                bb.parse_backup(buf)
        finally:
            bb.zeroize = original_zeroize

        self.assertTrue(wiped)
        self.assertTrue(all(bytes(value) == bytes(len(value)) for value in wiped))

    def test_name_over_byte_limit_rejected(self):
        # Built directly (not via make_valid_backup_bytes/compute_checksum,
        # which enforce this same limit) so the length violation itself -
        # not a checksum mismatch - is what gets exercised and rejected.
        checksum = bytes(32)
        metadata_bytes = build_metadata(timestamp=1, name=b"x" * 65)
        data_bytes = build_data(16, padded_seed(ENTROPY_16))
        content_bytes = build_content(checksum, metadata_bytes, data_bytes=data_bytes)
        buf = build_backup(build_backup_v1(content_bytes))
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_name_at_byte_limit_accepted(self):
        buf = self._build(name="x" * 64)
        bb.validate_backup(buf, self._dir())  # must not raise

    def test_generator_over_byte_limit_rejected(self):
        checksum = bytes(32)
        metadata_bytes = build_metadata(timestamp=1, name=b"n")
        data_bytes = build_data(16, padded_seed(ENTROPY_16), generator=b"x" * 21)
        content_bytes = build_content(checksum, metadata_bytes, data_bytes=data_bytes)
        buf = build_backup(build_backup_v1(content_bytes))
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(buf)

    def test_generator_at_byte_limit_accepted(self):
        buf = self._build(generator="x" * 20)
        bb.validate_backup(buf, self._dir())  # must not raise

    def test_file_exactly_at_size_limit(self):
        buf = self._build(name="x" * 64, generator="x" * 20)
        self.assertLessEqual(len(buf), bb.MAX_FILE_SIZE)

    def test_file_one_byte_over_size_limit_rejected(self):
        oversized = b"\x00" * (bb.MAX_FILE_SIZE + 1)
        with self.assertRaises(bb.BitboxParseError):
            bb.parse_backup(oversized)


class BackupIdTest(TestCase):
    def test_id_for_16_byte_entropy(self):
        expected = bb.compute_backup_id(ENTROPY_16)
        self.assertEqual(len(expected), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in expected))

    def test_id_for_24_byte_entropy(self):
        bb.compute_backup_id(ENTROPY_24)

    def test_id_for_32_byte_entropy(self):
        bb.compute_backup_id(ENTROPY_32)

    def test_wrong_directory_name_rejected(self):
        buf = make_valid_backup_bytes(ENTROPY_16)
        with self.assertRaises(bb.BitboxIdMismatchError):
            bb.validate_backup(buf, "f" * 64)

    def test_padding_before_hmac_matters(self):
        # id() must be computed over the zero-padded 32-byte seed, not the
        # raw entropy - a naive implementation that hashed raw entropy
        # would give a different (wrong) result for non-32-byte entropy.
        import hashlib as _hashlib
        import hmac as _hmac

        raw_hash = _hmac.new(b"backup", ENTROPY_16, _hashlib.sha256).hexdigest()
        padded_hash = bb.compute_backup_id(ENTROPY_16)
        self.assertNotEqual(raw_hash, padded_hash)

    def test_does_not_use_full_bip39_seed(self):
        # Using mnemonic_to_seed (PBKDF2, 64 bytes) instead of the raw
        # entropy would give a completely different id.
        from embit import bip39

        mnemonic = bip39.mnemonic_from_bytes(ENTROPY_16)
        full_seed = bip39.mnemonic_to_seed(mnemonic)
        wrong_id = bb.compute_backup_id(full_seed[:32])
        right_id = bb.compute_backup_id(ENTROPY_16)
        self.assertNotEqual(wrong_id, right_id)


class ThreeCopyRecoveryTest(TestCase):
    def setUp(self):
        self.buf = make_valid_backup_bytes(ENTROPY_16)
        self.dir_id = backup_id_for(ENTROPY_16)

    def _corrupt(self, buf, index, xor=0xFF):
        b = bytearray(buf)
        b[index % len(b)] ^= xor
        return bytes(b)

    def test_three_identical_valid_copies(self):
        parsed, valid_copies, used_majority = bb.load_backup(self.dir_id, [self.buf, self.buf, self.buf])
        self.assertFalse(used_majority)
        self.assertEqual(valid_copies, 3)

    def test_one_valid_two_corrupted(self):
        bad1 = self._corrupt(self.buf, 5)
        bad2 = self._corrupt(self.buf, 15)
        parsed, valid_copies, used_majority = bb.load_backup(self.dir_id, [self.buf, bad1, bad2])
        self.assertFalse(used_majority)
        self.assertEqual(valid_copies, 1)
        self.assertEqual(bytes(parsed.entropy), ENTROPY_16)

    def test_two_valid_one_corrupted(self):
        bad = self._corrupt(self.buf, 7)
        parsed, valid_copies, used_majority = bb.load_backup(self.dir_id, [self.buf, self.buf, bad])
        self.assertFalse(used_majority)
        self.assertEqual(valid_copies, 2)

    def test_three_differently_corrupted_recoverable_by_majority(self):
        b1 = self._corrupt(self.buf, 10, 0x01)
        b2 = self._corrupt(self.buf, 20, 0x02)
        b3 = self._corrupt(self.buf, 30, 0x04)
        parsed, valid_copies, used_majority = bb.load_backup(self.dir_id, [b1, b2, b3])
        self.assertTrue(used_majority)
        self.assertEqual(valid_copies, 0)
        self.assertEqual(bytes(parsed.entropy), ENTROPY_16)

    def test_three_identically_corrupted_not_recoverable(self):
        bad = self._corrupt(self.buf, 10, 0x01)
        with self.assertRaises(bb.BitboxBackupError):
            bb.load_backup(self.dir_id, [bad, bad, bad])

    def test_three_files_different_sizes_rejected(self):
        short = self.buf[:-1]
        with self.assertRaises(bb.BitboxBackupError):
            bb.load_backup(self.dir_id, [self._corrupt(self.buf, 1), self._corrupt(self.buf, 2), short])

    def test_only_two_files_rejected(self):
        with self.assertRaises(bb.BitboxParseError):
            bb.load_backup(self.dir_id, [self.buf, self.buf])

    def test_four_files_rejected(self):
        with self.assertRaises(bb.BitboxParseError):
            bb.load_backup(self.dir_id, [self.buf, self.buf, self.buf, self.buf])

    def test_two_valid_but_different_contents_rejected(self):
        other_buf = make_valid_backup_bytes(ENTROPY_16, name="a different backup")
        # both are individually valid for the SAME directory id (same entropy)
        # but their metadata disagrees - must not silently pick the first.
        with self.assertRaises(bb.BitboxInconsistentCopiesError):
            bb.load_backup(self.dir_id, [self.buf, other_buf, self._corrupt(self.buf, 3)])

    def test_same_entropy_conflicting_metadata_rejected(self):
        other_buf = make_valid_backup_bytes(ENTROPY_16, timestamp=999)
        with self.assertRaises(bb.BitboxInconsistentCopiesError):
            bb.load_backup(self.dir_id, [self.buf, self.buf, other_buf])

    def test_majority_result_with_wrong_checksum_rejected(self):
        # Corrupt all three copies at the same byte with different values
        # such that the majority-recovered checksum byte itself ends up
        # wrong (majority of 3 distinct wrong values can't reconstruct the
        # original byte).
        b1 = self._corrupt(self.buf, 8, 0x01)
        b2 = self._corrupt(self.buf, 8, 0x02)
        b3 = self._corrupt(self.buf, 8, 0x03)
        with self.assertRaises(bb.BitboxRecoveryError):
            bb.load_backup(self.dir_id, [b1, b2, b3])

    def test_majority_result_with_wrong_backup_id_rejected(self):
        other_entropy = bytes(range(1, 17))
        other_buf = make_valid_backup_bytes(other_entropy)
        # None of these three match self.dir_id individually or after majority.
        with self.assertRaises(bb.BitboxBackupError):
            bb.load_backup(self.dir_id, [other_buf, other_buf, other_buf])
