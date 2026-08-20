"""
Minimal protobuf byte-builder helpers used only by the BitBox backup test
suite, to construct both valid and deliberately malformed/corrupted
`Backup` messages without hand-writing hex strings for every case.

This is intentionally separate from src/bitbox_backup.py: production code
only ever *decodes* the format; this encoder exists purely so tests can
manufacture inputs.
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import hashlib

import bitbox_backup as bb

OFFICIAL_VECTOR_HEX = (
    "0a6c0a6a0a2017834e53e17370800c0bc49b49ef3f1309df104d7239db5bbd093c90eefc99511"
    "2110891bec6fb0512094d7920426974426f782233081012208af64d31126a39b98f59708a3a46"
    "3e5b000000000000000000000000000000001891bec6fb05220776392e31332e30"
)
OFFICIAL_VECTOR_MNEMONIC = (
    "memory raven era cave phone system dice come mechanic split moon repeat"
)
OFFICIAL_VECTOR_BACKUP_ID = (
    "577782fdfffbe314b23acaeefc39ad5e8641fba7e7dbe418a35956a879a67dd2"
)
OFFICIAL_VECTOR_ENTROPY = bytes.fromhex("8af64d31126a39b98f59708a3a463e5b")


def varint(value):
    out = bytearray()
    v = value
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def non_canonical_varint(value, extra_bytes=1):
    """Encodes `value` as a varint with `extra_bytes` redundant 0x80
    continuation padding - decodes to the same value but takes more bytes
    than necessary."""
    out = bytearray()
    v = value
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            break
    for _ in range(extra_bytes):
        out.append(b | 0x80)
        b = 0
    out.append(0)
    return bytes(out)


def tag(field_number, wire_type):
    return varint((field_number << 3) | wire_type)


def ld_field(field_number, data):
    """length-delimited field (wire type 2)"""
    return tag(field_number, 2) + varint(len(data)) + bytes(data)


def varint_field(field_number, value):
    """varint field (wire type 0)"""
    return tag(field_number, 0) + varint(value)


def fixed32_field(field_number, data4):
    return tag(field_number, 5) + bytes(data4)


def fixed64_field(field_number, data8):
    return tag(field_number, 1) + bytes(data8)


def group_field(field_number, wire_type=3):
    """A (deprecated) protobuf group start marker - always invalid here."""
    return tag(field_number, wire_type)


def build_metadata(timestamp=0, name=b"", mode=0, extra=b""):
    """Builds a BackupMetaData message. Like a canonical proto3 encoder,
    zero-valued scalar fields (timestamp=0, mode=0) are omitted - which is
    what real BitBox02 backups look like on the wire."""
    out = b""
    if timestamp != 0:
        out += varint_field(1, timestamp)
    out += ld_field(2, name)
    if mode != 0:
        out += varint_field(3, mode)
    out += extra
    return out


def build_data(seed_length, seed32, birthdate=0, generator=b"", extra=b""):
    out = b""
    if seed_length != 0:
        out += varint_field(1, seed_length)
    out += ld_field(2, seed32)
    if birthdate != 0:
        out += varint_field(3, birthdate)
    if generator:
        out += ld_field(4, generator)
    out += extra
    return out


def build_content(checksum, metadata_bytes, length=0, data_bytes=b"", extra=b""):
    out = ld_field(1, checksum)
    out += ld_field(2, metadata_bytes)
    if length != 0:
        out += varint_field(3, length)
    out += ld_field(4, data_bytes)
    out += extra
    return out


def build_backup_v1(content_bytes, extra=b""):
    return ld_field(1, content_bytes) + extra


def build_backup(backup_v1_bytes, field_number=1, extra=b""):
    return ld_field(field_number, backup_v1_bytes) + extra


def padded_seed(entropy, size=32):
    assert len(entropy) <= size
    return bytes(entropy) + bytes(size - len(entropy))


def make_valid_backup_bytes(
    entropy,
    name="test name",
    generator="v9.13.0",
    timestamp=1601281809,
    birthdate=1601281809 - 32400,
    mode=0,
    length=0,
    seed_length=None,
    checksum_override=None,
    corrupt_padding=False,
):
    """Builds a complete, well-formed (unless overridden) Backup message
    for the given entropy, mirroring bitbox02-firmware's backup::create().
    """
    if seed_length is None:
        seed_length = len(entropy)
    seed32 = bytearray(padded_seed(entropy))
    if corrupt_padding and seed_length < 32:
        seed32[-1] = 0x01

    name_raw = name.encode("utf-8")
    generator_raw = generator.encode("utf-8")

    if checksum_override is not None:
        checksum = checksum_override
    else:
        checksum = bb.compute_checksum(
            timestamp, mode, name_raw, seed_length, seed32, birthdate,
            generator_raw, length,
        )

    metadata_bytes = build_metadata(timestamp=timestamp, name=name_raw, mode=mode)
    data_bytes = build_data(seed_length, bytes(seed32), birthdate=birthdate, generator=generator_raw)
    content_bytes = build_content(checksum, metadata_bytes, length=length, data_bytes=data_bytes)
    backup_v1_bytes = build_backup_v1(content_bytes)
    return build_backup(backup_v1_bytes)


def backup_id_for(entropy):
    return bb.compute_backup_id(bytes(entropy))
