from binascii import unhexlify
from unittest import TestCase

from apps.wallets.wallet import Wallet
from embit import bip32
from embit.psbt import DerivationPath


class WalletPartialDerivationTest(TestCase):

    def setUp(self):
        xpub = (
            "[8cce63f8/84h/1h/0h]"
            "tpubDCZWxJ6kKqRHep5a2XycxrXRaTES1vs3ysfV7sdv5uhkaEgxBEdVbyQT46m3NcaLJqVNd41TYqDyQfvweLLXGmkxdHRnhxuJPf7BAWMXni2"
            "/<0;1>/*"
        )
        self.wallet = Wallet.parse("wpkh(%s)" % xpub)

    def _pub_at(self, branch, index):
        desc = self.wallet.descriptor.derive(index, branch_index=branch)
        return desc.keys[0].get_public_key()

    def test_short_derivation_with_zero_fingerprint(self):
        derivation = DerivationPath(
            unhexlify("00000000"),
            bip32.parse_path("m/0/3"),
        )

        self.assertEqual(
            self.wallet.get_derivation({self._pub_at(0, 3): derivation}),
            (3, 0),
        )

    def test_short_derivation_with_xpub_fingerprint(self):
        derivation = DerivationPath(
            unhexlify("8cce63f8"),
            bip32.parse_path("m/1/4"),
        )

        self.assertEqual(
            self.wallet.get_derivation({self._pub_at(1, 4): derivation}),
            (4, 1),
        )

    def test_short_derivation_must_match_psbt_pubkey(self):
        derivation = DerivationPath(
            unhexlify("00000000"),
            bip32.parse_path("m/0/3"),
        )

        self.assertIsNone(
            self.wallet.get_derivation({self._pub_at(1, 3): derivation}),
        )

    def test_short_derivation_is_limited_to_two_non_hardened_indexes(self):
        derivation = DerivationPath(
            unhexlify("00000000"),
            bip32.parse_path("m/0/0/3"),
        )

        self.assertIsNone(
            self.wallet.get_derivation({self._pub_at(0, 3): derivation}),
        )
