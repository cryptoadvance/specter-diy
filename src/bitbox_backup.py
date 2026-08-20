"""
Parser and validator for native BitBox02 microSD backup files.

The on-disk format (a small, fixed protobuf schema) is defined by BitBoxSwiss'
bitbox02-firmware project, see ``messages/backup.proto`` and
``src/rust/bitbox02-rust/src/backup.rs`` at
https://github.com/BitBoxSwiss/bitbox02-firmware (Apache-2.0,
SPDX-License-Identifier: Apache-2.0). No code from that project is copied
here - this is an independent, from-scratch reimplementation of the wire
format for Specter-DIY, restricted to exactly the messages/fields defined in
backup.proto:

    message BackupMetaData { uint32 timestamp=1; string name=2; BackupMode mode=3; }
    message BackupData     { uint32 seed_length=1; bytes seed=2; uint32 birthdate=3; string generator=4; }
    message BackupContent  { bytes checksum=1; BackupMetaData metadata=2; uint32 length=3; bytes data=4; }
    message BackupV1       { BackupContent content=1; }
    message Backup         { oneof backup_version { BackupV1 backup_v1=1; } }

This is deliberately NOT a general-purpose protobuf implementation: it only
understands this one schema, has no recursion, and enforces strict limits at
every step (see MAX_FILE_SIZE and the various *_MAX_BYTES constants below).
Unknown fields are only ever skipped for the wire types that can be skipped
safely (varint, 64-bit, length-delimited, 32-bit); protobuf "groups" (wire
types 3/4) are always rejected outright, wherever they appear.

Security note: the BitBox microSD backup format is NOT encrypted (mode is
always PLAINTEXT) and the checksum in the file is a corruption check, not an
authentication tag - anyone able to read the SD card can read the wallet's
BIP-39 entropy directly. See docs/security-model.md for details.
"""
import hashlib
import hmac
from binascii import hexlify, unhexlify

from embit import bip39


# ---------------------------------------------------------------------------
# Errors
#
# Error messages must never contain secret material (entropy, mnemonic words,
# raw file bytes, checksums derived from secrets). They may name the field or
# check that failed, but never its value.
# ---------------------------------------------------------------------------

class BitboxBackupError(Exception):
    """Base class for all BitBox backup parsing/validation errors."""


class BitboxParseError(BitboxBackupError):
    """The data is not a well-formed, canonical BitBox backup message, or it
    fails one of the format's structural/semantic invariants (mode, seed
    length, padding, string limits, ...)."""


class BitboxChecksumError(BitboxBackupError):
    """The message parsed correctly but its checksum does not match."""


class BitboxIdMismatchError(BitboxBackupError):
    """The message parsed and checksum-verified correctly, but the seed does
    not hash to the directory name it was loaded from."""


class BitboxInconsistentCopiesError(BitboxBackupError):
    """More than one of the (up to three) backup copies is individually
    valid, but they do not all agree with each other."""


class BitboxRecoveryError(BitboxBackupError):
    """Bitwise-majority recovery was not possible, or did not yield a valid
    backup."""


# ---------------------------------------------------------------------------
# Format constants (see messages/backup.proto and backup.rs / sd.h upstream)
# ---------------------------------------------------------------------------

# SD_MAX_FILE_SIZE in bitbox02-firmware/src/sd.h
MAX_FILE_SIZE = 1024
# Size of the zero-padded `name` buffer in the checksum preimage.
NAME_MAX_BYTES = 64
# Size of the zero-padded `generator` buffer in the checksum preimage.
GENERATOR_MAX_BYTES = 20
# The official writer keeps one byte available for the historical C
# nanopb NUL terminator. Keep the reader liberal, but make backups emitted by
# Specter restoreable by older BitBox02 firmware as well.
WRITER_NAME_MAX_BYTES = 63
WRITER_GENERATOR_MAX_BYTES = 19
# The `seed` field is always exactly 32 bytes (zero padded on the right),
# regardless of the actual entropy length.
SEED_FIELD_SIZE = 32
# Valid BIP-39 entropy lengths: 12, 18 and 24 word mnemonics.
VALID_SEED_LENGTHS = (16, 24, 32)
# The only backup mode ever defined so far.
BACKUP_MODE_PLAINTEXT = 0
# SHA-256 output size; the stored checksum must be exactly this long.
SHA256_SIZE = 32

# protobuf varints never need more than 10 bytes to encode a 64-bit value.
_MAX_VARINT_BYTES = 10
_U64_MAX = (1 << 64) - 1
_U32_MAX = (1 << 32) - 1

WIRE_VARINT = 0
WIRE_64BIT = 1
WIRE_LENGTH_DELIMITED = 2
WIRE_32BIT = 5


def zeroize(buf):
    """Best-effort in-place zeroization of a mutable buffer (bytearray).

    Pure Python cannot guarantee secret material is wiped from memory -
    the garbage collector, string interning, and the underlying
    (Micro)Python runtime may still leave copies elsewhere. This only
    overwrites the one buffer we have a direct, mutable handle to.
    Immutable `bytes`/`str` values (e.g. the final mnemonic string) cannot
    be zeroized in pure Python at all; this is a known, documented limit
    that already applies to the rest of Specter-DIY (see docs/security-model.md).
    """
    if buf is None:
        return
    try:
        buf[:] = bytes(len(buf))
    except TypeError:
        # not a mutable buffer (e.g. plain bytes/str) - nothing we can do.
        pass


def _copy_prefix(src, n):
    """Copies the first n bytes of src into a fresh bytearray without
    creating an intermediate slice object. Slicing would leave an extra,
    un-zeroizable copy of secret bytes on the heap; n is 16-32 here, so
    the explicit loop costs nothing measurable."""
    out = bytearray(n)
    for i in range(n):
        out[i] = src[i]
    return out


def _bytes_eq(a, b):
    """Length-checked byte comparison used for the checksum and backup-id
    checks.

    Deliberately NOT advertised as constant-time: both values compared here
    are public (the checksum is stored in the file, the backup id is the
    directory name), so there is no secret whose timing could leak - and
    anyone able to read the card already holds the plaintext seed. This is
    a plain equality check with an explicit length guard.
    """
    if len(a) != len(b):
        return False
    for i in range(len(a)):
        if a[i] != b[i]:
            return False
    return True


def _varint_size(value):
    size = 1
    v = value
    while v > 0x7F:
        v >>= 7
        size += 1
    return size


def _read_varint(buf, pos):
    """Decode a canonical protobuf varint starting at buf[pos].

    Returns (value, new_pos). Rejects truncated input, overlong varints
    (more than 10 bytes), values that don't fit in 64 bits, and
    non-canonical (needlessly padded) encodings.
    """
    result = 0
    shift = 0
    start = pos
    n = len(buf)
    while True:
        if pos >= n:
            raise BitboxParseError("truncated varint")
        if pos - start >= _MAX_VARINT_BYTES:
            raise BitboxParseError("varint too long")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    if result > _U64_MAX:
        raise BitboxParseError("varint value too large")
    if _varint_size(result) != (pos - start):
        raise BitboxParseError("non-canonical varint encoding")
    return result, pos


def _read_length_delimited(buf, pos):
    length, pos = _read_varint(buf, pos)
    if length > _U32_MAX:
        raise BitboxParseError("length prefix too large")
    end = pos + length
    if end > len(buf):
        raise BitboxParseError("length-delimited field exceeds buffer")
    return buf[pos:end], end


def _iter_fields(buf):
    """Yield (field_number, wire_type, value, pos) tuples for a flat
    protobuf message.

    `value` is the decoded integer for wire type 0 (varint), and a raw byte
    slice for wire types 1 (64-bit), 2 (length-delimited) and 5 (32-bit).
    Wire types 1 and 5 are only ever encountered on unknown fields we skip,
    so their bytes are never interpreted further - no field in this schema
    uses a fixed-width type.

    Wire types 3 and 4 (deprecated "groups") are always rejected - we never
    silently skip them, since doing so safely would require understanding
    group nesting, which this minimal parser deliberately does not
    implement.
    """
    pos = 0
    n = len(buf)
    while pos < n:
        tag, pos = _read_varint(buf, pos)
        field_number = tag >> 3
        wire_type = tag & 0x7
        if field_number == 0:
            raise BitboxParseError("invalid field number 0")
        if wire_type == WIRE_VARINT:
            value, pos = _read_varint(buf, pos)
        elif wire_type == WIRE_64BIT:
            if pos + 8 > n:
                raise BitboxParseError("truncated 64-bit field")
            value = buf[pos:pos + 8]
            pos += 8
        elif wire_type == WIRE_LENGTH_DELIMITED:
            value, pos = _read_length_delimited(buf, pos)
        elif wire_type == WIRE_32BIT:
            if pos + 4 > n:
                raise BitboxParseError("truncated 32-bit field")
            value = buf[pos:pos + 4]
            pos += 4
        else:
            raise BitboxParseError(
                "unsupported wire type %d (protobuf groups are not supported)" % wire_type
            )
        yield field_number, wire_type, value, pos


def _require_u32(value, field_name):
    if value > _U32_MAX:
        raise BitboxParseError("%s: value does not fit in uint32" % field_name)
    return value


def _parse_known_message(buf, spec, msg_name):
    """Generic strict parser for a flat message.

    spec: {field_number: (name, expected_wire_type)}

    Unknown fields (not in spec) are safely skipped (already validated by
    _iter_fields to have a skippable wire type). Known fields must match
    their expected wire type and may only appear once each - a second
    occurrence of any known field is rejected rather than silently
    overwriting the first ("last one wins" is not used here).
    """
    result = {}
    for field_number, wire_type, value, _pos in _iter_fields(buf):
        spec_entry = spec.get(field_number)
        if spec_entry is None:
            continue
        name, expected_wire = spec_entry
        if wire_type != expected_wire:
            raise BitboxParseError(
                "%s: field %d (%s) has unexpected wire type" % (msg_name, field_number, name)
            )
        if name in result:
            raise BitboxParseError(
                "%s: duplicate field %d (%s)" % (msg_name, field_number, name)
            )
        result[name] = value
    return result


def _decode_utf8(raw, field_name, max_bytes):
    if len(raw) > max_bytes:
        raise BitboxParseError("%s: exceeds %d byte limit" % (field_name, max_bytes))
    try:
        value = bytes(raw).decode("utf-8")
    except UnicodeError:
        raise BitboxParseError("%s: invalid UTF-8" % field_name)
    # These fields are displayed on the device. Reject line breaks, control
    # characters and bidi overrides so an SD card cannot spoof the metadata
    # shown in a security-sensitive confirmation screen.
    for char in value:
        codepoint = ord(char)
        if (
            codepoint < 32
            or codepoint == 127
            or 0x202A <= codepoint <= 0x202E
            or 0x2066 <= codepoint <= 0x2069
        ):
            raise BitboxParseError("%s: contains unsupported control characters" % field_name)
    return value


def _right_pad(data, size):
    if len(data) > size:
        raise BitboxParseError("field longer than %d bytes" % size)
    return bytes(data) + bytes(size - len(data))


def _u32_le(value):
    return bytes((value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF))


# ---------------------------------------------------------------------------
# Message-specific parsers
# ---------------------------------------------------------------------------

_METADATA_SPEC = {
    1: ("timestamp", WIRE_VARINT),
    2: ("name", WIRE_LENGTH_DELIMITED),
    3: ("mode", WIRE_VARINT),
}

_DATA_SPEC = {
    1: ("seed_length", WIRE_VARINT),
    2: ("seed", WIRE_LENGTH_DELIMITED),
    3: ("birthdate", WIRE_VARINT),
    4: ("generator", WIRE_LENGTH_DELIMITED),
}

_CONTENT_SPEC = {
    1: ("checksum", WIRE_LENGTH_DELIMITED),
    2: ("metadata", WIRE_LENGTH_DELIMITED),
    3: ("length", WIRE_VARINT),
    4: ("data", WIRE_LENGTH_DELIMITED),
}

_BACKUP_V1_SPEC = {
    1: ("content", WIRE_LENGTH_DELIMITED),
}


def _parse_metadata(buf):
    fields = _parse_known_message(buf, _METADATA_SPEC, "BackupMetaData")
    timestamp = _require_u32(fields.get("timestamp", 0), "timestamp")
    name_raw = fields.get("name", b"")
    name = _decode_utf8(name_raw, "name", NAME_MAX_BYTES)
    mode = _require_u32(fields.get("mode", 0), "mode")
    return {
        "timestamp": timestamp,
        "name": name,
        "name_raw": bytes(name_raw),
        "mode": mode,
    }


def _parse_backup_data(buf):
    fields = _parse_known_message(buf, _DATA_SPEC, "BackupData")
    seed_length = _require_u32(fields.get("seed_length", 0), "seed_length")
    if "seed" not in fields:
        raise BitboxParseError("BackupData: missing seed field")
    seed = fields["seed"]
    if len(seed) != SEED_FIELD_SIZE:
        raise BitboxParseError(
            "BackupData: seed field must be exactly %d bytes" % SEED_FIELD_SIZE
        )
    seed_buf = bytearray(seed)
    try:
        birthdate = _require_u32(fields.get("birthdate", 0), "birthdate")
        generator_raw = fields.get("generator", b"")
        generator = _decode_utf8(generator_raw, "generator", GENERATOR_MAX_BYTES)
        result = {
            "seed_length": seed_length,
            "seed": seed_buf,
            "birthdate": birthdate,
            "generator": generator,
            "generator_raw": bytes(generator_raw),
        }
        seed_buf = None
        return result
    finally:
        zeroize(seed_buf)


def _parse_backup_content(buf):
    fields = _parse_known_message(buf, _CONTENT_SPEC, "BackupContent")
    if "checksum" not in fields:
        raise BitboxParseError("BackupContent: missing checksum field")
    checksum = fields["checksum"]
    if len(checksum) != SHA256_SIZE:
        raise BitboxParseError(
            "BackupContent: checksum must be exactly %d bytes" % SHA256_SIZE
        )
    if "metadata" not in fields:
        raise BitboxParseError("BackupContent: missing metadata field")
    if "data" not in fields:
        raise BitboxParseError("BackupContent: missing data field")
    length = _require_u32(fields.get("length", 0), "length")
    return {
        "checksum": bytes(checksum),
        "metadata_raw": fields["metadata"],
        "length": length,
        "data_raw": fields["data"],
    }


def _parse_backup_v1(buf):
    fields = _parse_known_message(buf, _BACKUP_V1_SPEC, "BackupV1")
    if "content" not in fields:
        raise BitboxParseError("BackupV1: missing content field")
    return fields["content"]


def _parse_backup_top_level(buf):
    """Parses the top-level `Backup` oneof.

    Unlike sub-messages, unknown fields at this level are NOT silently
    skipped: `backup_version` is a oneof and any field number other than 1
    (backup_v1) represents either an unsupported future backup version or a
    duplicate/conflicting oneof selection. Either way we must not guess -
    we reject explicitly instead of ignoring data we don't understand.
    """
    content_bytes = None
    for field_number, wire_type, value, _pos in _iter_fields(buf):
        if field_number != 1:
            raise BitboxParseError(
                "unsupported or unknown backup version (field %d)" % field_number
            )
        if wire_type != WIRE_LENGTH_DELIMITED:
            raise BitboxParseError("backup_v1 field has unexpected wire type")
        if content_bytes is not None:
            raise BitboxParseError("duplicate backup_v1 field")
        content_bytes = value
    if content_bytes is None:
        raise BitboxParseError("missing backup version (backup_v1)")
    return content_bytes


def compute_checksum(timestamp, mode, name_raw, seed_length, seed32, birthdate, generator_raw, length):
    """Recomputes the BackupContent checksum for the given field values.

    Preimage layout (see backup.rs `compute_checksum`):
        u32le(timestamp) || u8(mode) || name padded to 64 bytes ||
        u32le(seed_length) || seed (32 bytes) || u32le(birthdate) ||
        generator padded to 20 bytes || u32le(length)

    `seed32` must be a bytearray (not bytes): it carries the plaintext
    seed, and the checksum preimage is computed by feeding it straight to
    hashlib.update() precisely so the caller can zeroize it afterwards.
    Passing an immutable bytes defeats that - the seed would live on the
    heap with no handle to wipe it. This is enforced as a TypeError so a
    future caller can't silently regress the zeroization promise.
    """
    if not isinstance(seed32, bytearray):
        raise TypeError(
            "seed32 must be a bytearray so the caller can zeroize it, "
            "not %s" % type(seed32).__name__
        )
    if len(seed32) != SEED_FIELD_SIZE:
        raise BitboxParseError("seed must be exactly %d bytes for checksum" % SEED_FIELD_SIZE)
    h = hashlib.sha256()
    h.update(_u32_le(timestamp))
    h.update(bytes((mode & 0xFF,)))
    h.update(_right_pad(name_raw, NAME_MAX_BYTES))
    h.update(_u32_le(seed_length))
    # hashlib.update() accepts any bytes-like object - passing seed32
    # directly (it's a bytearray on the paths that own and later wipe it)
    # avoids leaving an extra immutable bytes copy of the seed on the heap.
    h.update(seed32)
    h.update(_u32_le(birthdate))
    h.update(_right_pad(generator_raw, GENERATOR_MAX_BYTES))
    h.update(_u32_le(length))
    return h.digest()


def compute_backup_id(entropy):
    """Returns the lowercase hex backup directory id for the given BIP-39
    entropy (16/24/32 raw bytes, NOT the 32-byte zero-padded seed field)."""
    # hexlify().decode() rather than bytes.hex(): MicroPython has no
    # bytes.hex(). Same convention as keystore/ram.py and keystore/sdcard.py.
    return hexlify(_backup_id_bytes(entropy)).decode()


def _backup_id_bytes(entropy):
    # The padded buffer holds the plaintext seed, so keep it in a mutable
    # bytearray and wipe it after use instead of leaving an immutable
    # bytes copy on the heap. hmac.new() accepts any bytes-like object as
    # msg, so no intermediate bytes(entropy)+bytes(...) concatenation copy
    # is needed.
    padded = bytearray(SEED_FIELD_SIZE)
    padded[:len(entropy)] = entropy
    try:
        # digestmod must be the *name* "sha256", not hashlib.sha256: MicroPython's
        # hmac only accepts the string form (CPython accepts both, which is why
        # this only shows up on the device / in the unix port). Same convention as
        # helpers.py, keystore/flash.py and keystore/ram.py.
        return hmac.new(b"backup", padded, digestmod="sha256").digest()
    finally:
        zeroize(padded)


def _id_matches(entropy, dir_name_hex):
    try:
        expected = unhexlify(dir_name_hex)
    except Exception:
        return False
    return _bytes_eq(_backup_id_bytes(entropy), expected)


class ParsedBackup:
    """Holds the validated contents of one BitBox backup copy.

    `entropy` is the single authoritative copy of the secret this object
    owns: one mutable bytearray holding exactly the real BIP-39 entropy
    (16/24/32 bytes), which zeroize() overwrites. The 32-byte zero-padded
    `seed` field is deliberately NOT retained - it carries no information
    beyond (entropy, seed_length), since the padding is validated to be
    all-zero, so keeping it would only mean a second secret buffer to
    track.
    """

    __slots__ = (
        "timestamp", "name", "mode", "seed_length", "entropy", "birthdate",
        "generator", "length", "checksum", "backup_id",
    )

    def __init__(self, timestamp, name, mode, seed_length, entropy, birthdate,
                 generator, length, checksum, backup_id):
        self.timestamp = timestamp
        self.name = name
        self.mode = mode
        self.seed_length = seed_length
        # bytearray of exactly seed_length bytes - owned by this object
        self.entropy = entropy
        self.birthdate = birthdate
        self.generator = generator
        self.length = length
        self.checksum = checksum
        self.backup_id = backup_id

    def mnemonic(self):
        """Derives the BIP-39 mnemonic. Does NOT cache the result.

        The bytes() conversion is load-bearing, do NOT "optimise" it away:
        embit's bip39.mnemonic_from_bytes() does `entropy += checksum`
        internally, which for a bytearray argument mutates the CALLER's
        buffer in place (16 bytes in -> 48 bytes out). Passing an immutable
        bytes forces embit to work on its own copy and leaves self.entropy
        intact and still zeroizable.
        """
        return bip39.mnemonic_from_bytes(bytes(self.entropy))

    def zeroize(self):
        zeroize(self.entropy)


def parse_backup(buf):
    """Parses `buf` as a `Backup` protobuf message and validates all
    structural and semantic invariants of the format (canonical field
    encoding, single backup version, exactly-32-byte seed field, valid
    seed length, zero padding, supported mode, string length limits, valid
    UTF-8).

    Does NOT verify the checksum or the backup directory id - use
    validate_backup() for that, or verify_checksum()/id checks manually.

    Raises BitboxParseError (or a subclass) on any violation.
    """
    if len(buf) > MAX_FILE_SIZE:
        raise BitboxParseError("backup file exceeds %d byte limit" % MAX_FILE_SIZE)
    if len(buf) == 0:
        raise BitboxParseError("empty backup file")

    backup_v1_bytes = _parse_backup_top_level(buf)
    content_bytes = _parse_backup_v1(backup_v1_bytes)
    content = _parse_backup_content(content_bytes)
    metadata = _parse_metadata(content["metadata_raw"])
    data = _parse_backup_data(content["data_raw"])

    if data["seed_length"] not in VALID_SEED_LENGTHS:
        raise BitboxParseError(
            "unsupported seed length %d (must be 16, 24 or 32)" % data["seed_length"]
        )
    # Checked index-wise rather than on a slice, to avoid materialising an
    # extra copy of part of the seed buffer on the heap.
    seed_buf = data["seed"]
    try:
        for i in range(data["seed_length"], SEED_FIELD_SIZE):
            if seed_buf[i] != 0:
                raise BitboxParseError("seed padding is not all-zero")
        if metadata["mode"] != BACKUP_MODE_PLAINTEXT:
            raise BitboxParseError("unsupported backup mode %d" % metadata["mode"])

        result = {
            "timestamp": metadata["timestamp"],
            "name": metadata["name"],
            "name_raw": metadata["name_raw"],
            "mode": metadata["mode"],
            "seed_length": data["seed_length"],
            "seed": seed_buf,
            "birthdate": data["birthdate"],
            "generator": data["generator"],
            "generator_raw": data["generator_raw"],
            "length": content["length"],
            "checksum": content["checksum"],
        }
        data["seed"] = None
        seed_buf = None
        return result
    finally:
        zeroize(seed_buf)


def validate_backup(buf, dir_name_hex):
    """Fully parses, checksum-verifies and id-verifies one backup file.

    Returns a ParsedBackup on success. Raises BitboxParseError,
    BitboxChecksumError or BitboxIdMismatchError otherwise.

    On every exit path the intermediate 32-byte padded seed buffer is
    zeroized, and on any failure path the extracted entropy is zeroized
    too, so a rejected backup leaves no secret bytes behind in buffers this
    function owns.
    """
    fields = parse_backup(buf)
    seed32 = fields["seed"]
    entropy = None
    try:
        computed = compute_checksum(
            fields["timestamp"], fields["mode"], fields["name_raw"],
            fields["seed_length"], seed32, fields["birthdate"],
            fields["generator_raw"], fields["length"],
        )
        if not _bytes_eq(computed, fields["checksum"]):
            raise BitboxChecksumError("checksum does not match backup contents")

        entropy = _copy_prefix(seed32, fields["seed_length"])
        if not _id_matches(entropy, dir_name_hex):
            raise BitboxIdMismatchError(
                "backup id does not match the directory it was loaded from"
            )

        result = ParsedBackup(
            timestamp=fields["timestamp"],
            name=fields["name"],
            mode=fields["mode"],
            seed_length=fields["seed_length"],
            entropy=entropy,
            birthdate=fields["birthdate"],
            generator=fields["generator"],
            length=fields["length"],
            checksum=fields["checksum"],
            backup_id=dir_name_hex,
        )
        # ownership of `entropy` now belongs to `result`; don't wipe it below
        entropy = None
        return result
    finally:
        zeroize(seed32)
        zeroize(entropy)


def _copies_match(a, b):
    """True if two ParsedBackup instances represent the identical backup.

    Comparing entropy + seed_length is equivalent to comparing the raw
    32-byte seed fields, because parse_backup() has already enforced that
    all bytes past seed_length are zero.
    """
    return (
        a.seed_length == b.seed_length
        and _bytes_eq(a.entropy, b.entropy)
        and a.timestamp == b.timestamp
        and a.name == b.name
        and a.mode == b.mode
        and a.birthdate == b.birthdate
        and a.generator == b.generator
        and a.length == b.length
        and a.checksum == b.checksum
    )


def bitwise_majority(buffers):
    """Bitwise-majority-vote recovery across exactly 3 equal-length buffers:
    for every bit position, the value that at least two of the three
    buffers agree on. Returns a new bytearray; does not modify the inputs.

    The per-byte loop is intentional. Doing this as one big-integer
    expression (int.from_bytes -> (a&b)|(a&c)|(b&c) -> to_bytes) measures
    ~29x faster, but would materialise three immutable big integers derived
    from the secret seed which can never be zeroized, in exchange for
    saving well under a millisecond on a path that only runs when all three
    copies are already damaged. Not a worthwhile trade on a wallet.
    """
    if len(buffers) != 3:
        raise BitboxRecoveryError("majority recovery requires exactly 3 copies")
    length = len(buffers[0])
    if any(len(b) != length for b in buffers):
        raise BitboxRecoveryError(
            "copies have different lengths; cannot attempt majority recovery"
        )
    a, b, c = buffers
    result = bytearray(length)
    for i in range(length):
        result[i] = (a[i] & b[i]) | (a[i] & c[i]) | (b[i] & c[i])
    return result


def load_backup(dir_name_hex, raw_files):
    """Top-level entry point: given the (already format-validated) backup
    directory name and the raw contents of its files, returns
    (ParsedBackup, valid_copy_count, used_majority_recovery).

    valid_copy_count is how many of the 3 raw files individually
    parsed/checksum/id-verified correctly (0, 1, 2 or 3). It is always 0
    when used_majority_recovery is True - majority recovery is only ever
    attempted when no individual copy validated on its own.

    `raw_files` must contain exactly 3 items, each at most MAX_FILE_SIZE
    bytes (the caller - the SD discovery layer - is expected to have
    enforced the file count and per-file size limit already while reading;
    this function re-checks defensively).

    Never mutates or writes anything - purely a function of its inputs.
    """
    if len(raw_files) != 3:
        raise BitboxParseError("expected exactly 3 backup files, found %d" % len(raw_files))
    for buf in raw_files:
        if len(buf) > MAX_FILE_SIZE:
            raise BitboxParseError("backup file exceeds %d byte limit" % MAX_FILE_SIZE)

    valid_copies = []
    for buf in raw_files:
        try:
            valid_copies.append(validate_backup(buf, dir_name_hex))
        except BitboxBackupError:
            continue

    if valid_copies:
        chosen = valid_copies[0]
        try:
            for other in valid_copies[1:]:
                if not _copies_match(chosen, other):
                    raise BitboxInconsistentCopiesError(
                        "backup copies disagree with each other - refusing to guess"
                    )
        except BitboxInconsistentCopiesError:
            # Nothing is returned to the caller, so wipe every copy we hold,
            # including the one we would otherwise have handed over.
            for copy in valid_copies:
                copy.zeroize()
            raise
        finally:
            # The redundant copies are never returned; only `chosen` is.
            for copy in valid_copies[1:]:
                copy.zeroize()
        return chosen, len(valid_copies), False

    lengths = set(len(b) for b in raw_files)
    if len(lengths) != 1:
        raise BitboxRecoveryError(
            "all copies are invalid and majority recovery is not possible "
            "(files have different lengths)"
        )

    recovered = bitwise_majority(raw_files)
    try:
        parsed = validate_backup(recovered, dir_name_hex)
    except BitboxBackupError:
        raise BitboxRecoveryError(
            "all copies are invalid and majority recovery did not produce a valid backup"
        )
    finally:
        zeroize(recovered)
    return parsed, 0, True


# ---------------------------------------------------------------------------
# Writer (the encoding counterpart of the parser above)
#
# Used only when Specter-DIY itself creates a new BitBox-format backup (see
# keystore/ram.py::export_mnemonic_to_sd), never by the import path above.
# Every encoder here mirrors the corresponding decoder one-to-one (same
# field numbers, same wire types, same preimage layout in compute_checksum),
# so build_backup()'s output is required to round-trip unchanged through
# parse_backup()/validate_backup() - this is exercised in the test suite.
# ---------------------------------------------------------------------------

def _encode_varint_into(out, value):
    """Appends a non-negative integer to `out` (a bytearray) as a canonical
    protobuf varint - the exact inverse of _read_varint().

    Appending in place, rather than returning a fresh bytes object, lets
    the caller keep everything in buffers it can zeroize() afterwards -
    the encoding of a backup contains the plaintext seed, so every
    intermediate holding it must stay wipeable (see zeroize()).
    """
    if value < 0 or value > _U64_MAX:
        raise BitboxParseError("varint value out of range")
    v = value
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            break


def _encode_varint_field_into(out, field_number, value):
    _encode_varint_into(out, (field_number << 3) | WIRE_VARINT)
    _encode_varint_into(out, value)


def _encode_length_delimited_field_into(out, field_number, data):
    _encode_varint_into(out, (field_number << 3) | WIRE_LENGTH_DELIMITED)
    _encode_varint_into(out, len(data))
    out.extend(data)


def build_backup(entropy, name="", generator="specter-diy", timestamp=0, birthdate=0):
    """Encodes `entropy` (16/24/32 raw BIP-39 entropy bytes, NOT the 32-byte
    zero-padded seed field) as a single native BitBox02 backup message -
    the on-disk content of one of the three redundant copies a real backup
    consists of.

    `length` is always encoded as 0: every backup this writes is in the
    current format (see the module docstring's note on the historical,
    non-zero `length` some old real-device backups carry, which
    parse_backup() also still accepts).

    Returns (backup_id_hex, encoded), where encoded is a **bytearray**:
    it carries the plaintext seed, so it is deliberately mutable - the
    caller owns it and must zeroize() it once it has been written out.
    All intermediate buffers holding seed material are zeroized here on
    every path, success or failure. Does not write anything to disk or
    duplicate the copy three times - see RAMKeyStore._write_bitbox_backup
    for that. Raises BitboxParseError if entropy has an unsupported length
    or name/generator exceed their byte limits.
    """
    if len(entropy) not in VALID_SEED_LENGTHS:
        raise BitboxParseError(
            "entropy must be 16, 24 or 32 bytes (got %d)" % len(entropy)
        )
    seed_length = len(entropy)
    mode = BACKUP_MODE_PLAINTEXT
    length = 0

    name_raw = name.encode("utf-8")
    if len(name_raw) > WRITER_NAME_MAX_BYTES:
        raise BitboxParseError("name exceeds %d byte limit" % WRITER_NAME_MAX_BYTES)
    generator_raw = generator.encode("utf-8")
    if len(generator_raw) > WRITER_GENERATOR_MAX_BYTES:
        raise BitboxParseError(
            "generator exceeds %d byte limit" % WRITER_GENERATOR_MAX_BYTES
        )

    # `data` embeds seed32; `content` embeds `data`; `v1` embeds `content`;
    # `out` embeds `v1` - so every one of these buffers ends up holding the
    # plaintext seed. All are bytearrays and all are wiped in the finally
    # block. `metadata` holds no secret (timestamp/name/mode only).
    seed32 = bytearray(SEED_FIELD_SIZE)
    seed32[:seed_length] = entropy
    data = bytearray()
    content = bytearray()
    v1 = bytearray()
    out = bytearray()
    try:
        checksum = compute_checksum(
            timestamp, mode, name_raw, seed_length, seed32, birthdate,
            generator_raw, length,
        )

        _encode_varint_field_into(data, 1, seed_length)
        _encode_length_delimited_field_into(data, 2, seed32)
        _encode_varint_field_into(data, 3, birthdate)
        _encode_length_delimited_field_into(data, 4, generator_raw)

        metadata = bytearray()
        _encode_varint_field_into(metadata, 1, timestamp)
        _encode_length_delimited_field_into(metadata, 2, name_raw)
        _encode_varint_field_into(metadata, 3, mode)

        _encode_length_delimited_field_into(content, 1, checksum)
        _encode_length_delimited_field_into(content, 2, metadata)
        _encode_varint_field_into(content, 3, length)
        _encode_length_delimited_field_into(content, 4, data)

        _encode_length_delimited_field_into(v1, 1, content)
        _encode_length_delimited_field_into(out, 1, v1)

        if len(out) > MAX_FILE_SIZE:
            raise BitboxParseError(
                "encoded backup exceeds %d byte limit" % MAX_FILE_SIZE
            )

        result = out
        # ownership of the encoded backup passes to the caller - exempt it
        # from the wipe below (the caller must zeroize() it once written)
        out = None
        return compute_backup_id(entropy), result
    finally:
        zeroize(seed32)
        zeroize(data)
        zeroize(content)
        zeroize(v1)
        zeroize(out)
