import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase

from embit import ec, script
from embit.liquid.addresses import address as liquid_address
from embit.liquid.networks import NETWORKS as LIQUID_NETWORKS
from apps.wallets.liquid.manager import LWalletManager
from apps.wallets.wallet import WalletError


class LiquidAddressVerificationTest(TestCase):
    def setUp(self):
        self.manager = LWalletManager.__new__(LWalletManager)
        self.output_script = script.Script(b"\x00\x14" + b"\x11" * 20)
        self.first_blinding_key = ec.PrivateKey(b"\x00" * 31 + b"\x01").get_public_key()
        self.second_blinding_key = (
            ec.PrivateKey(b"\x00" * 31 + b"\x02").get_public_key()
        )
        self.first_confidential_address = liquid_address(
            self.output_script, self.first_blinding_key
        )
        self.second_confidential_address = liquid_address(
            self.output_script, self.second_blinding_key
        )
        self.unconfidential_address = liquid_address(self.output_script)

    def test_confidential_addresses_with_different_blinding_keys_do_not_match(self):
        self.assertNotEqual(
            self.first_confidential_address, self.second_confidential_address
        )
        self.assertFalse(
            self.manager.addresses_match(
                self.first_confidential_address, self.second_confidential_address
            )
        )
        self.assertIsNone(
            self.manager.address_match_type(
                self.first_confidential_address, self.second_confidential_address
            )
        )

    def test_confidential_and_unconfidential_forms_match(self):
        self.assertTrue(
            self.manager.addresses_match(
                self.first_confidential_address, self.unconfidential_address
            )
        )
        self.assertFalse(
            self.manager.addresses_match(
                self.unconfidential_address, self.first_confidential_address
            )
        )
        self.assertEqual(
            self.manager.address_match_type(
                self.first_confidential_address, self.unconfidential_address
            ),
            "same_script",
        )

    def test_confidential_scan_does_not_match_unconfidential_candidate(self):
        # The target has a blinding key that the wallet's raw address lacks.
        self.assertIsNone(
            self.manager.address_match_type(
                self.unconfidential_address, self.first_confidential_address
            )
        )

    def test_identical_confidential_addresses_match(self):
        self.assertTrue(
            self.manager.addresses_match(
                self.first_confidential_address, self.first_confidential_address
            )
        )
        self.assertEqual(
            self.manager.address_match_type(
                self.first_confidential_address, self.first_confidential_address
            ),
            "exact",
        )

    def test_malformed_liquid_address_does_not_match(self):
        self.assertFalse(
            self.manager.addresses_match(self.first_confidential_address, "lq1invalid")
        )

    def test_liquid_address_validation_accepts_both_address_forms(self):
        self.manager.validate_address(self.first_confidential_address)
        self.manager.validate_address(self.unconfidential_address)

    def test_uppercase_liquid_bech32_addresses_are_accepted(self):
        self.manager.validate_address(self.first_confidential_address.upper())
        self.manager.validate_address(self.unconfidential_address.upper())
        self.assertTrue(
            self.manager.addresses_match(
                self.first_confidential_address.upper(),
                self.first_confidential_address,
            )
        )

    def test_malformed_liquid_address_fails_validation(self):
        with self.assertRaises(WalletError):
            self.manager.validate_address("lq1invalid")

    def test_network_hint_recognizes_elements_regtest_bech32(self):
        address = liquid_address(
            self.output_script, network=LIQUID_NETWORKS["elementsregtest"]
        )

        self.assertEqual(
            self.manager.address_network_hint(address),
            ("elementsregtest", "Liquid Regtest"),
        )

    def test_network_hint_recognizes_liquid_legacy_p2sh(self):
        p2sh_script = script.Script(b"\xa9\x14" + b"\x22" * 20 + b"\x87")
        address = liquid_address(
            p2sh_script, network=LIQUID_NETWORKS["liquidtestnet"]
        )

        self.assertEqual(
            self.manager.address_network_hint(address),
            ("liquidtestnet", "Liquid Testnet"),
        )
