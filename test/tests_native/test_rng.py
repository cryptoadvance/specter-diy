import random
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase

import rng
from errors import BaseError


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

    def test_get_random_bytes_handles_zero_length_requests(self):
        # apps/getrandom.py rejects num_bytes < 0 but permits 0, so a host can
        # reach this: _looks_dead(b"") is False, feed(b"") still advances the
        # pool, and the caller gets an empty result rather than an error
        rng.entropy_pool = b"A" * 64
        rng.get_trng_bytes = lambda nbytes: b""

        self.assertEqual(rng.get_random_bytes(0), b"")
        self.assertNotEqual(rng.entropy_pool, b"A" * 64)

    def test_get_random_bytes_keeps_one_byte_requests_working(self):
        rng.get_trng_bytes = lambda nbytes: b"\x00" * nbytes
        self.assertEqual(len(rng.get_random_bytes(1)), 1)

    def test_get_random_bytes_returns_requested_length_for_live_output(self):
        rng.get_trng_bytes = lambda nbytes: bytes(range(nbytes))
        self.assertEqual(len(rng.get_random_bytes(32)), 32)

    def test_looks_dead_rejects_partially_stalled_output(self):
        # an intermittently stalling peripheral returns mostly-repeated output
        # with a few live bytes - a plain "all bytes equal" test misses this
        self.assertTrue(rng._looks_dead(b"\x00" * 31 + b"\x2a"))
        self.assertTrue(rng._looks_dead(b"\x00" * 26 + bytes(range(1, 7))))

    def test_looks_dead_rejects_majority_stall_that_survives_counting(self):
        # these have enough distinct values to pass a plain distinct-count
        # threshold, but are mostly one repeated byte
        # 16 bytes = 12-word seed entropy: 13 zeros + 3 live bytes
        self.assertTrue(rng._looks_dead(b"\x00" * 13 + bytes(range(1, 4))))
        # 32 bytes = 24-word seed entropy: 25 zeros + 7 live bytes
        self.assertTrue(rng._looks_dead(b"\x00" * 25 + bytes(range(1, 8))))
        # 96 of 128 bytes stalled
        self.assertTrue(rng._looks_dead(b"\x00" * 96 + bytes(range(1, 33))))

    def test_looks_dead_rejects_low_variety_without_a_majority_value(self):
        # no value covers half the buffer, but 8 distinct values in 32 bytes
        # is ~2^-111 for healthy output (expected is ~30)
        self.assertTrue(rng._looks_dead(bytes(range(8)) * 4))
        # 1000 bytes with 40 distinct values - passes any fixed cap of 32
        self.assertTrue(rng._looks_dead(bytes(range(40)) * 25))

    def test_looks_dead_allows_healthy_long_buffers(self):
        # distinct byte values saturate at 256, so the threshold cannot grow
        # with n - 245 distinct values in 1000 bytes is healthy TRNG output
        data = bytes(range(245)) * 4 + bytes(range(20))
        self.assertEqual(len(data), 1000)
        self.assertEqual(len(set(data)), 245)
        self.assertFalse(rng._looks_dead(data))

    def test_looks_dead_passes_healthy_random_output(self):
        # guards against a threshold tight enough to reject healthy hardware.
        # A seeded PRNG rather than os.urandom: the thresholds do have a
        # non-zero false rejection rate (5.96e-8 at 4 bytes, 1.36e-8 at 8,
        # 6.43e-13 at 16), which over enough CI runs would eventually flake.
        # Uniform independent bytes are what the check is specified against,
        # so a fixed stream tests the same property without the dice roll.
        prng = random.Random(0x5EEDBEEF)
        for nbytes in (4, 8, 16, 32, 64, 128, 1000):
            for _ in range(100):
                data = bytes(prng.getrandbits(8) for _ in range(nbytes))
                self.assertFalse(rng._looks_dead(data))

    def test_expected_distinct_matches_the_closed_form(self):
        for nbytes in (1, 4, 8, 16, 32, 64, 128, 256, 512, 1000):
            self.assertEqual(
                rng._expected_distinct(nbytes),
                int(256 * (1 - (255 / 256) ** nbytes)),
            )

    def test_get_random_bytes_checks_trng_on_the_raw_path(self):
        # requests over 64 bytes return TRNG output directly, without mixing
        # in the entropy pool, so the sanity check is the only defence there
        rng.get_trng_bytes = lambda nbytes: b"\x00" * nbytes
        try:
            rng.get_random_bytes(100)
        except rng.RNGError:
            pass
        else:
            self.fail("Expected RNGError for dead TRNG output above 64 bytes")

    def test_get_random_bytes_returns_raw_trng_above_64_bytes(self):
        rng.get_trng_bytes = lambda nbytes: bytes(range(nbytes))
        self.assertEqual(rng.get_random_bytes(100), bytes(range(100)))

    def test_rng_error_is_a_base_error(self):
        # BaseError subclasses get a readable alert in specter.py instead of
        # an "unexpected error" traceback
        self.assertTrue(issubclass(rng.RNGError, BaseError))
        self.assertEqual(rng.RNGError.NAME, "RNG Error")
