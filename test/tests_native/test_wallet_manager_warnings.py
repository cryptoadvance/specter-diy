import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase
from io import BytesIO
import gc
from binascii import hexlify

from embit import bip32, ec, script
from embit.descriptor import Descriptor
from embit.psbt import PSBT, DerivationPath
from embit.transaction import Transaction, TransactionInput, TransactionOutput
from tests.util import get_keystore, get_wallets_app, clear_testdir

MIXED_INPUTS_WARNING = "Mixed inputs from different wallets!"
UNKNOWN_INPUTS_WARNING = "Multiple unknown inputs may be from different wallets!"

# Watch-only testnet wallets used by the integration tests below.
DESCRIPTOR_A = (
    "MixTestA&wpkh([71348C8A/84h/1h/0h]tpubDCTb5JhwTc9S3pfEMNMajVPCEgCDxHTiBwmJgzLa2Znne2pPQ4dh1CjpS7ibiPBEXeJRJxddRaW1ZxxWyDvrndrQk8vqfco9Uvr7Eseo55L/{0,1}/*)"
)
DESCRIPTOR_B = (
    "MixTestB&wpkh([0EBCE71A/84h/1h/0h]tpubDCXmKn7bo4uUsnUDU1CLbCRRjVuurCunD5jRZMtFps71qwTgL1XUM8BJhcJYJqNhqTHUE8kU28GhApgz4o2FHjqE4ZC3QQN3k6VUa3z6ZMQ/{0,1}/*)"
)

# Fake but self-consistent PSBTs (generated with psbt_faker, spending
# made-up UTXOs). PSBT_SINGLE spends two inputs from wallet A only,
# PSBT_MIXED spends one input from wallet A and one from wallet B.
PSBT_SINGLE = "cHNidP8BAJoCAAAAArUycUzxHEYzxqsTEJVpL5MYmW9wZOC1U6TXC0PKgX/KAAAAAAD/////iMm3mDjFqdaBbHE/ZVrLcAIFnLVeCxQzlFg0wCHDEi0AAAAAAP////8CDN/1BQAAAAAWABQC0qr2BrLmrF9lcRZk4RxX07tggQzf9QUAAAAAFgAUrVwtkW35L7+4yws03wUISOuLit8AAAAAAAEBHwDh9QUAAAAAFgAU8mDo58D7gGT7T9CxRQuGRlwAiqAiBgLI4yrmNHwvj2S5sdX3WsF7jY7rTe1p0sW7ZRKC5s4HaRhxNIyKVAAAgAEAAIAAAACAAQAAAAAAAAAAAQEfAOH1BQAAAAAWABRAVRuVv94TtoL/GQBX1PqmTtF2HiIGA2yDc8YimWC+7tsbIVV0hpE4tgd+Bm0rciZp7YsrL6xWGHE0jIpUAACAAQAAgAAAAIABAAAAAQAAAAABARYAFALSqvYGsuasX2VxFmThHFfTu2CBIgIC/gh+oUaTn9z4FWQlnHORv710xPo5ORPAuJqGvqFtSWUYcTSMilQAAIABAACAAAAAgAAAAAAAAAAAAAEBFgAUrVwtkW35L7+4yws03wUISOuLit8A"
PSBT_MIXED = "cHNidP8BAJoCAAAAArUycUzxHEYzxqsTEJVpL5MYmW9wZOC1U6TXC0PKgX/KAAAAAAD/////9N9hUp4UTYXTCCHy4pkQAEF6xe8hP88jB6bQIO/XttEAAAAAAP////8CGN31BQAAAAAWABQggAVX3zK/wgkFSYcWcRCWgrMA1Rjd9QUAAAAAFgAUywr+Xnk67suP4O4XkARG2PJ2FucAAAAAAAEBHwDh9QUAAAAAFgAU8mDo58D7gGT7T9CxRQuGRlwAiqAiBgLI4yrmNHwvj2S5sdX3WsF7jY7rTe1p0sW7ZRKC5s4HaRhxNIyKVAAAgAEAAIAAAACAAQAAAAAAAAAAAQEfAOH1BQAAAAAWABT4MqE0hU0txS199SKSqpnSPcS/vyIGAhyvfzUnvLMT5JSMbPZOflc81MOmxvKfsELZApdS+FFXGA685xpUAACAAQAAgAAAAIABAAAAAAAAAAABARYAFCCABVffMr/CCQVJhxZxEJaCswDVAAEBFgAUywr+Xnk67suP4O4XkARG2PJ2FucA"


class WalletManagerWarningsTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.wallets_app = get_wallets_app(self.keystore, "regtest")
        self.manager = self.wallets_app.manager

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def _meta(self):
        return {
            "inputs": [],
            "outputs": [],
            "signed_inputs": 0,
            "tx_version": 2,
            "locktime": 0,
        }

    def test_no_warning_for_empty_wallets(self):
        meta = self._meta()
        self.manager.add_warnings({}, meta)
        self.assertFalse("warnings" in meta)

    def test_no_warning_for_single_wallet(self):
        meta = self._meta()
        wallets = {object(): {"amount": 1000, "gaps": [0, 0]}}
        self.manager.add_warnings(wallets, meta)
        self.assertFalse("warnings" in meta)

    def test_no_warning_for_single_unknown_input(self):
        meta = self._meta()
        meta["inputs"] = [{}]
        wallets = {None: {"amount": 1000, "gaps": None}}
        self.manager.add_warnings(wallets, meta)
        self.assertFalse("warnings" in meta)

    def test_warning_for_multiple_unknown_inputs(self):
        meta = self._meta()
        meta["inputs"] = [{}, {}]
        wallets = {None: {"amount": 2000, "gaps": None}}
        self.manager.add_warnings(wallets, meta)
        self.assertEqual(meta["warnings"], [UNKNOWN_INPUTS_WARNING])

    def test_warning_for_mixed_inputs_from_two_wallets(self):
        meta = self._meta()
        wallets = {
            object(): {"amount": 1000, "gaps": [0, 0]},
            object(): {"amount": 2000, "gaps": [0, 0]},
        }
        self.manager.add_warnings(wallets, meta)
        self.assertEqual(meta["warnings"], [MIXED_INPUTS_WARNING])

    def test_warning_for_mixed_known_and_unknown_wallets(self):
        meta = self._meta()
        wallets = {
            object(): {"amount": 1000, "gaps": [0, 0]},
            None: {"amount": 2000, "gaps": None},
        }
        self.manager.add_warnings(wallets, meta)
        self.assertEqual(meta["warnings"], [MIXED_INPUTS_WARNING])

    def test_existing_warnings_are_preserved(self):
        meta = self._meta()
        meta["warnings"] = ["Some other warning!"]
        wallets = {
            object(): {"amount": 1000, "gaps": [0, 0]},
            object(): {"amount": 2000, "gaps": [0, 0]},
        }
        self.manager.add_warnings(wallets, meta)
        self.assertEqual(
            meta["warnings"], ["Some other warning!", MIXED_INPUTS_WARNING]
        )

    def test_warning_is_not_duplicated(self):
        meta = self._meta()
        wallets = {
            object(): {"amount": 1000, "gaps": [0, 0]},
            object(): {"amount": 2000, "gaps": [0, 0]},
        }
        self.manager.add_warnings(wallets, meta)
        self.manager.add_warnings(wallets, meta)
        self.assertEqual(meta["warnings"], [MIXED_INPUTS_WARNING])


class WalletManagerWarningsIntegrationTest(TestCase):
    """
    Regression tests for the full wiring: PSBT -> preprocess_psbt() ->
    wallet detection -> meta["warnings"]. The mixed-inputs warning was
    originally lost during the Liquid refactor (c476cde) precisely because
    this wiring was dropped, so unit tests of add_warnings alone are not
    sufficient.
    """

    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.wallets_app = get_wallets_app(self.keystore, "test")
        self.manager = self.wallets_app.manager

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def _import(self, desc):
        self.manager.add_wallet(self.manager.parse_wallet(desc))

    def _preprocess(self, b64):
        raw = PSBT.from_string(b64).serialize()
        return self.manager.preprocess_psbt(BytesIO(raw), BytesIO())

    def test_preprocess_single_wallet_tx_produces_no_warning(self):
        self._import(DESCRIPTOR_A)
        self._import(DESCRIPTOR_B)
        wallets, meta = self._preprocess(PSBT_SINGLE)
        self.assertEqual(len(wallets), 1)
        self.assertFalse("warnings" in meta)

    def test_preprocess_mixed_wallets_tx_produces_warning(self):
        self._import(DESCRIPTOR_A)
        self._import(DESCRIPTOR_B)
        wallets, meta = self._preprocess(PSBT_MIXED)
        self.assertEqual(len(wallets), 2)
        self.assertIn(MIXED_INPUTS_WARNING, meta.get("warnings", []))

    def test_preprocess_mixed_with_unknown_wallet_produces_warning(self):
        # multisig change-address attack scenario: the victim's wallet is
        # imported, the attacker's inputs are unknown - the device must
        # still warn about mixed inputs
        self._import(DESCRIPTOR_A)
        wallets, meta = self._preprocess(PSBT_MIXED)
        self.assertEqual(len(wallets), 2)
        self.assertTrue(None in wallets)
        self.assertIn(MIXED_INPUTS_WARNING, meta.get("warnings", []))

    def test_preprocess_multiple_unknown_signable_policies_warns(self):
        paths = [
            bip32.parse_path("m/48h/1h/0h/2h/0/0"),
            bip32.parse_path("m/48h/1h/0h/2h/0/1"),
        ]
        device_pubs = [
            self.keystore.root.derive(path).key.get_public_key() for path in paths
        ]
        cosigner_pubs = [
            ec.PrivateKey(bytes([3]) * 32).get_public_key(),
            ec.PrivateKey(bytes([4]) * 32).get_public_key(),
        ]
        descriptors = [
            Descriptor.from_string(
                "wsh(sortedmulti(2,%s,%s))"
                % (
                    hexlify(device_pubs[i].sec()).decode(),
                    hexlify(cosigner_pubs[i].sec()).decode(),
                )
            )
            for i in range(2)
        ]
        tx = Transaction(
            vin=[TransactionInput(b"1" * 32, 0), TransactionInput(b"2" * 32, 0)],
            vout=[TransactionOutput(190000, script.p2wpkh(device_pubs[0]))],
        )
        psbt = PSBT(tx)
        for i in range(2):
            psbt.inputs[i].witness_utxo = TransactionOutput(
                100000, descriptors[i].script_pubkey()
            )
            psbt.inputs[i].witness_script = descriptors[i].witness_script()
            psbt.inputs[i].bip32_derivations[device_pubs[i]] = DerivationPath(
                self.keystore.fingerprint, paths[i]
            )

        filled = BytesIO()
        wallets, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), filled)

        self.assertEqual(len(wallets), 1)
        self.assertTrue(None in wallets)
        self.assertIn(UNKNOWN_INPUTS_WARNING, meta.get("warnings", []))

        # Both inputs are signable despite collapsing into the same unknown bucket.
        filled.seek(0)
        psbtv = self.manager.PSBTViewClass.view(filled, compress=True)
        signed = BytesIO()
        self.manager.sign_psbtview(psbtv, signed, wallets, None)
        signed.seek(0)
        signed_psbt = PSBT.read_from(signed)
        self.assertEqual(
            [len(inp.partial_sigs) for inp in signed_psbt.inputs], [1, 1]
        )
