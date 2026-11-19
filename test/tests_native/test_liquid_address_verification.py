import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase

from embit import ec, script
from embit.liquid.addresses import address as liquid_address
from apps.wallets.liquid.manager import LWalletManager


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

    def test_confidential_and_unconfidential_forms_match(self):
        self.assertTrue(
            self.manager.addresses_match(
                self.first_confidential_address, self.unconfidential_address
            )
        )
        self.assertTrue(
            self.manager.addresses_match(
                self.unconfidential_address, self.first_confidential_address
            )
        )

    def test_identical_confidential_addresses_match(self):
        self.assertTrue(
            self.manager.addresses_match(
                self.first_confidential_address, self.first_confidential_address
            )
        )

    def test_malformed_liquid_address_does_not_match(self):
        self.assertFalse(
            self.manager.addresses_match(self.first_confidential_address, "lq1invalid")
        )
