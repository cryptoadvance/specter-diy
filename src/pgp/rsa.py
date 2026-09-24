# RSA PKCS#1 v1.5 signature verification.
#
# DigestInfo prefixes and EMSA-PKCS1-v1_5 encoding follow RFC 8017 and the
# verify path of python-rsa:
# https://github.com/sybrenstuvel/python-rsa/blob/main/rsa/pkcs1.py
# https://www.rfc-editor.org/rfc/rfc8017#section-9.2
#
# Copyright 2011 Sybren A. Stüvel <sybren@stuvel.eu>
# Licensed under the Apache License, Version 2.0.

from binascii import unhexlify

from .base import MAX_RSA_EXPONENT_BYTES, MAX_RSA_MODULUS_BYTES


# ASN.1 DigestInfo prefixes from RFC 8017 Appendix A / python-rsa HASH_ASN1.
HASH_ASN1 = {
    "SHA-256": b"\x30\x31\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00\x04\x20",
    "SHA-512": b"\x30\x51\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x03\x05\x00\x04\x40",
}

_DIGEST_LEN = {
    "SHA-256": 32,
    "SHA-512": 64,
}

_HASH_NAME_ALIASES = {
    "sha256": "SHA-256",
    "sha512": "SHA-512",
    "SHA256": "SHA-256",
    "SHA512": "SHA-512",
    "SHA-256": "SHA-256",
    "SHA-512": "SHA-512",
}


def _byte_size(n: int) -> int:
    # MicroPython ints do not implement bit_length().
    if n <= 0:
        return 1
    h = "%x" % n
    return (len(h) + 1) // 2


def _int_to_bytes(n: int, length: int) -> bytes:
    if n < 0:
        raise OverflowError
    h = "%x" % n
    if len(h) & 1:
        h = "0" + h
    raw = unhexlify(h)
    if len(raw) > length:
        raise OverflowError
    if len(raw) < length:
        raw = b"\x00" * (length - len(raw)) + raw
    return raw


def _pad_for_signing(message: bytes, target_length: int):
    max_msglength = target_length - 11
    msglength = len(message)
    if msglength > max_msglength:
        return None
    padding_length = target_length - msglength - 3
    return b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + message


def verify_digest(key: tuple, digest: bytes, signature: bytes, hash_name: str) -> bool:
    """
    Return True if signature is a valid PKCS#1 v1.5 signature of digest.

    key is an (n, e) tuple. hash_name is "SHA-256" / "SHA-512" (or aliases).
    signature may be shorter than the modulus (leading zeros stripped).
    """
    try:
        return _verify_digest(key, digest, signature, hash_name)
    except (OverflowError, TypeError, ValueError, MemoryError):
        return False


def _verify_digest(key: tuple, digest: bytes, signature: bytes, hash_name: str) -> bool:
    try:
        n, e = key
    except Exception:
        return False
    if not isinstance(digest, bytes) or not isinstance(signature, bytes):
        return False
    if n <= 0 or e <= 0:
        return False
    hash_name = _HASH_NAME_ALIASES.get(hash_name)
    if hash_name is None or hash_name not in HASH_ASN1:
        return False
    if len(digest) != _DIGEST_LEN[hash_name]:
        return False

    keylength = _byte_size(n)
    if keylength > MAX_RSA_MODULUS_BYTES or _byte_size(e) > MAX_RSA_EXPONENT_BYTES:
        return False
    if len(signature) < keylength:
        signature = b"\x00" * (keylength - len(signature)) + signature
    elif len(signature) > keylength:
        return False

    decrypted = pow(int.from_bytes(signature, "big"), e, n)
    try:
        clearsig = _int_to_bytes(decrypted, keylength)
    except OverflowError:
        return False

    expected = _pad_for_signing(HASH_ASN1[hash_name] + digest, keylength)
    if expected is None:
        return False
    return expected == clearsig
