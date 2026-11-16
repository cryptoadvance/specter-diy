from unittest import TestCase

from embit import bip39
from helpers import mnemonic_to_seedqr


class SeedQRTest(TestCase):
    def test_seedqr_uses_zero_based_four_digit_indices(self):
        mnemonic = "abandon abuse access zoo"
        self.assertEqual(mnemonic_to_seedqr(mnemonic), "0000000900102047")

    def test_seedqr_round_trips_bip39_word_counts(self):
        for word_count in (12, 18, 24):
            entropy = bytes(word_count * 4 // 3)
            mnemonic = bip39.mnemonic_from_bytes(entropy)
            seedqr = mnemonic_to_seedqr(mnemonic)
            decoded = " ".join(
                bip39.WORDLIST[int(seedqr[i:i + 4])]
                for i in range(0, len(seedqr), 4)
            )
            self.assertEqual(len(seedqr), word_count * 4)
            self.assertEqual(decoded, mnemonic)
            self.assertEqual(bip39.mnemonic_to_bytes(decoded), entropy)
