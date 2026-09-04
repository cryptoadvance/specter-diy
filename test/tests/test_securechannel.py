from unittest import TestCase
from keystore.javacard.applets.securechannel import SecureChannel, SecureChannelError
import hashlib
import hmac
import secp256k1
from rng import get_random_bytes
from ucryptolib import aes

AES_BLOCK = 16
IV_SIZE = 16
AES_CBC = 2
MAC_SIZE = 14


def card_encrypt(sc, data):
    """
    Builds a ciphertext the way the real card would encrypt a response
    to the host, using sc's card_aes_key/card_mac_key/iv - i.e. exactly
    what SecureChannel.decrypt() is expected to be able to open.
    """
    d = data + b"\x80"
    if len(d) % AES_BLOCK != 0:
        d += b"\x00" * (AES_BLOCK - (len(d) % AES_BLOCK))
    iv = sc.iv.to_bytes(IV_SIZE, "big")
    crypto = aes(sc.card_aes_key, AES_CBC, iv)
    ct = crypto.encrypt(d)
    h = hmac.new(sc.card_mac_key, digestmod="sha256")
    h.update(iv)
    h.update(ct)
    ct += h.digest()[:MAC_SIZE]
    return ct


def get_channel():
    sc = SecureChannel(applet=None)
    sc.card_aes_key = b"1" * 32
    sc.card_mac_key = b"2" * 32
    sc.iv = 0
    return sc


class SecureChannelDecryptTest(TestCase):
    """
    Regression tests for the L6 constant-time HMAC check in
    SecureChannel.decrypt(). No smartcard/simulator is needed: decrypt()
    only depends on card_aes_key/card_mac_key/iv, which are set directly.
    """

    def test_valid_mac_decrypts(self):
        sc = get_channel()
        ct = card_encrypt(sc, b"hello from card")
        self.assertEqual(sc.decrypt(ct), b"hello from card")

    def test_first_mac_byte_flipped_rejected(self):
        sc = get_channel()
        ct = bytearray(card_encrypt(sc, b"hello from card"))
        ct[-MAC_SIZE] ^= 0xFF
        with self.assertRaises(SecureChannelError):
            sc.decrypt(bytes(ct))

    def test_middle_mac_byte_flipped_rejected(self):
        sc = get_channel()
        ct = bytearray(card_encrypt(sc, b"hello from card"))
        ct[-(MAC_SIZE // 2)] ^= 0xFF
        with self.assertRaises(SecureChannelError):
            sc.decrypt(bytes(ct))

    def test_last_mac_byte_flipped_rejected(self):
        sc = get_channel()
        ct = bytearray(card_encrypt(sc, b"hello from card"))
        ct[-1] ^= 0xFF
        with self.assertRaises(SecureChannelError):
            sc.decrypt(bytes(ct))

    def test_tampered_ciphertext_rejected(self):
        """A flipped ciphertext byte must be caught by the MAC check,
        never silently decrypted to different plaintext."""
        sc = get_channel()
        ct = bytearray(card_encrypt(sc, b"hello from card"))
        ct[0] ^= 0xFF
        with self.assertRaises(SecureChannelError):
            sc.decrypt(bytes(ct))

    def test_wrong_key_rejected(self):
        sc = get_channel()
        ct = card_encrypt(sc, b"hello from card")
        wrong = get_channel()
        wrong.card_mac_key = b"3" * 32
        with self.assertRaises(SecureChannelError):
            wrong.decrypt(ct)


def _decode(payload):
    """Reverse of keystore.javacard.util.encode(): bytes([len]) + data"""
    l = payload[0]
    return payload[1:1 + l]


class MockCardApplet:
    """
    Stands in for the real smartcard applet during open(). Simulates the
    card's side of the ee/se handshake using genuine secp256k1 operations
    (real ECDH + real ECDSA signatures over the card's static key), so
    these tests exercise the same crypto path as the real protocol -
    only the transport (self.applet.request) is mocked.
    """

    def __init__(self, card_static_secret, tamper_hmac=False, tamper_sig=False):
        self.card_static_secret = card_static_secret
        self.tamper_hmac = tamper_hmac
        self.tamper_sig = tamper_sig

    def _sign(self, data):
        sig = secp256k1.ecdsa_sign(hashlib.sha256(data).digest(), self.card_static_secret)
        der = secp256k1.ecdsa_signature_serialize_der(sig)
        if self.tamper_sig:
            der = bytes([der[0] ^ 0xFF]) + der[1:]
        return der

    def request(self, payload):
        cmd, body = payload[:4], payload[4:]
        if cmd == SecureChannel.OPEN_EE:
            host_pub_bytes = _decode(body)
            host_pub = secp256k1.ec_pubkey_parse(host_pub_bytes)

            card_secret = get_random_bytes(32)
            card_pub = secp256k1.ec_pubkey_create(card_secret)
            card_pub_bytes = secp256k1.ec_pubkey_serialize(card_pub, secp256k1.EC_UNCOMPRESSED)

            shared_point = secp256k1.ec_pubkey_parse(host_pub_bytes)
            secp256k1.ec_pubkey_tweak_mul(shared_point, card_secret)
            shared_secret = hashlib.sha256(
                secp256k1.ec_pubkey_serialize(shared_point)[1:33]
            ).digest()

            card_side = SecureChannel(applet=None)
            card_side.derive_keys(shared_secret)

            h = hmac.new(card_side.card_mac_key, digestmod="sha256")
            h.update(card_pub_bytes)
            mac = h.digest()[:MAC_SIZE]
            if self.tamper_hmac:
                mac = bytes([mac[0] ^ 0xFF]) + mac[1:]

            der = self._sign(card_pub_bytes + mac)
            return card_pub_bytes + mac + der

        elif cmd == SecureChannel.OPEN_SE:
            host_pub_bytes = _decode(body)

            card_static_pub = secp256k1.ec_pubkey_create(self.card_static_secret)
            shared_point = secp256k1.ec_pubkey_parse(host_pub_bytes)
            secp256k1.ec_pubkey_tweak_mul(shared_point, self.card_static_secret)
            shared_secret = secp256k1.ec_pubkey_serialize(shared_point)[1:33]

            nonce_card = get_random_bytes(32)
            secret_with_nonces = hashlib.sha256(shared_secret + nonce_card).digest()
            card_side = SecureChannel(applet=None)
            card_side.derive_keys(secret_with_nonces)

            h = hmac.new(card_side.card_mac_key, digestmod="sha256")
            h.update(nonce_card)
            mac = h.digest()[:MAC_SIZE]
            if self.tamper_hmac:
                mac = bytes([mac[0] ^ 0xFF]) + mac[1:]

            der = self._sign(nonce_card + mac)
            return nonce_card + mac + der

        raise AssertionError("Unexpected request in mock applet: %r" % cmd)


class SecureChannelOpenTest(TestCase):
    """
    Regression tests for the L6 constant-time HMAC checks in
    SecureChannel.open() (both "ee" and "se" handshake modes). A mock
    applet simulates the card's side with genuine secp256k1 ECDH/ECDSA,
    so a tampered HMAC is rejected for the same reason a tampered
    signature would be - not because the mock is unrealistic.
    """

    def test_open_ee_succeeds_with_valid_card_response(self):
        card_secret = get_random_bytes(32)
        applet = MockCardApplet(card_secret)
        sc = SecureChannel(applet)
        sc.card_pubkey = secp256k1.ec_pubkey_create(card_secret)
        sc.open(mode="ee")
        self.assertTrue(sc.is_open)

    def test_open_ee_tampered_hmac_rejected(self):
        card_secret = get_random_bytes(32)
        applet = MockCardApplet(card_secret, tamper_hmac=True)
        sc = SecureChannel(applet)
        sc.card_pubkey = secp256k1.ec_pubkey_create(card_secret)
        with self.assertRaises(SecureChannelError):
            sc.open(mode="ee")
        self.assertFalse(sc.is_open)

    def test_open_se_succeeds_with_valid_card_response(self):
        card_secret = get_random_bytes(32)
        applet = MockCardApplet(card_secret)
        sc = SecureChannel(applet)
        sc.card_pubkey = secp256k1.ec_pubkey_create(card_secret)
        sc.open(mode="se")
        self.assertTrue(sc.is_open)

    def test_open_se_tampered_hmac_rejected(self):
        card_secret = get_random_bytes(32)
        applet = MockCardApplet(card_secret, tamper_hmac=True)
        sc = SecureChannel(applet)
        sc.card_pubkey = secp256k1.ec_pubkey_create(card_secret)
        with self.assertRaises(SecureChannelError):
            sc.open(mode="se")
        self.assertFalse(sc.is_open)
