"""
Deleting a wallet must overwrite its encrypted descriptor and meta, not
just unlink them. Both are encrypted with the keystore id key, which is
NOT rotated when a single wallet is removed, so a plain unlink leaves
them decryptable in QSPI free space until the clusters happen to be
reused.
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import gc
from unittest import TestCase

import platform
from tests.util import get_keystore, get_wallets_app, clear_testdir

DESCRIPTOR = (
    "wsh(sortedmulti(2,"
    "[b317ec86/48h/1h/0h/2h]tpubDEToKMGFhyuP6kfwvjtYaf56khzS1cUcwc47C6aMH6bQ8sNVLMcCK6jr21YDCkU2QhTK5CAnddhfgZ8dD4EL1wGCaAKZaGFeVVdXHaJMTMn,"
    "[f04828fe/48h/1h/0h/2h]tpubDFekS5zvPSdW6WWjH2p7vPRkxmeeNGnirmj36AUyoAYbJvfKBj6UARWR5gQ6FRrr98dzT1XFTi6rfGo9AAAeutY1S6SoWijQ8BKxDhYQzDR,"
    "[d3c05b2e/48h/1h/0h/2h]tpubDFnAczXQTHxuBh7FxrpLDHBidkC1Di54pTPSPMu4AQjKziFQQTTEFXEVugqm8ucKQhJfLGesBjRZWtLpqAkAmecoXtvaPwCzf4teqrY7Uu5))"
)
NAMED_DESCRIPTOR = "Secure wipe test&" + DESCRIPTOR


class WalletSecureWipeTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.manager = get_wallets_app(self.keystore, "regtest").manager
        self.seen = []
        self._real = platform.secure_delete_file

        def recording(path):
            self.seen.append(path.rsplit("/", 1)[-1])
            return self._real(path)

        platform.secure_delete_file = recording

    def tearDown(self):
        platform.secure_delete_file = self._real
        clear_testdir()
        gc.collect()

    def test_delete_wallet_overwrites_descriptor_and_meta(self):
        w = self.manager.parse_wallet(NAMED_DESCRIPTOR)
        self.manager.add_wallet(w)
        wpath = w.path
        self.assertTrue(platform.file_exists(wpath + "/descriptor"))

        self.manager.delete_wallet(w)

        self.assertFalse(platform.file_exists(wpath + "/descriptor"))
        self.assertIn("descriptor", self.seen)
        self.assertIn("meta", self.seen)
