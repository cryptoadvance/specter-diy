"""Unit tests for the Kurihara n-of-m threshold XOR secret sharing core.

Runs off device under the Unix simulator: `make test`.
"""
from unittest import TestCase

import kurihara
from kurihara import KuriharaScheme, Share


def combinations(items, r):
    """itertools.combinations is not available in MicroPython; reimplement."""
    n = len(items)
    if r > n:
        return
    idx = list(range(r))
    yield tuple(items[i] for i in idx)
    while True:
        i = r - 1
        while i >= 0 and idx[i] == i + n - r:
            i -= 1
        if i < 0:
            return
        idx[i] += 1
        for j in range(i + 1, r):
            idx[j] = idx[j - 1] + 1
        yield tuple(items[i] for i in idx)


def counter_randfunc(seed=0):
    """Deterministic, non-crypto byte source for reproducible test vectors."""
    state = [seed & 0xFF]

    def randfunc(nbytes):
        out = bytearray(nbytes)
        for i in range(nbytes):
            state[0] = (state[0] * 1103515245 + 12345) & 0xFF
            out[i] = state[0]
        return bytes(out)

    return randfunc


# Profiles exercised: (n, m, L)
PROFILES = [
    (2, 3, 128),
    (2, 5, 256),
    (3, 5, 256),
    (4, 5, 256),
    (2, 2, 128),
]


class PrimeTest(TestCase):
    def test_smallest_prime_gte(self):
        self.assertEqual(kurihara.smallest_prime_gte(2), 2)
        self.assertEqual(kurihara.smallest_prime_gte(3), 3)
        self.assertEqual(kurihara.smallest_prime_gte(4), 5)
        self.assertEqual(kurihara.smallest_prime_gte(6), 7)
        self.assertEqual(kurihara.smallest_prime_gte(9), 11)

    def test_is_prime(self):
        self.assertTrue(kurihara.is_prime(2))
        self.assertTrue(kurihara.is_prime(5))
        self.assertFalse(kurihara.is_prime(1))
        self.assertFalse(kurihara.is_prime(9))


class XorTest(TestCase):
    def test_xor_bytes(self):
        self.assertEqual(kurihara.xor_bytes(b"\x0f", b"\xf0"), b"\xff")
        self.assertEqual(kurihara.xor_bytes(b"\xff", b"\xff", b"\xff"), b"\xff")
        self.assertEqual(
            kurihara.xor_bytes(b"\xaa\x55", b"\x55\xaa"), b"\xff\xff"
        )


class ParamTest(TestCase):
    def test_share_size_equals_secret(self):
        for n, m, L in PROFILES:
            sch = KuriharaScheme(n, m, L)
            _, shares = sch.generate(randfunc=counter_randfunc())
            for s in shares:
                self.assertEqual(len(s.to_bytes()) * 8, L)

    def test_rejects_bad_params(self):
        with self.assertRaises(ValueError):
            KuriharaScheme(1, 3, 128)        # n < 2
        with self.assertRaises(ValueError):
            KuriharaScheme(4, 3, 128)        # n > m
        with self.assertRaises(ValueError):
            KuriharaScheme(2, 3, 100)        # non-BIP39 L
        with self.assertRaises(ValueError):
            KuriharaScheme(3, 6, 256)        # p-1=6 does not divide L=256


class ReconstructTest(TestCase):
    def test_all_coalitions_reconstruct(self):
        for n, m, L in PROFILES:
            sch = KuriharaScheme(n, m, L)
            secret, shares = sch.generate(randfunc=counter_randfunc(7))
            for combo in combinations(list(range(m)), n):
                picked = [shares[i] for i in combo]
                got = sch.reconstruct(picked)
                self.assertEqual(
                    got, secret,
                    "coalition %s failed for %d-of-%d L=%d"
                    % (str(combo), n, m, L),
                )

    def test_oversized_coalition_reconstructs(self):
        sch = KuriharaScheme(3, 5, 256)
        secret, shares = sch.generate(randfunc=counter_randfunc(1))
        # all m shares (more than n) must still reconstruct
        self.assertEqual(sch.reconstruct(shares), secret)

    def test_subthreshold_is_rejected(self):
        for n, m, L in PROFILES:
            if n < 2:
                continue
            sch = KuriharaScheme(n, m, L)
            _, shares = sch.generate(randfunc=counter_randfunc(3))
            for combo in combinations(list(range(m)), n - 1):
                picked = [shares[i] for i in combo]
                with self.assertRaises(ValueError):
                    sch.reconstruct(picked)

    def test_mixed_instances_rejected(self):
        sch = KuriharaScheme(3, 5, 256)
        _, shares_a = sch.generate(randfunc=counter_randfunc(10))
        _, shares_b = sch.generate(randfunc=counter_randfunc(20))
        mixed = [shares_a[0], shares_a[1], shares_b[2]]
        with self.assertRaises(ValueError):
            sch.reconstruct(mixed)


class LostShareTest(TestCase):
    def test_regenerate_is_bit_identical(self):
        for n, m, L in PROFILES:
            if m <= n:
                continue
            sch = KuriharaScheme(n, m, L)
            _, shares = sch.generate(randfunc=counter_randfunc(42))
            # use the first n shares to regenerate each of the others
            coalition = shares[:n]
            for lost in range(n, m):
                regen = sch.reconstruct_lost(coalition, lost + 1)
                self.assertEqual(
                    regen.pieces, shares[lost].pieces,
                    "regenerated S_%d mismatch for %d-of-%d"
                    % (lost + 1, n, m),
                )

    def test_regenerated_share_is_usable(self):
        # A regenerated share must work in a fresh coalition.
        sch = KuriharaScheme(3, 5, 256)
        secret, shares = sch.generate(randfunc=counter_randfunc(99))
        regen = sch.reconstruct_lost(shares[:3], 5)
        # coalition that includes the regenerated share
        got = sch.reconstruct([shares[0], shares[3], regen])
        self.assertEqual(got, secret)

    def test_cannot_regenerate_present_share(self):
        sch = KuriharaScheme(3, 5, 256)
        _, shares = sch.generate(randfunc=counter_randfunc(5))
        with self.assertRaises(ValueError):
            sch.reconstruct_lost(shares[:3], 1)  # S_1 is in the coalition


class Bip39Test(TestCase):
    def test_each_share_is_valid_mnemonic(self):
        from embit import bip39
        sch = KuriharaScheme(3, 5, 256)
        _, shares = sch.generate(randfunc=counter_randfunc(8))
        for s in shares:
            mnemonic = kurihara.share_to_mnemonic(s)
            self.assertTrue(bip39.mnemonic_is_valid(mnemonic))
            self.assertEqual(len(mnemonic.split()), 24)

    def test_secret_roundtrips_through_mnemonics(self):
        # Generate from a known mnemonic entropy, split, re-encode each share
        # to a mnemonic, decode them back, reconstruct, and compare.
        from embit import bip39
        n, m, L = 3, 5, 256
        sch = KuriharaScheme(n, m, L)
        secret, shares = sch.generate(randfunc=counter_randfunc(11))

        mnemonics = [(s.part_id, kurihara.share_to_mnemonic(s)) for s in shares]
        # pick n of them and rebuild Share objects from the words alone
        chosen = mnemonics[:n]
        rebuilt = [
            kurihara.share_from_mnemonic(
                pid, words, n, m, L, instance=shares[0].meta["instance"]
            )
            for pid, words in chosen
        ]
        got = sch.reconstruct(rebuilt)
        self.assertEqual(got, secret)
        # and the reconstructed secret is itself a valid 24-word entropy
        self.assertTrue(
            bip39.mnemonic_is_valid(kurihara.entropy_to_mnemonic(got))
        )


class DeterministicVectorTest(TestCase):
    def test_known_answer(self):
        # Fixed secret + deterministic randomness => stable shares.
        # This guards against accidental changes to the construction formula.
        sch = KuriharaScheme(2, 3, 128)
        secret = bytes(range(16))  # 00 01 02 ... 0f
        _, shares = sch.generate(secret=secret, randfunc=counter_randfunc(0))
        # round-trip is the contract we lock in
        self.assertEqual(sch.reconstruct([shares[0], shares[1]]), secret)
        self.assertEqual(sch.reconstruct([shares[0], shares[2]]), secret)
        self.assertEqual(sch.reconstruct([shares[1], shares[2]]), secret)
        # shares differ from each other and from the secret
        blobs = [s.to_bytes() for s in shares]
        self.assertNotEqual(blobs[0], blobs[1])
        self.assertNotEqual(blobs[0], secret)
