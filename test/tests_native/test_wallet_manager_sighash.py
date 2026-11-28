import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase
import gc

from embit.transaction import SIGHASH
from tests.util import get_keystore, get_wallets_app, clear_testdir
from apps.wallets.manager import SIGHASH_NAMES
from apps.wallets.wallet import WalletError


class FakeInput:
    """Minimal stand-in for embit InputScope for sighash-resolution tests."""

    def __init__(self, is_taproot=False, sighash_type=None):
        self.is_taproot = is_taproot
        self.sighash_type = sighash_type


class SighashNamesTest(TestCase):
    def test_default_is_named(self):
        self.assertEqual(SIGHASH_NAMES[SIGHASH.DEFAULT], "DEFAULT")

    def test_invalid_default_anyonecanpay_is_not_accepted(self):
        # DEFAULT (0x00) | ANYONECANPAY (0x80) == 0x80 is not a valid
        # BIP341 sighash and must not be a recognised value.
        self.assertNotIn(SIGHASH.DEFAULT | SIGHASH.ANYONECANPAY, SIGHASH_NAMES)
        self.assertNotIn(0x80, SIGHASH_NAMES)

    def test_all_none_single_anyonecanpay_are_accepted(self):
        for sh in (SIGHASH.ALL, SIGHASH.NONE, SIGHASH.SINGLE):
            self.assertIn(sh | SIGHASH.ANYONECANPAY, SIGHASH_NAMES)


class DefaultSighashTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.manager = get_wallets_app(self.keystore, "regtest").manager

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def test_taproot_input_defaults_to_sighash_default(self):
        self.assertEqual(
            self.manager.default_sighash(FakeInput(is_taproot=True)),
            SIGHASH.DEFAULT,
        )

    def test_non_taproot_input_keeps_manager_default(self):
        self.assertEqual(
            self.manager.default_sighash(FakeInput(is_taproot=False)),
            self.manager.DEFAULT_SIGHASH,
        )
        self.assertEqual(self.manager.DEFAULT_SIGHASH, SIGHASH.ALL)

    def test_get_sighash_info_rejects_bare_0x80(self):
        with self.assertRaises(WalletError):
            self.manager.get_sighash_info(0x80)


class LiquidDefaultSighashTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.manager = get_wallets_app(self.keystore, "elementsregtest").manager

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def test_liquid_never_uses_bare_default(self):
        # Liquid has no taproot path; the default stays ALL | RANGEPROOF
        # regardless of the input, and a bare 0 stays unknown/rejected.
        self.assertEqual(
            self.manager.default_sighash(FakeInput(is_taproot=True)),
            self.manager.DEFAULT_SIGHASH,
        )
        with self.assertRaises(WalletError):
            self.manager.get_sighash_info(SIGHASH.DEFAULT)
