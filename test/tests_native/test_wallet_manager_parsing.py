import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase
from io import BytesIO
import gc

from tests.util import get_keystore, get_wallets_app, clear_testdir
from apps.wallets.manager import ADD_WALLET, SIGN_PSBT, VERIFY_ADDRESS
from apps.wallets.manager import WalletManager, WalletError
from embit.psbt import PSBT
from embit.psbtview import PSBTView
from embit.script import Script
from embit.transaction import SIGHASH, Transaction, TransactionInput, TransactionOutput

DOC_DESCRIPTOR = (
    "wsh(sortedmulti(2,"
    "[b317ec86/48h/1h/0h/2h]tpubDEToKMGFhyuP6kfwvjtYaf56khzS1cUcwc47C6aMH6bQ8sNVLMcCK6jr21YDCkU2QhTK5CAnddhfgZ8dD4EL1wGCaAKZaGFeVVdXHaJMTMn,"
    "[f04828fe/48h/1h/0h/2h]tpubDFekS5zvPSdW6WWjH2p7vPRkxmeeNGnirmj36AUyoAYbJvfKBj6UARWR5gQ6FRrr98dzT1XFTi6rfGo9AAAeutY1S6SoWijQ8BKxDhYQzDR,"
    "[d3c05b2e/48h/1h/0h/2h]tpubDFnAczXQTHxuBh7FxrpLDHBidkC1Di54pTPSPMu4AQjKziFQQTTEFXEVugqm8ucKQhJfLGesBjRZWtLpqAkAmecoXtvaPwCzf4teqrY7Uu5))"
)
DOC_NAMED_DESCRIPTOR = "My multisig&" + DOC_DESCRIPTOR
DOC_ADDWALLET_COMMAND = "addwallet " + DOC_NAMED_DESCRIPTOR
DOC_ADDRESS_REQUEST = (
    "bitcoin:bcrt1qd3mtrhysk3k4w6fmu7ayjvwk6q98c2dpf0p4x87zauu8rcgq5dzq73tyrx?index=2"
)
# Minimal base64-encoded PSBT prefix. The parser only checks the magic bytes,
# so using a short fixture keeps memory usage low on constrained interpreters.
DOC_BASE64_PSBT = "cHNidP8="


class WalletManagerParsingTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.wallets_app = get_wallets_app(self.keystore, "regtest")
        self.manager = self.wallets_app.manager

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def _parse_command(self, data):
        stream = BytesIO(data)
        cmd, result_stream = self.manager.parse_stream(stream)
        self.assertIs(result_stream, stream)
        return cmd, result_stream

    def test_docs_addwallet_command_is_detected(self):
        cmd, stream = self._parse_command(DOC_ADDWALLET_COMMAND.encode())
        self.assertEqual(cmd, ADD_WALLET)
        self.assertEqual(stream.read().decode(), DOC_NAMED_DESCRIPTOR)

    def test_descriptor_without_addwallet_prefix_is_parsed(self):
        cmd, stream = self._parse_command(DOC_NAMED_DESCRIPTOR.encode())
        self.assertEqual(cmd, ADD_WALLET)
        self.assertEqual(stream.read().decode(), DOC_NAMED_DESCRIPTOR)
        wallet = self.manager.parse_wallet(DOC_NAMED_DESCRIPTOR)
        self.assertEqual(wallet.name, "My multisig")
        self.assertEqual(str(wallet.descriptor), DOC_DESCRIPTOR)

    def test_raw_descriptor_is_parsed(self):
        cmd, stream = self._parse_command(DOC_DESCRIPTOR.encode())
        self.assertEqual(cmd, ADD_WALLET)
        self.assertEqual(stream.read().decode(), DOC_DESCRIPTOR)
        wallet = self.manager.parse_wallet(DOC_DESCRIPTOR)
        self.assertEqual(wallet.name, "Untitled")
        self.assertEqual(str(wallet.descriptor), DOC_DESCRIPTOR)

    def test_docs_base64_psbt_is_detected(self):
        cmd, stream = self._parse_command(DOC_BASE64_PSBT.encode())
        self.assertEqual(cmd, SIGN_PSBT)
        # ensure stream is rewound for later processing
        self.assertEqual(stream.read(10), DOC_BASE64_PSBT[:10].encode())

    def test_docs_address_request_is_detected(self):
        cmd, stream = self._parse_command(DOC_ADDRESS_REQUEST.encode())
        self.assertEqual(cmd, VERIFY_ADDRESS)
        # parse_stream should keep address data available for processing
        self.assertEqual(stream.read().decode(), DOC_ADDRESS_REQUEST.replace("bitcoin:", "", 1))


class SighashSinglePolicyTest(TestCase):
    def setUp(self):
        self.manager = WalletManager.__new__(WalletManager)

    def view(self, sighashes, num_outputs):
        tx = Transaction(
            vin=[TransactionInput(b"\x00" * 32, i) for i in range(len(sighashes))],
            vout=[TransactionOutput(1000, Script(b"\x51")) for _ in range(num_outputs)],
        )
        psbt = PSBT(tx)
        for inp, sighash in zip(psbt.inputs, sighashes):
            inp.sighash_type = sighash
        return PSBTView.view(BytesIO(psbt.serialize()), compress=True)

    def test_single_without_output_rejected_before_signing(self):
        for sh in (SIGHASH.SINGLE, SIGHASH.SINGLE | SIGHASH.ANYONECANPAY):
            with self.subTest(sighash=sh):
                view = self.view([SIGHASH.ALL, sh], 1)
                out = BytesIO()
                with self.assertRaisesRegex(WalletError, "SIGHASH_SINGLE requires"):
                    self.manager.sign_psbtview(view, out, {}, None)
                self.assertEqual(out.getvalue(), b"")

    def test_single_with_output_allowed(self):
        for sh in (SIGHASH.SINGLE, SIGHASH.SINGLE | SIGHASH.ANYONECANPAY):
            with self.subTest(sighash=sh):
                self.manager.check_sighash_single(self.view([sh, SIGHASH.ALL], 1))

    def test_non_single_without_matching_output_allowed(self):
        for sh in (None, SIGHASH.ALL, SIGHASH.NONE):
            with self.subTest(sighash=sh):
                self.manager.check_sighash_single(self.view([SIGHASH.ALL, sh], 1))

    def test_default_override_does_not_bypass_invalid_request(self):
        with self.assertRaisesRegex(WalletError, "SIGHASH_SINGLE requires"):
            self.manager.check_sighash_single(
                self.view([SIGHASH.ALL, SIGHASH.SINGLE], 1), SIGHASH.ALL
            )

    def test_explicit_single_override_rejected(self):
        with self.assertRaisesRegex(WalletError, "SIGHASH_SINGLE requires"):
            self.manager.check_sighash_single(
                self.view([None, None], 1), SIGHASH.SINGLE
            )

    def test_liquid_rangeproof_modifier_does_not_bypass_check(self):
        with self.assertRaisesRegex(WalletError, "SIGHASH_SINGLE requires"):
            self.manager.check_sighash_single(
                self.view([SIGHASH.ALL, SIGHASH.SINGLE | 0x40], 1)
            )
