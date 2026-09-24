# OpenPGP codec: ASCII armor, packets, key material, signature packets.
#
# Packet formats follow RFC 4880 / RFC 9580. EdDSA signatures are verified
# over the hash of the signed data (RFC 9580 section 5.2.4). RSA uses
# PKCS#1 v1.5.

import hashlib
from binascii import a2b_base64, hexlify

from .base import (
    LINE_PROBE_LIMIT,
    MAX_RSA_EXPONENT_BYTES,
    MAX_RSA_MODULUS_BYTES,
    PGPBadMatchError,
    PGPDecodeArmorError,
    PGPError,
    PGPInvalidSignatureError,
    PGPOtherKeyError,
    PGPParseError,
    PGPSignatureExpirationError,
    PGPUnknownHashError,
)
from .ed25519 import verify as verify_ed25519
from .rsa import verify_digest as verify_rsa_digest

BEGIN_PUBLIC_KEY = "-----BEGIN PGP PUBLIC KEY BLOCK-----"
END_PUBLIC_KEY = "-----END PGP PUBLIC KEY BLOCK-----"
BEGIN_SIGNED_MESSAGE = "-----BEGIN PGP SIGNED MESSAGE-----"
BEGIN_SIGNATURE = "-----BEGIN PGP SIGNATURE-----"
END_SIGNATURE = "-----END PGP SIGNATURE-----"

# RFC 4880 / RFC 9580 public-key algorithms we can verify with.
ALGO_RSA_ENCRYPT_OR_SIGN = 1
ALGO_RSA_SIGN_ONLY = 3
ALGO_EDDSA_LEGACY = 22
ALGO_ED25519 = 27

# OID 1.3.6.1.4.1.11591.15.1 (Ed25519) used with algorithm 22.
OID_ED25519 = b"\x2b\x06\x01\x04\x01\xda\x47\x0f\x01"

KEY_RSA = "rsa"
KEY_ED25519 = "ed25519"

HASH_ALGO_SHA256 = 8
HASH_ALGO_SHA512 = 10

HASH_ALGOS = {
    HASH_ALGO_SHA256: ("sha256", "SHA-256", hashlib.sha256),
    HASH_ALGO_SHA512: ("sha512", "SHA-512", hashlib.sha512),
}

HASH_HEADER = {
    "SHA256": HASH_ALGO_SHA256,
    "SHA512": HASH_ALGO_SHA512,
}

SIG_TYPE_BINARY = 0x00
SIG_TYPE_TEXT = 0x01
SIG_TYPE_CERT_GENERIC = 0x10
SIG_TYPE_CERT_PERSONA = 0x11
SIG_TYPE_CERT_CASUAL = 0x12
SIG_TYPE_CERT_POSITIVE = 0x13
SIG_TYPE_SUBKEY_BINDING = 0x18
SIG_TYPE_PRIMARY_BINDING = 0x19
SIG_TYPE_DIRECT_KEY = 0x1F
SIG_TYPE_KEY_REVOCATION = 0x20
SIG_TYPE_SUBKEY_REVOCATION = 0x28
SIG_TYPE_CERT_REVOCATION = 0x30

FLAG_SIGN = 0x02

TAG_SIGNATURE = 2
TAG_PUBLIC_KEY = 6
TAG_MARKER = 10
TAG_USER_ID = 13
TAG_PUBLIC_SUBKEY = 14
TAG_USER_ATTR = 17
TAG_PADDING = 21

SUBPACKET_CREATION = 2
SUBPACKET_SIG_EXPIRE = 3
SUBPACKET_REVOKER = 5
SUBPACKET_KEY_EXPIRE = 9
SUBPACKET_ISSUER = 16
SUBPACKET_KEY_FLAGS = 27
SUBPACKET_EMBEDDED = 32
SUBPACKET_ISSUER_FPR = 33

# RFC 9580 Table 5. Unknown critical hashed subpackets reject the signature.
KNOWN_SUBPACKETS = {
    SUBPACKET_CREATION, SUBPACKET_SIG_EXPIRE, 4, SUBPACKET_REVOKER, 6, 7, SUBPACKET_KEY_EXPIRE,
    11, 12, SUBPACKET_ISSUER,
    20, 21, 22, 23, 24, 25, 26, SUBPACKET_KEY_FLAGS, 28, 29, 30, 31,
    SUBPACKET_EMBEDDED, SUBPACKET_ISSUER_FPR, 35, 37, 38, 39,
}


def looks_like_public_key(data: bytes) -> bool:
    """True if data is an ASCII-armored or binary OpenPGP public key."""
    if not data:
        return False
    try:
        head = bytes(data).lstrip()[:40].decode("ascii")
    except Exception:
        head = ""
    if head.startswith(BEGIN_PUBLIC_KEY):
        return True
    if head.startswith("-----BEGIN"):
        return False
    try:
        tag = _peek_packet_tag(bytes(data), 0)
    except Exception:
        return False
    return tag in (6, 14)


def _peek_packet_tag(data: bytes, offset: int = 0) -> int:
    if offset >= len(data):
        raise PGPParseError()
    first = data[offset]
    if (first & 0x80) == 0:
        raise PGPParseError()
    if first & 0x40:
        return first & 0x3F
    return (first >> 2) & 0x0F


def format_fingerprint(fingerprint: bytes) -> str:
    hexstr = hexlify(fingerprint).decode().upper()
    parts = [hexstr[i : i + 4] for i in range(0, len(hexstr), 4)]
    lines = [" ".join(parts[i : i + 5]) for i in range(0, len(parts), 5)]
    return "\n".join(lines)


class Base64Decoder:
    def __init__(self):
        self._out = bytearray()
        self._leftover = b""

    def feed(self, line: str):
        data = line.encode("ascii")
        data = bytes(b for b in data if b not in b" \t\r\n")
        if not data:
            return
        self._leftover += data
        if len(self._leftover) > 4:
            n = len(self._leftover) - (len(self._leftover) % 4)
            try:
                self._out.extend(a2b_base64(self._leftover[:n]))
            except Exception:
                raise PGPDecodeArmorError()
            self._leftover = self._leftover[n:]

    def finish(self) -> bytes:
        leftover = self._leftover
        self._leftover = b""
        if leftover:
            pad = (-len(leftover)) % 4
            if pad:
                leftover += b"=" * pad
            try:
                self._out.extend(a2b_base64(leftover))
            except Exception:
                return b""
        return bytes(self._out)


def crc24(data: bytes) -> int:
    crc = 0xB704CE
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


def decode_armor(text: str, begin: str = BEGIN_PUBLIC_KEY, end: str = END_PUBLIC_KEY) -> bytes:
    lines = text.split("\n")
    while lines and not lines[0].startswith(begin):
        lines.pop(0)
    if not lines:
        raise PGPDecodeArmorError()
    lines.pop(0)

    # Ignore header lines
    while lines and ":" in lines[0]:
        lines.pop(0)
    if lines and lines[0].strip() == "":
        lines.pop(0)

    decoder = Base64Decoder()
    crc_line = None
    found_end = False
    while lines:
        line = lines.pop(0).strip()
        if not line:
            continue
        if found_end:
            raise PGPDecodeArmorError()
        if line.startswith(end):
            found_end = True
            continue
        if line.startswith("-----") or len(line) > LINE_PROBE_LIMIT:
            raise PGPDecodeArmorError()
        if line.startswith("="):
            crc_line = line[1:]
            continue
        decoder.feed(line)

    if not found_end:
        raise PGPDecodeArmorError()
    raw = decoder.finish()
    if not raw:
        raise PGPDecodeArmorError()
    if crc_line is not None:
        crc_decoder = Base64Decoder()
        crc_decoder.feed(crc_line)
        crc_bytes = crc_decoder.finish()
        if len(crc_bytes) != 3:
            raise PGPDecodeArmorError()
        got = (crc_bytes[0] << 16) | (crc_bytes[1] << 8) | crc_bytes[2]
        if crc24(raw) != got:
            raise PGPDecodeArmorError()
    return raw


def _read_new_length(data: bytes, offset: int) -> tuple:
    if offset >= len(data):
        raise PGPParseError()
    first = data[offset]
    if first < 192:
        return first, offset + 1
    if first < 224:
        if offset + 1 >= len(data):
            raise PGPParseError()
        length = ((first - 192) << 8) + data[offset + 1] + 192
        return length, offset + 2
    if first == 255:
        if offset + 4 >= len(data):
            raise PGPParseError()
        length = (
            (data[offset + 1] << 24)
            | (data[offset + 2] << 16)
            | (data[offset + 3] << 8)
            | data[offset + 4]
        )
        return length, offset + 5
    raise PGPParseError()


def read_packet(data: bytes, offset: int) -> tuple:
    if offset >= len(data):
        raise PGPParseError()
    first = data[offset]
    if (first & 0x80) == 0:
        raise PGPParseError()
    offset += 1
    if first & 0x40:
        tag = first & 0x3F
        length, offset = _read_new_length(data, offset)
    else:
        tag = (first >> 2) & 0x0F
        lentype = first & 0x03
        if lentype == 0:
            if offset >= len(data):
                raise PGPParseError()
            length = data[offset]
            offset += 1
        elif lentype == 1:
            if offset + 1 >= len(data):
                raise PGPParseError()
            length = (data[offset] << 8) | data[offset + 1]
            offset += 2
        elif lentype == 2:
            if offset + 3 >= len(data):
                raise PGPParseError()
            length = (
                (data[offset] << 24)
                | (data[offset + 1] << 16)
                | (data[offset + 2] << 8)
                | data[offset + 3]
            )
            offset += 4
        else:
            length = len(data) - offset
    if offset + length > len(data):
        raise PGPParseError()
    return tag, data[offset : offset + length], offset + length


def fingerprint(body: bytes) -> bytes:
    # v4 fingerprints are SHA-1 by spec; signatures still reject SHA-1.
    if not body:
        raise PGPParseError()
    version = body[0]
    if version == 4:
        if len(body) > 0xFFFF:
            raise PGPParseError()
        header = bytes([0x99, (len(body) >> 8) & 0xFF, len(body) & 0xFF])
        return hashlib.sha1(header + body).digest()
    if version == 6:
        header = bytes([0x9B]) + len(body).to_bytes(4, "big")
        return hashlib.sha256(header + body).digest()
    raise PGPParseError()


def key_creation_time(body: bytes):
    if not body or len(body) < 5 or body[0] not in (4, 6):
        return None
    return int.from_bytes(body[1:5], "big")


def read_mpi_bytes(data: bytes, offset: int) -> tuple:
    if offset + 2 > len(data):
        raise PGPParseError()
    bits = (data[offset] << 8) | data[offset + 1]
    offset += 2
    nbytes = (bits + 7) // 8
    if offset + nbytes > len(data):
        raise PGPParseError()
    return data[offset : offset + nbytes], offset + nbytes


def _algorithm_and_material(body: bytes) -> tuple:
    if len(body) < 6:
        raise PGPParseError()
    version = body[0]
    algo = body[5]
    if version == 4:
        return algo, body[6:]
    if version == 6:
        if len(body) < 10:
            raise PGPParseError()
        return algo, body[10:]
    raise PGPParseError()


def parse_supported_key(body: bytes) -> tuple:
    algo, material = _algorithm_and_material(body)
    if algo in (ALGO_RSA_ENCRYPT_OR_SIGN, ALGO_RSA_SIGN_ONLY):
        raw_n, offset = read_mpi_bytes(material, 0)
        if len(raw_n) > MAX_RSA_MODULUS_BYTES:
            raise PGPParseError()
        raw_e, offset = read_mpi_bytes(material, offset)
        if len(raw_e) > MAX_RSA_EXPONENT_BYTES:
            raise PGPParseError()
        n = int.from_bytes(raw_n, "big") if raw_n else 0
        e = int.from_bytes(raw_e, "big") if raw_e else 0
        if n <= 0 or e <= 0:
            raise PGPParseError()
        return KEY_RSA, (n, e)
    if algo == ALGO_ED25519:
        if len(material) < 32:
            raise PGPParseError()
        return KEY_ED25519, bytes(material[:32])
    if algo == ALGO_EDDSA_LEGACY:
        if not material:
            raise PGPParseError()
        oid_len = material[0]
        if len(material) < 1 + oid_len:
            raise PGPParseError()
        oid = material[1 : 1 + oid_len]
        if oid != OID_ED25519:
            return None, None
        raw, _offset = read_mpi_bytes(material, 1 + oid_len)
        if len(raw) == 33 and raw[0] == 0x40:
            return KEY_ED25519, bytes(raw[1:])
        if len(raw) == 32:
            return KEY_ED25519, bytes(raw)
        raise PGPParseError()
    return None, None


class Signature:
    def __init__(self):
        self.version = 0
        self.sig_type = 0
        self.pk_algo = 0
        self.hash_algo = 0
        self.hashed_area = b""
        self.issuer_fpr = None
        self.issuer_keyid = None
        self.hashed_issuer_fpr = None
        self.hashed_issuer_keyid = None
        self.left16 = b""
        self.mpis = []
        self.raw_sig = b""
        self.created = None
        self.key_flags = None
        self.key_expiration = None
        self.sig_expiration = None
        self.has_sig_expiration = False
        self.has_designated_revoker = False
        self.unknown_critical = False
        self.embedded = []


def parse_armored_signature(text: str):
    try:
        raw = decode_armor(text, BEGIN_SIGNATURE, END_SIGNATURE)
    except PGPDecodeArmorError:
        raise PGPInvalidSignatureError()
    return _parse_signature_bytes(raw)


def _parse_signature_bytes(data: bytes):
    offset = 0
    while offset < len(data):
        try:
            tag, body, offset = read_packet(data, offset)
        except PGPError:
            raise PGPInvalidSignatureError()
        if tag == 2:
            return parse_signature_packet(body)
    raise PGPInvalidSignatureError()


def parse_signature_packet(body: bytes):
    if not body:
        raise PGPInvalidSignatureError()
    sig = Signature()
    sig.version = body[0]
    if sig.version != 4:
        raise PGPInvalidSignatureError()
    if len(body) < 6:
        raise PGPInvalidSignatureError()
    sig.sig_type = body[1]
    sig.pk_algo = body[2]
    sig.hash_algo = body[3]
    hashed_len = (body[4] << 8) | body[5]
    hashed_end = 6 + hashed_len
    if hashed_end + 2 > len(body):
        raise PGPInvalidSignatureError()
    sig.hashed_area = body[:hashed_end]
    hashed = body[6:hashed_end]
    unhashed_len = (body[hashed_end] << 8) | body[hashed_end + 1]
    unhashed_start = hashed_end + 2
    unhashed_end = unhashed_start + unhashed_len
    if unhashed_end + 2 > len(body):
        raise PGPInvalidSignatureError()
    unhashed = body[unhashed_start:unhashed_end]
    sig.left16 = body[unhashed_end : unhashed_end + 2]
    rest = body[unhashed_end + 2 :]

    _apply_subpackets(sig, hashed, True)
    _apply_subpackets(sig, unhashed, False)

    if sig.pk_algo == ALGO_ED25519:
        if len(rest) < 64:
            raise PGPInvalidSignatureError()
        sig.raw_sig = bytes(rest[:64])
        return sig

    offset = 0
    try:
        while offset < len(rest):
            raw, offset = read_mpi_bytes(rest, offset)
            sig.mpis.append(raw)
    except PGPError:
        raise PGPInvalidSignatureError()

    if sig.pk_algo == ALGO_EDDSA_LEGACY:
        if len(sig.mpis) < 2:
            raise PGPInvalidSignatureError()
        sig.raw_sig = _ed25519_mpi(sig.mpis[0]) + _ed25519_mpi(sig.mpis[1])
    elif sig.pk_algo in (ALGO_RSA_ENCRYPT_OR_SIGN, ALGO_RSA_SIGN_ONLY):
        if not sig.mpis:
            raise PGPInvalidSignatureError()
        sig.raw_sig = sig.mpis[0]
    else:
        raise PGPInvalidSignatureError(
            "This signature uses an unsupported key type."
        )
    return sig


def _ed25519_mpi(raw: bytes) -> bytes:
    if len(raw) == 33 and raw[0] == 0x40:
        raw = raw[1:]
    if len(raw) > 32:
        raw = raw[-32:]
    if len(raw) < 32:
        raw = b"\x00" * (32 - len(raw)) + raw
    return raw


def _apply_subpackets(sig: Signature, data: bytes, hashed: bool):
    offset = 0
    while offset < len(data):
        length, offset = _read_subpacket_length(data, offset)
        if offset + length > len(data) or length < 1:
            raise PGPInvalidSignatureError()
        raw_type = data[offset]
        typ = raw_type & 0x7F
        payload = data[offset + 1 : offset + length]
        offset += length
        if hashed and (raw_type & 0x80) and typ not in KNOWN_SUBPACKETS:
            sig.unknown_critical = True
        if typ == SUBPACKET_CREATION and hashed and len(payload) == 4:
            sig.created = int.from_bytes(payload, "big")
        elif typ == SUBPACKET_SIG_EXPIRE:
            if len(payload) == 4:
                duration = int.from_bytes(payload, "big")
                if duration:
                    sig.has_sig_expiration = True
                if hashed:
                    sig.sig_expiration = duration
        elif typ == SUBPACKET_REVOKER:
            sig.has_designated_revoker = True
        elif typ == SUBPACKET_KEY_EXPIRE and hashed and len(payload) == 4:
            sig.key_expiration = int.from_bytes(payload, "big")
        elif typ == SUBPACKET_KEY_FLAGS and hashed and payload:
            sig.key_flags = payload[0]
        elif typ == SUBPACKET_EMBEDDED and payload:
            sig.embedded.append(payload)
        elif typ == SUBPACKET_ISSUER_FPR and len(payload) >= 21:
            fpr = bytes(payload[1:])
            if hashed:
                sig.hashed_issuer_fpr = fpr
            if sig.issuer_fpr is None:
                sig.issuer_fpr = fpr
        elif typ == SUBPACKET_ISSUER and len(payload) >= 8:
            keyid = bytes(payload[:8])
            if hashed:
                sig.hashed_issuer_keyid = keyid
            if sig.issuer_keyid is None:
                sig.issuer_keyid = keyid


def _read_subpacket_length(data: bytes, offset: int) -> tuple:
    if offset >= len(data):
        raise PGPInvalidSignatureError()
    first = data[offset]
    if first < 192:
        return first, offset + 1
    if first < 255:
        if offset + 1 >= len(data):
            raise PGPInvalidSignatureError()
        length = ((first - 192) << 8) + data[offset + 1] + 192
        return length, offset + 2
    if offset + 4 >= len(data):
        raise PGPInvalidSignatureError()
    length = (
        (data[offset + 1] << 24)
        | (data[offset + 2] << 16)
        | (data[offset + 3] << 8)
        | data[offset + 4]
    )
    return length, offset + 5


def issuer_match(sig, fingerprint: bytes):
    if sig.hashed_issuer_fpr is not None:
        return sig.hashed_issuer_fpr == fingerprint
    if sig.issuer_fpr is not None:
        return sig.issuer_fpr == fingerprint
    if sig.issuer_keyid is not None:
        return fingerprint[-8:] == sig.issuer_keyid
    return None


def signature_trailer(sig) -> bytes:
    return sig.hashed_area + b"\x04\xff" + bytes([
        (len(sig.hashed_area) >> 24) & 0xFF,
        (len(sig.hashed_area) >> 16) & 0xFF,
        (len(sig.hashed_area) >> 8) & 0xFF,
        len(sig.hashed_area) & 0xFF,
    ])


def verify_signature(signing_keys: list, sig, digest: bytes):
    if sig.has_sig_expiration:
        raise PGPSignatureExpirationError()
    if (
        sig.hashed_issuer_fpr is None
        and sig.issuer_fpr is None
        and sig.issuer_keyid is None
    ):
        raise PGPInvalidSignatureError()
    key_type = None
    key = None
    for fingerprint, kt, k in signing_keys:
        if issuer_match(sig, fingerprint) is True:
            key_type, key = kt, k
            break
    if key is None:
        raise PGPOtherKeyError()
    if digest[:2] == sig.left16 and check_sig(key_type, key, sig, digest):
        return
    raise PGPBadMatchError()


def check_sig(key_type: str, key, sig, digest: bytes) -> bool:
    if sig.pk_algo in (ALGO_EDDSA_LEGACY, ALGO_ED25519):
        if key_type != KEY_ED25519:
            return False
        return verify_ed25519(key, digest, sig.raw_sig)
    if sig.pk_algo in (ALGO_RSA_ENCRYPT_OR_SIGN, ALGO_RSA_SIGN_ONLY):
        if key_type != KEY_RSA:
            return False
        entry = HASH_ALGOS.get(sig.hash_algo)
        if entry is None:
            raise PGPUnknownHashError()
        return verify_rsa_digest(key, digest, sig.raw_sig, entry[1])
    return False

