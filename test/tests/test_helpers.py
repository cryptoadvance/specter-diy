from unittest import TestCase
from helpers import conv_time, consteq, aead_encrypt, aead_decrypt

class HelpersTest(TestCase):
    def test_consteq(self):
        """consteq() must agree with regular equality on all these cases (L6)"""
        self.assertTrue(consteq(b"", b""))
        self.assertTrue(consteq(b"abcdef", b"abcdef"))
        # mismatch in the first byte
        self.assertFalse(consteq(b"abcdef", b"xbcdef"))
        # mismatch in the last byte
        self.assertFalse(consteq(b"abcdef", b"abcdex"))
        # mismatch in the middle
        self.assertFalse(consteq(b"abcdef", b"abXdef"))
        # different lengths, same prefix
        self.assertFalse(consteq(b"abc", b"abcd"))
        self.assertFalse(consteq(b"abcd", b"abc"))
        # different lengths, one empty
        self.assertFalse(consteq(b"", b"a"))
        self.assertFalse(consteq(b"a", b""))

    def test_aead_roundtrip(self):
        """Valid storage MAC still authenticates and decrypts (L6)"""
        key = b"0" * 32
        adata = b"associated-data"
        plaintext = b"top secret mnemonic"
        ct = aead_encrypt(key, adata, plaintext)
        out_adata, out_plaintext = aead_decrypt(ct, key)
        self.assertEqual(out_adata, adata)
        self.assertEqual(out_plaintext, plaintext)

    def test_aead_rejects_tampered_mac(self):
        """A tampered/invalid storage MAC is still rejected (L6)"""
        key = b"0" * 32
        ct = aead_encrypt(key, b"ad", b"top secret mnemonic")
        # flip the last bit of the MAC
        tampered = ct[:-1] + bytes([ct[-1] ^ 0x01])
        with self.assertRaises(Exception):
            aead_decrypt(tampered, key)

    def test_conv_time(self):
        """Test conv_time function: used for converting nLocktime to human-readable timestamp"""
        self.assertEqual(conv_time(0), (1970, 1, 1, 0, 0, 0, 3, 1))
        # Test day before USA DST start on March 7th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1772841600 + hour * 3600), (2026, 3, 7, hour, 0, 0, 5, 66))
        # Test during USA DST start on March 8th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1772928000 + hour * 3600), (2026, 3, 8, hour, 0, 0, 6, 67))
        # Test day after USA DST start on March 9th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1773014400 + hour * 3600), (2026, 3, 9, hour, 0, 0, 0, 68))
        # Test during Europe DST start on March 29th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1774742400 + hour * 3600), (2026, 3, 29, hour, 0, 0, 6, 88))
        # Test during Europe DST end on October 25th 2026
        for hour in range(24):
            self.assertEqual(conv_time(1792886400 + hour * 3600), (2026, 10, 25, hour, 0, 0, 6, 298))
        # Test day before USA DST end on October 31st 2026
        for hour in range(24):
            self.assertEqual(conv_time(1793404800 + hour * 3600), (2026, 10, 31, hour, 0, 0, 5, 304))
        # Test day during USA DST end on November 1st 2026
        for hour in range(24):
            self.assertEqual(conv_time(1793491200 + hour * 3600), (2026, 11, 1, hour, 0, 0, 6, 305))
        # Test day after USA DST end on November 2nd 2026
        for hour in range(24):
            self.assertEqual(conv_time(1793577600 + hour * 3600), (2026, 11, 2, hour, 0, 0, 0, 306))
