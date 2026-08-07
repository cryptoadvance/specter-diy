import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase

import rng


class RNGSanityCheckTest(TestCase):
    def setUp(self):
        self.original_get_trng_bytes = rng.get_trng_bytes
        self.original_entropy_pool = rng.entropy_pool

    def tearDown(self):
        rng.get_trng_bytes = self.original_get_trng_bytes
        rng.entropy_pool = self.original_entropy_pool

    def test_looks_dead_ignores_short_repeated_buffers(self):
        self.assertFalse(rng._looks_dead(b""))
        self.assertFalse(rng._looks_dead(b"\x00"))
        self.assertFalse(rng._looks_dead(b"\x00\x00\x00"))
        self.assertFalse(rng._looks_dead(b"\xff\xff\xff"))

    def test_looks_dead_rejects_repeated_buffers_from_four_bytes(self):
        self.assertTrue(rng._looks_dead(b"\x00\x00\x00\x00"))
        self.assertTrue(rng._looks_dead(b"\xff\xff\xff\xff"))
        self.assertTrue(rng._looks_dead(b"\x11" * 32))

    def test_looks_dead_allows_non_repeated_buffers(self):
        self.assertFalse(rng._looks_dead(b"\x00\x00\x00\x01"))
        self.assertFalse(rng._looks_dead(bytes(range(32))))

    def test_get_random_bytes_raises_before_feeding_dead_output(self):
        rng.entropy_pool = b"A" * 64
        rng.get_trng_bytes = lambda nbytes: b"\x00" * nbytes

        try:
            rng.get_random_bytes(32)
        except rng.RNGError:
            pass
        else:
            self.fail("Expected RNGError for repeated TRNG output")

        self.assertEqual(rng.entropy_pool, b"A" * 64)

    def test_get_random_bytes_keeps_one_byte_requests_working(self):
        rng.get_trng_bytes = lambda nbytes: b"\x00" * nbytes
        self.assertEqual(len(rng.get_random_bytes(1)), 1)

    def test_get_random_bytes_returns_requested_length_for_live_output(self):
        rng.get_trng_bytes = lambda nbytes: bytes(range(nbytes))
        self.assertEqual(len(rng.get_random_bytes(32)), 32)
