import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase
from binascii import b2a_base64, unhexlify
import hashlib
import os

from tests.util import TEST_DIR

from pgp.ed25519 import verify as verify_ed25519
from pgp.rsa import verify_digest as verify_rsa_digest
from pgp.base import (
    FILE_CHUNK_SIZE,
    LINE_PROBE_LIMIT,
    MAX_PUBLIC_KEY_BYTES,
    MAX_RSA_MODULUS_BYTES,
    PGPBinaryError,
    PGPError,
    PGPInvalidKeyError,
    PGPKeyTooLargeError,
    PGPParseError,
    PGPSignatureExpirationError,
    PGPSlashInFilenameError,
    PGPUnsupportedKeyError,
    companion_filename,
    iter_file_chunks,
)
from pgp.checksums import (
    KIND_BINARY,
    KIND_CHECKSUM_FILES,
    KIND_EMPTY,
    KIND_LONG_CHECKSUM_FILES,
    KIND_LONG_TEXT,
    KIND_TEXT,
    MAX_CHECKSUM_LIST_BYTES,
    MAX_TEXT_BYTES,
    PayloadClassifier,
    unverified_files,
    verify_checksum_files,
)
from pgp.pgp import (
    SIG_INVALID_MSG,
    SIG_TOO_LARGE_MSG,
    _TransferablePublicKey,
    _expiry_unix,
    load_ascii_armored_public_key,
    verify_signed_checksums,
)
from pgp.codec import (
    BEGIN_PUBLIC_KEY,
    BEGIN_SIGNATURE,
    END_SIGNATURE,
    crc24,
    decode_armor,
    format_fingerprint,
    key_creation_time,
    parse_supported_key,
    read_packet,
)

UNKNOWN_HASH_MSG = (
    "Unknown hash format. We only support SHA256 and SHA512 signed messages."
)
SIG_PUBLIC_KEY_MSG = "This file is a public key, not a signed message."
SIG_OTHER_KEY_MSG = "This signature was made by a different key."
SIG_BAD_MATCH_MSG = (
    "The signature claims to be from this key, but it does not match."
)
SIG_EXPIRE_MSG = "Signatures with expiration are not supported."


_DATA = os.path.dirname(__file__) + "/data"


def _read_data(name):
    with open(_DATA + "/" + name, "rb") as f:
        return f.read()


VALID_PUBLIC_KEY = _read_data("valid_public_key.asc")
VALID_FINGERPRINT = "9F2AFE042D377AC965E817F4E99DFAA7B813535D"

# RFC 8032 section 7.1, test 1 (empty message).
ED25519_PK = unhexlify(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)
ED25519_SIG = unhexlify(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)

RSA_N = 150546926018442044081036059820980577724549357799260265344637398135953244289965187086559959087496417648021270950827275307686580997307774013397939032689869353255019314603180443668064377750767186156168318586778596839845971038952894993705964175347125695088544856132401125246921617487041265355083092558040042895169
RSA_E = 65537
RSA_PAYLOAD = b"specter-diy pgp verify test"
RSA_SIG = unhexlify(
    "9f275cbf41baafb5468d10010d784040695874d139ce6f6d858181b5f7294ea6"
    "bcc79a9023e3d25c9ae641ce1e6e139fa1cd3c6d484f3e42ca99634406bab7b2"
    "7b32001c6e1837f6aa2ecc14314fbecc7f4c92d963c604e29b3a5c763179114a"
    "4864088644f7ebc7d36155ce15c87236907882d933a8af70aae3f3872544687c"
)

SHA256SUMS = (
    "b46b6b3ea256bc9f9d4da4250c0d6ffdfc1800cbb44a8845810e045c5e8cae01  initial_firmware_v1.10.5.bin\n"
    "fcd23591cd990cc7973861916e5d398ddd8f3f4dea226035d236ffe0e30bb0ea  specter_upgrade_v1.10.5.bin\n"
)

ED_PUB = _read_data("ed_pub.asc")
ED_CLEARSIGN = _read_data("ed_clearsign.asc")
ED_DETACH = _read_data("ed_detach.asc")
ED_DETACH_SIG = unhexlify(
    "88750400160a001d162104e9938cc62642f0b1c123ab79d97ddda9997c179a05"
    "026aaeb77b000a0910d97ddda9997c179a2a670100b2c1c85c92d7b85987f285"
    "da781ca5311bd8525e2c4c8e5623079e181cabc9b80100bb51725e980e3b0c8f"
    "8e7a62c4c445b3196f63abc1abce521528fcd68441c90b"
)
OTHER_DETACH = _read_data("other_detach.asc")
RSA_PUB = _read_data("rsa_pub.asc")
RSA_CLEARSIGN = _read_data("rsa_clearsign.asc")
RSA_DETACH = _read_data("rsa_detach.asc")
RSA_SHA1 = _read_data("rsa_sha1.asc")
RSA_SUBKEY_PUB = _read_data("rsa_subkey_pub.asc")
# Ed25519 [SC] primary + Cv25519 [E] encryption subkey.
ED_ENCRYPT_SUBKEY_PUB = _read_data("ed_encrypt_subkey_pub.asc")
RSA_SUBKEY_DETACH = _read_data("rsa_subkey_detach.asc")


def _armor_packets(raw, begin, end):
    b64 = b2a_base64(raw).decode().replace("\n", "")
    wrapped = "\n".join(b64[i : i + 64] for i in range(0, len(b64), 64))
    crc = crc24(raw)
    crc_b64 = b2a_base64(
        bytes([(crc >> 16) & 0xFF, (crc >> 8) & 0xFF, crc & 0xFF])
    ).decode().strip()
    return (begin + "\n\n" + wrapped + "\n=" + crc_b64 + "\n" + end + "\n").encode()


def _armor_public_key_packets(raw):
    return _armor_packets(
        raw,
        "-----BEGIN PGP PUBLIC KEY BLOCK-----",
        "-----END PGP PUBLIC KEY BLOCK-----",
    )


def _armor_signature_packets(raw):
    return _armor_packets(raw, BEGIN_SIGNATURE, END_SIGNATURE)


def _rsa_v4_key_body(n_bytes, e=65537):
    n_bits = n_bytes * 8
    n_mpi = bytes([(n_bits >> 8) & 0xFF, n_bits & 0xFF]) + (b"\xff" * n_bytes)
    e_bits = e.bit_length()
    e_len = (e_bits + 7) // 8
    e_mpi = bytes([(e_bits >> 8) & 0xFF, e_bits & 0xFF]) + e.to_bytes(e_len, "big")
    return bytes([4, 0, 0, 0, 1, 1]) + n_mpi + e_mpi


def _encode_new_packet(tag, body):
    n = len(body)
    if n < 192:
        return bytes([0xC0 | tag, n]) + body
    if n < 8384:
        n2 = n - 192
        return bytes([0xC0 | tag, (n2 >> 8) + 192, n2 & 0xFF]) + body
    return bytes([0xC0 | tag, 255]) + n.to_bytes(4, "big") + body


def _with_sig_expire(armored, hashed=False, seconds=86400):
    raw = decode_armor(armored.decode(), BEGIN_SIGNATURE, END_SIGNATURE)
    tag, body, _end = read_packet(raw, 0)
    if tag != 2:
        raise AssertionError("no signature packet")
    hashed_len = (body[4] << 8) | body[5]
    hashed_end = 6 + hashed_len
    unhashed_len = (body[hashed_end] << 8) | body[hashed_end + 1]
    unhashed_start = hashed_end + 2
    unhashed_end = unhashed_start + unhashed_len
    extra = bytes([5, 3]) + int(seconds).to_bytes(4, "big")
    if hashed:
        new_hashed_len = hashed_len + len(extra)
        new_body = (
            body[:4]
            + bytes([(new_hashed_len >> 8) & 0xFF, new_hashed_len & 0xFF])
            + body[6:hashed_end]
            + extra
            + body[hashed_end:]
        )
    else:
        new_unhashed_len = unhashed_len + len(extra)
        new_body = (
            body[:hashed_end]
            + bytes([(new_unhashed_len >> 8) & 0xFF, new_unhashed_len & 0xFF])
            + body[unhashed_start:unhashed_end]
            + extra
            + body[unhashed_end:]
        )
    return _armor_signature_packets(_encode_new_packet(2, new_body))


def _with_first_sig_hash_algo(armored, algo):
    raw = bytearray(decode_armor(armored.decode()))
    offset = 0
    while offset < len(raw):
        tag, body, end = read_packet(bytes(raw), offset)
        if tag == 2:
            raw[end - len(body) + 3] = algo
            return _armor_public_key_packets(bytes(raw))
        offset = end
    raise AssertionError("no signature packet")


def _with_first_sig_type(armored, sig_type):
    raw = bytearray(decode_armor(armored.decode()))
    offset = 0
    while offset < len(raw):
        tag, body, end = read_packet(bytes(raw), offset)
        if tag == 2:
            raw[end - len(body) + 1] = sig_type
            return _armor_public_key_packets(bytes(raw))
        offset = end
    raise AssertionError("no signature packet")


def _inject_unhashed(body, extra):
    hashed_len = (body[4] << 8) | body[5]
    hashed_end = 6 + hashed_len
    unhashed_len = (body[hashed_end] << 8) | body[hashed_end + 1]
    unhashed_start = hashed_end + 2
    unhashed_end = unhashed_start + unhashed_len
    new_unhashed_len = unhashed_len + len(extra)
    return (
        body[:hashed_end]
        + bytes([(new_unhashed_len >> 8) & 0xFF, new_unhashed_len & 0xFF])
        + body[unhashed_start:unhashed_end]
        + extra
        + body[unhashed_end:]
    )


def _with_first_key_unhashed(armored, extra):
    raw = decode_armor(armored.decode())
    offset = 0
    out = bytearray()
    done = False
    while offset < len(raw):
        tag, body, end = read_packet(raw, offset)
        if tag == 2 and not done:
            out.extend(_encode_new_packet(2, _inject_unhashed(body, extra)))
            done = True
        else:
            out.extend(raw[offset:end])
        offset = end
    if not done:
        raise AssertionError("no signature packet")
    return _armor_public_key_packets(bytes(out))


def _with_subkey_sig_type(armored, sig_type):
    raw = bytearray(decode_armor(armored.decode()))
    offset = 0
    seen_sub = False
    while offset < len(raw):
        tag, body, end = read_packet(bytes(raw), offset)
        if tag == 14:
            seen_sub = True
        elif tag == 2 and seen_sub:
            raw[end - len(body) + 1] = sig_type
            return _armor_public_key_packets(bytes(raw))
        offset = end
    raise AssertionError("no subkey signature")


def _with_subkey_unhashed(armored, extra):
    raw = decode_armor(armored.decode())
    offset = 0
    out = bytearray()
    seen_sub = False
    done = False
    while offset < len(raw):
        tag, body, end = read_packet(raw, offset)
        if tag == 14:
            seen_sub = True
        if tag == 2 and seen_sub and not done:
            out.extend(_encode_new_packet(2, _inject_unhashed(body, extra)))
            done = True
        else:
            out.extend(raw[offset:end])
        offset = end
    if not done:
        raise AssertionError("no subkey signature")
    return _armor_public_key_packets(bytes(out))


def _with_document_sig_type(armored, sig_type):
    raw = bytearray(decode_armor(armored.decode(), BEGIN_SIGNATURE, END_SIGNATURE))
    offset = 0
    while offset < len(raw):
        tag, body, end = read_packet(bytes(raw), offset)
        if tag == 2:
            raw[end - len(body) + 1] = sig_type
            return _armor_signature_packets(bytes(raw))
        offset = end
    raise AssertionError("no signature packet")


def _drop_packets_after_first_subkey(armored):
    raw = decode_armor(armored.decode())
    offset = 0
    while offset < len(raw):
        tag, body, end = read_packet(raw, offset)
        if tag == 14:
            return _armor_public_key_packets(raw[:end])
        offset = end
    raise AssertionError("no subkey packet")


def iter_bytes_chunks(data, chunk_size=FILE_CHUNK_SIZE):
    i = 0
    n = len(data)
    while i < n:
        yield data[i : i + chunk_size]
        i += chunk_size


def _unescape_line(line: str) -> str:
    if line.startswith("- "):
        return line[2:]
    return line


def parsed_signed_message(payload):
    clf = PayloadClassifier()
    if isinstance(payload, str):
        clf.feed_text(payload.replace("\r\n", "\n").replace("\r", "\n"))
    else:
        clf.feed_bytes(payload)
    return clf.finish()


def parse_checksum_list(text):
    kind, value = parsed_signed_message(text)
    if kind != KIND_CHECKSUM_FILES:
        raise PGPError("Could not parse checksum file.")
    return value


def _load_pub(data):
    fingerprint, signing_keys, _expires = load_ascii_armored_public_key(
        iter_bytes_chunks(data)
    )
    return fingerprint, signing_keys


def verify_rsa(key, payload, signature):
    digest = hashlib.sha256(payload).digest()
    return verify_rsa_digest(key, digest, signature, "SHA-256")


class PGPPublicKeyLoadTest(TestCase):
    def test_loads_ascii_armored_public_key_and_fingerprint(self):
        fingerprint, signing_keys = _load_pub(VALID_PUBLIC_KEY)
        self.assertEqual(fingerprint.hex().upper(), VALID_FINGERPRINT)
        self.assertEqual(
            format_fingerprint(fingerprint),
            "9F2A FE04 2D37 7AC9 65E8\n17F4 E99D FAA7 B813 535D",
        )
        self.assertEqual(len(signing_keys), 1)
        self.assertEqual(signing_keys[0][0], fingerprint)
        self.assertEqual(signing_keys[0][1], "ed25519")
        self.assertEqual(len(signing_keys[0][2]), 32)
        _fpr, _keys, expires = load_ascii_armored_public_key(
            iter_bytes_chunks(VALID_PUBLIC_KEY)
        )
        self.assertIsNone(expires)

    def test_key_expiry_unix(self):
        raw = decode_armor(VALID_PUBLIC_KEY.decode())
        _tag, body, _end = read_packet(raw, 0)
        created = key_creation_time(body)
        self.assertTrue(created)
        self.assertEqual(_expiry_unix(body, 86400), created + 86400)
        self.assertIsNone(_expiry_unix(body, 0))
        self.assertIsNone(_expiry_unix(body, None))
        collector = _TransferablePublicKey(raw)
        collector._note_expiry(body, 200)
        collector._note_expiry(body, 100)
        collector._note_expiry(body, None)
        self.assertEqual(collector.expires_at, created + 100)

    def test_rejects_binary_key_with_flag(self):
        try:
            _load_pub(b"\x99\x01\x00" + b"\xff" * 16)
        except PGPBinaryError as e:
            self.assertEqual(str(e), "Invalid or unsupported ASCII-armored OpenPGP public key")
        else:
            self.fail("Expected PGPBinaryError for binary key")

    def test_rejects_non_ascii_inside_armor(self):
        data = VALID_PUBLIC_KEY.replace(b"KEY BLOCK", b"KEY BLOCK\xff")
        try:
            _load_pub(data)
        except PGPBinaryError:
            return
        self.fail("Expected PGPBinaryError for non-ascii armor")

    def test_rejects_private_key_header(self):
        data = VALID_PUBLIC_KEY.replace(
            b"BEGIN PGP PUBLIC KEY BLOCK",
            b"BEGIN PGP PRIVATE KEY BLOCK",
        ).replace(
            b"END PGP PUBLIC KEY BLOCK",
            b"END PGP PRIVATE KEY BLOCK",
        )
        try:
            _load_pub(data)
        except PGPBinaryError:
            self.fail("Private key should not be reported as binary")
        except PGPError:
            return
        self.fail("Expected PGPError for private key")

    def test_rejects_bad_checksum(self):
        data = VALID_PUBLIC_KEY.replace(b"=cTwO", b"=AAAA")
        try:
            _load_pub(data)
        except PGPBinaryError:
            self.fail("Bad checksum should not be reported as binary")
        except PGPError:
            return
        self.fail("Expected PGPError for bad checksum")

    def test_rejects_empty_ascii(self):
        try:
            _load_pub(b"")
        except PGPBinaryError:
            self.fail("Empty key should not be reported as binary")
        except PGPError:
            return
        self.fail("Expected PGPError for empty data")

    def test_rejects_trailing_junk_after_end(self):
        try:
            _load_pub(VALID_PUBLIC_KEY + b"extra\n")
        except PGPBinaryError:
            self.fail("Trailing junk should not be reported as binary")
        except PGPError:
            return
        self.fail("Expected PGPError for trailing junk after armor end")

    def test_allows_trailing_blank_lines_after_end(self):
        fingerprint, signing_keys = _load_pub(VALID_PUBLIC_KEY + b"\n\n")
        self.assertEqual(fingerprint.hex().upper(), VALID_FINGERPRINT)

    def test_rejects_wrong_header_without_reading_rest(self):
        extra = []

        def chunks():
            yield b"not-a-pgp-key-file-" + b"x" * 40
            extra.append("read")
            yield b"should-not-be-read"

        try:
            load_ascii_armored_public_key(chunks())
        except PGPInvalidKeyError:
            pass
        else:
            self.fail("Expected PGPInvalidKeyError for wrong header")
        self.assertEqual(extra, [])

    def test_normalizes_crlf_split_across_chunks(self):
        data = VALID_PUBLIC_KEY.replace(b"\n", b"\r\n")
        idx = data.find(b"\r\n")
        self.assertTrue(idx >= 0)
        first = data[: idx + 1]
        rest = data[idx + 1 :]
        fingerprint, signing_keys, _expires = load_ascii_armored_public_key(
            iter([first, rest])
        )
        self.assertEqual(fingerprint.hex().upper(), VALID_FINGERPRINT)

    def test_rejects_oversized_public_key(self):
        def chunks():
            yield (BEGIN_PUBLIC_KEY + "\n\n").encode()
            n = 0
            while n <= MAX_PUBLIC_KEY_BYTES:
                yield b"A" * 256
                n += 256

        try:
            load_ascii_armored_public_key(chunks())
        except PGPKeyTooLargeError:
            return
        self.fail("Expected PGPKeyTooLargeError")

    def test_parses_4096_bit_rsa_modulus(self):
        kind, key = parse_supported_key(_rsa_v4_key_body(MAX_RSA_MODULUS_BYTES))
        self.assertEqual(kind, "rsa")
        n, e = key
        self.assertEqual(e, 65537)
        self.assertEqual((n.bit_length() + 7) // 8, MAX_RSA_MODULUS_BYTES)

    def test_rejects_oversized_rsa_modulus(self):
        try:
            parse_supported_key(_rsa_v4_key_body(MAX_RSA_MODULUS_BYTES + 1))
        except PGPParseError:
            return
        self.fail("Expected PGPParseError for RSA modulus larger than 4096 bits")

    def test_rejects_oversized_rsa_exponent(self):
        try:
            parse_supported_key(_rsa_v4_key_body(128, e=1 << 32))
        except PGPParseError:
            return
        self.fail("Expected PGPParseError for RSA exponent larger than 32 bits")

    def test_unsupported_algorithm_is_rejected(self):
        body = bytes([4, 0, 0, 0, 1, 17])
        raw = bytes([0xC6, len(body)]) + body
        try:
            _load_pub(_armor_public_key_packets(raw))
        except PGPUnsupportedKeyError as e:
            self.assertEqual(
                str(e),
                "This key seems valid, but we only support Ed25519 and RSA keys.",
            )
        else:
            self.fail("Expected PGPUnsupportedKeyError for unsupported primary")

    def test_encrypt_subkey_is_not_a_signer(self):
        fingerprint, signing_keys = _load_pub(ED_ENCRYPT_SUBKEY_PUB)
        self.assertEqual(signing_keys[0][1], "ed25519")
        self.assertEqual(len(signing_keys), 1)
        self.assertEqual(signing_keys[0][0], fingerprint)

    def test_rejects_sha1_self_signature(self):
        try:
            _load_pub(_with_first_sig_hash_algo(VALID_PUBLIC_KEY, 1))
        except PGPInvalidKeyError as e:
            self.assertEqual(
                str(e), "Invalid or unsupported ASCII-armored OpenPGP public key"
            )
        else:
            self.fail("Expected PGPInvalidKeyError for SHA-1 self-signature")

    def test_rejects_subkey_without_binding(self):
        try:
            _load_pub(_drop_packets_after_first_subkey(RSA_SUBKEY_PUB))
        except PGPInvalidKeyError as e:
            self.assertEqual(
                str(e), "Invalid or unsupported ASCII-armored OpenPGP public key"
            )
        else:
            self.fail("Expected PGPInvalidKeyError for unbound subkey")

    def test_rejects_tampered_subkey_binding(self):
        raw = bytearray(decode_armor(RSA_SUBKEY_PUB.decode()))
        offset = 0
        last_sig_end = None
        while offset < len(raw):
            tag, body, end = read_packet(bytes(raw), offset)
            if tag == 2:
                last_sig_end = end
            offset = end
        raw[last_sig_end - 1] ^= 1
        try:
            _load_pub(_armor_public_key_packets(bytes(raw)))
        except PGPInvalidKeyError:
            return
        self.fail("Expected PGPInvalidKeyError for tampered subkey binding")

    def test_rejects_cert_revocation(self):
        try:
            _load_pub(_with_first_sig_type(VALID_PUBLIC_KEY, 0x30))
        except PGPInvalidKeyError:
            return
        self.fail("Expected PGPInvalidKeyError for certification revocation")

    def test_rejects_key_revocation_packet(self):
        try:
            _load_pub(_with_first_sig_type(VALID_PUBLIC_KEY, 0x20))
        except PGPInvalidKeyError:
            return
        self.fail("Expected PGPInvalidKeyError for key revocation")

    def test_rejects_subkey_revocation_packet(self):
        try:
            _load_pub(_with_subkey_sig_type(RSA_SUBKEY_PUB, 0x28))
        except PGPInvalidKeyError:
            return
        self.fail("Expected PGPInvalidKeyError for subkey revocation")

    def test_rejects_designated_revoker(self):
        extra = bytes([2, 5, 0x80])
        try:
            _load_pub(_with_first_key_unhashed(VALID_PUBLIC_KEY, extra))
        except PGPInvalidKeyError:
            return
        self.fail("Expected PGPInvalidKeyError for designated revoker")

    def test_rejects_expiring_self_signature(self):
        extra = bytes([5, 3]) + (86400).to_bytes(4, "big")
        try:
            _load_pub(_with_first_key_unhashed(VALID_PUBLIC_KEY, extra))
        except PGPInvalidKeyError:
            return
        self.fail("Expected PGPInvalidKeyError for expiring self-signature")

    def test_rejects_expiring_subkey_binding(self):
        extra = bytes([5, 3]) + (86400).to_bytes(4, "big")
        try:
            _load_pub(_with_subkey_unhashed(RSA_SUBKEY_PUB, extra))
        except PGPInvalidKeyError:
            return
        self.fail("Expected PGPInvalidKeyError for expiring subkey binding")


class Ed25519VerifyTest(TestCase):
    def test_rfc8032_empty_message(self):
        self.assertTrue(verify_ed25519(ED25519_PK, b"", ED25519_SIG))

    def test_rejects_wrong_payload(self):
        self.assertFalse(verify_ed25519(ED25519_PK, b"x", ED25519_SIG))

    def test_rejects_flipped_signature_bit(self):
        bad = bytes([ED25519_SIG[0] ^ 1]) + ED25519_SIG[1:]
        self.assertFalse(verify_ed25519(ED25519_PK, b"", bad))


class RSAVerifyTest(TestCase):
    def test_pkcs1_v15_sha256(self):
        self.assertTrue(verify_rsa((RSA_N, RSA_E), RSA_PAYLOAD, RSA_SIG))

    def test_rejects_wrong_payload(self):
        self.assertFalse(verify_rsa((RSA_N, RSA_E), b"other", RSA_SIG))

    def test_rejects_flipped_signature_bit(self):
        bad = bytes([RSA_SIG[0] ^ 1]) + RSA_SIG[1:]
        self.assertFalse(verify_rsa((RSA_N, RSA_E), RSA_PAYLOAD, bad))

    def test_verify_digest_sha256(self):
        digest = hashlib.sha256(RSA_PAYLOAD).digest()
        self.assertTrue(
            verify_rsa_digest((RSA_N, RSA_E), digest, RSA_SIG, "SHA-256")
        )
        self.assertFalse(
            verify_rsa_digest((RSA_N, RSA_E), digest, RSA_SIG, "SHA-512")
        )

    def test_rejects_oversized_modulus(self):
        n = (1 << (8 * (MAX_RSA_MODULUS_BYTES + 1))) - 1
        digest = b"\x00" * 32
        self.assertFalse(
            verify_rsa_digest((n, RSA_E), digest, b"\x00" * 32, "SHA-256")
        )


def _write_pgp_file(name: str, data) -> str:
    os.makedirs(TEST_DIR, exist_ok=True)
    path = TEST_DIR + "/" + name
    if isinstance(data, str):
        data = data.encode()
    with open(path, "wb") as f:
        f.write(data)
    return path


def _load_key(armored):
    return _load_pub(armored)


def _verify_sig(armored, sig, companion=None, sig_name="SHA256SUMS.asc"):
    _fingerprint, signing_keys = _load_key(armored)
    fname = _write_pgp_file(sig_name, sig)
    companion_factory = None
    if companion is not None:
        companion_path = _write_pgp_file(companion_filename(sig_name), companion)
        companion_factory = lambda: iter_file_chunks(companion_path)
    kind, value = verify_signed_checksums(
        signing_keys,
        lambda: iter_file_chunks(fname),
        companion_factory,
        fname,
    )
    return kind, value


class OpenPGPSignatureTest(TestCase):
    def test_ed25519_clearsign(self):
        kind, value = _verify_sig(ED_PUB, ED_CLEARSIGN)
        self.assertEqual(kind, KIND_CHECKSUM_FILES)
        self.assertEqual(len(value), 2)
        self.assertEqual(value[0][1], "initial_firmware_v1.10.5.bin")

    def test_ed25519_detached_armor(self):
        kind, value = _verify_sig(ED_PUB, ED_DETACH, SHA256SUMS.encode())
        self.assertEqual(kind, KIND_CHECKSUM_FILES)
        names = [name for _digest, name in value]
        self.assertIn("specter_upgrade_v1.10.5.bin", names)

    def test_rejects_binary_signature(self):
        try:
            _verify_sig(ED_PUB, ED_DETACH_SIG, SHA256SUMS.encode(), "SHA256SUMS.sig")
        except PGPError as e:
            self.assertEqual(str(e), SIG_INVALID_MSG)
        else:
            self.fail("Expected invalid signature for binary .sig")

    def test_rsa_clearsign_sha256(self):
        kind, value = _verify_sig(RSA_PUB, RSA_CLEARSIGN)
        self.assertEqual(kind, KIND_CHECKSUM_FILES)
        self.assertEqual(len(value), 2)

    def test_rsa_detached(self):
        kind, value = _verify_sig(RSA_PUB, RSA_DETACH, SHA256SUMS.encode())
        self.assertEqual(kind, KIND_CHECKSUM_FILES)

    def test_rejects_sha1_clearsign(self):
        try:
            _verify_sig(RSA_PUB, RSA_SHA1)
        except PGPError as e:
            self.assertEqual(str(e), UNKNOWN_HASH_MSG)
        else:
            self.fail("Expected PGPError for SHA1 signed message")

    def test_missing_companion_file(self):
        try:
            _verify_sig(ED_PUB, ED_DETACH)
        except PGPError as e:
            self.assertEqual(str(e), "Missing companion file SHA256SUMS")
        else:
            self.fail("Expected missing companion file")

    def test_rejects_oversized_clearsign_line(self):
        text = ED_CLEARSIGN.decode()
        begin = text.index("\n\n") + 2
        end = text.index("-----BEGIN PGP SIGNATURE-----")
        huge = "x" * (LINE_PROBE_LIMIT + 1) + "\n"
        padded = (text[:begin] + huge + text[end:]).encode()
        try:
            _verify_sig(ED_PUB, padded)
        except PGPError as e:
            self.assertEqual(str(e), SIG_TOO_LARGE_MSG)
        else:
            self.fail("Expected PGPError for oversized clearsign line")

    def test_tampered_huge_clearsign_still_verified_as_mismatch(self):
        text = ED_CLEARSIGN.decode()
        begin = text.index("\n\n") + 2
        end = text.index("-----BEGIN PGP SIGNATURE-----")
        huge = ("x" * 80 + "\n") * ((MAX_TEXT_BYTES // 80) + 2)
        padded = (text[:begin] + huge + text[end:]).encode()
        try:
            _verify_sig(ED_PUB, padded)
        except PGPError as e:
            self.assertEqual(str(e), SIG_BAD_MATCH_MSG)
        else:
            self.fail("Expected signature mismatch for tampered huge payload")

    def test_huge_detached_companion_still_verified_as_mismatch(self):
        try:
            _verify_sig(ED_PUB, ED_DETACH, b"x" * (MAX_TEXT_BYTES + 1))
        except PGPError as e:
            self.assertEqual(str(e), SIG_BAD_MATCH_MSG)
        else:
            self.fail("Expected signature mismatch for wrong huge companion")

    def test_rejects_public_key_as_signature(self):
        try:
            _verify_sig(ED_PUB, VALID_PUBLIC_KEY, sig_name="message_public_key.gpg")
        except PGPError as e:
            self.assertEqual(str(e), SIG_PUBLIC_KEY_MSG)
        else:
            self.fail("Expected public-key-as-signature error")

    def test_signature_from_other_key(self):
        try:
            _verify_sig(ED_PUB, OTHER_DETACH, SHA256SUMS.encode())
        except PGPError as e:
            self.assertEqual(str(e), SIG_OTHER_KEY_MSG)
        else:
            self.fail("Expected other-key error")

    def test_rejects_signature_expiration(self):
        for hashed in (False, True):
            expired = _with_sig_expire(ED_DETACH, hashed=hashed)
            try:
                _verify_sig(ED_PUB, expired, SHA256SUMS.encode())
            except PGPSignatureExpirationError as e:
                self.assertEqual(str(e), SIG_EXPIRE_MSG)
            else:
                self.fail(
                    "Expected PGPSignatureExpirationError hashed=%s" % hashed
                )

    def test_rejects_non_document_signature_type(self):
        mutated = _with_document_sig_type(ED_DETACH, 0x10)
        try:
            _verify_sig(ED_PUB, mutated, SHA256SUMS.encode())
        except PGPError as e:
            self.assertEqual(str(e), SIG_INVALID_MSG)
        else:
            self.fail("Expected invalid signature for certification type")

    def test_rejects_clearsign_binary_signature_type(self):
        text = ED_CLEARSIGN.decode()
        marker = "-----BEGIN PGP SIGNATURE-----"
        idx = text.index(marker)
        mutated = _with_document_sig_type(text[idx:].encode(), 0x00)
        combined = (text[:idx] + mutated.decode()).encode()
        try:
            _verify_sig(ED_PUB, combined)
        except PGPError as e:
            self.assertEqual(str(e), SIG_INVALID_MSG)
        else:
            self.fail("Expected invalid signature for binary clearsign type")

    def test_tampered_clearsign_payload(self):
        tampered = ED_CLEARSIGN.replace(b"b46b6b3e", b"aaaaaaaa")
        try:
            _verify_sig(ED_PUB, tampered)
        except PGPError as e:
            self.assertEqual(str(e), SIG_BAD_MATCH_MSG)
        else:
            self.fail("Expected signature mismatch")

    def test_companion_filename(self):
        self.assertEqual(companion_filename("/sd/SHA256SUMS.asc"), "SHA256SUMS")
        self.assertEqual(companion_filename("SHA256SUMS.sig"), "SHA256SUMS")

    def test_unescape_without_dash_keeps_payload(self):
        text = "Don't trust, verify."
        self.assertIs(_unescape_line(text), text)

    def test_unescape_dash_escaped_line(self):
        self.assertEqual(_unescape_line("- --hello"), "--hello")
        self.assertEqual(_unescape_line("world"), "world")

    def test_rsa_signing_subkey(self):
        fingerprint, signing_keys = _load_pub(
            RSA_SUBKEY_PUB
        )
        # Certify-only primary; the document signature is from the signing subkey.
        self.assertEqual(len(signing_keys), 1)
        self.assertNotEqual(signing_keys[0][0], fingerprint)
        sig_path = _write_pgp_file("SHA256SUMS.asc", RSA_SUBKEY_DETACH)
        companion_path = _write_pgp_file("SHA256SUMS", SHA256SUMS.encode())
        kind, value = verify_signed_checksums(
            signing_keys,
            lambda: iter_file_chunks(sig_path),
            lambda: iter_file_chunks(companion_path),
            sig_path,
        )
        self.assertEqual(kind, KIND_CHECKSUM_FILES)
        self.assertEqual(len(value), 2)


class ChecksumListTest(TestCase):
    def test_parse_gnu_and_binary_lines(self):
        text = (
            SHA256SUMS
            + "d207f6d3750e3aacbc98080581934b8d0ebe52eb833f341e0e249d96c0c711d6 *unsigned.bin\n"
        )
        entries = parse_checksum_list(text)
        self.assertEqual(entries[2][1], "unsigned.bin")

    def test_empty_payload(self):
        kind, value = parsed_signed_message("   \n")
        self.assertEqual(kind, KIND_EMPTY)
        self.assertIsNone(value)

    def test_ascii_when_not_checksum_list(self):
        kind, value = parsed_signed_message("hello world\n")
        self.assertEqual(kind, KIND_TEXT)
        self.assertEqual(value, "hello world")

    def test_binary_payload(self):
        kind, value = parsed_signed_message(b"\xff\x00secret")
        self.assertEqual(kind, KIND_BINARY)
        self.assertIsNone(value)

    def test_long_ascii_is_still_ascii(self):
        text = "a" * 1000
        kind, value = parsed_signed_message(text)
        self.assertEqual(kind, KIND_TEXT)
        self.assertEqual(len(value), 1000)

    def test_long_text_stops_accumulating(self):
        kind, value = parsed_signed_message("a" * (MAX_TEXT_BYTES + 50))
        self.assertEqual(kind, KIND_LONG_TEXT)
        self.assertIsNone(value)

    def test_huge_line_without_newline_is_bounded(self):
        kind, value = parsed_signed_message("a" * (MAX_CHECKSUM_LIST_BYTES + 200))
        self.assertEqual(kind, KIND_LONG_TEXT)
        self.assertIsNone(value)

    def test_long_checksum_list(self):
        digest = "b" * 64
        # Each line is 64 + name; names long enough to exceed 4k of hashes+names.
        name = "n" * 200
        lines = []
        total = 0
        while total <= MAX_CHECKSUM_LIST_BYTES:
            lines.append(digest + "  " + name)
            total += 64 + len(name)
        kind, value = parsed_signed_message("\n".join(lines) + "\n")
        self.assertEqual(kind, KIND_LONG_CHECKSUM_FILES)
        self.assertIsNone(value)

    def test_slash_in_checksum_filename(self):
        text = (
            "b46b6b3ea256bc9f9d4da4250c0d6ffdfc1800cbb44a8845810e045c5e8cae01"
            "  dir/firmware.bin\n"
        )
        try:
            parsed_signed_message(text)
        except PGPSlashInFilenameError:
            return
        self.fail("Expected PGPSlashInFilenameError")

    def test_verify_missing_and_corrupt(self):
        entries = parse_checksum_list(SHA256SUMS)
        files = {
            "initial_firmware_v1.10.5.bin": entries[0][0],
            "specter_upgrade_v1.10.5.bin": "00" * 32,
        }

        def sha256_of(name):
            return files.get(name)

        verified, missing, corrupt = verify_checksum_files(entries, sha256_of)
        self.assertEqual(verified, ["initial_firmware_v1.10.5.bin"])
        self.assertEqual(missing, [])
        self.assertEqual(corrupt, ["specter_upgrade_v1.10.5.bin"])

        def missing_fn(name):
            return None

        verified, missing, corrupt = verify_checksum_files(entries, missing_fn)
        self.assertEqual(verified, [])
        self.assertEqual(
            missing,
            [
                "initial_firmware_v1.10.5.bin",
                "specter_upgrade_v1.10.5.bin",
            ],
        )
        self.assertEqual(corrupt, [])

    def test_unverified_files_excludes_pgp_and_listed(self):
        extras = unverified_files(
            [
                "seedsigner_pubkey.gpg",
                "SHA256SUMS.asc",
                "SHA256SUMS",
                "notes.txt",
                "initial_firmware_v1.10.5.bin",
            ],
            ["initial_firmware_v1.10.5.bin"],
            ["seedsigner_pubkey.gpg", "SHA256SUMS.asc", "SHA256SUMS"],
        )
        self.assertEqual(extras, ["notes.txt"])

