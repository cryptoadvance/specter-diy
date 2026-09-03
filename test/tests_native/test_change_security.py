import ast
import gc
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

from embit import bip32, ec, script
from embit.psbt import DerivationPath, PSBT
from embit.transaction import Transaction, TransactionInput, TransactionOutput

from apps.wallets.wallet import Wallet
from apps.wallets.manager import UNVERIFIED_CHANGE_WARNING
from tests.util import clear_testdir, get_keystore, get_wallets_app


INVALID_CHANGE_WARNING = (
    "Invalid change metadata! Host claimed this output as wallet change, "
    "but it does not match your wallet. Verify the destination."
)


def fake_pubkey(seed):
    return ec.PrivateKey(bytes([seed]) * 32).get_public_key()


class ChangeSecurityTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.app = get_wallets_app(self.keystore, "regtest")
        self.manager = self.app.manager
        self.wallet = self.manager.wallets[0]
        self.fingerprint = self.keystore.fingerprint
        self.origin = "m/84h/1h/0h"

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def derivation(self, branch, index, origin=None):
        origin = origin or self.origin
        path = bip32.parse_path("%s/%d/%d" % (origin, branch, index))
        return DerivationPath(self.fingerprint, path)

    def output(self, branch=None, index=0, output_script=None, taproot=False):
        derivations = {}
        taproot_derivations = {}
        if branch is not None:
            der = self.derivation(branch, index)
            if taproot:
                taproot_derivations[fake_pubkey(1)] = ([], der)
            else:
                derivations[fake_pubkey(1)] = der
        return SimpleNamespace(
            bip32_derivations=derivations,
            taproot_bip32_derivations=taproot_derivations,
            script_pubkey=output_script,
        )

    def wallet_script(self, wallet, branch, index):
        return wallet.descriptor.derive(index, branch_index=branch).script_pubkey()

    def test_canonical_change_is_verified_without_warning(self):
        out = self.output(1, 3, self.wallet_script(self.wallet, 1, 3))
        status = self.manager.get_output_status(self.wallet, {self.wallet: {}}, out)
        self.assertEqual(status, ((3, 1), True, None))

    def test_internal_change_address_with_unknown_input_is_not_verified_change(self):
        out = self.output(1, 10, self.wallet_script(self.wallet, 1, 10))
        derivation, change, warning = self.manager.get_output_status(
            self.wallet, {self.wallet: {}, None: {}}, out
        )
        self.assertEqual(derivation, (10, 1))
        self.assertFalse(change)
        self.assertEqual(
            warning, UNVERIFIED_CHANGE_WARNING % (1, 10)
        )

    def test_receive_branch_is_visible_wallet_output_without_warning(self):
        out = self.output(0, 3, self.wallet_script(self.wallet, 0, 3))
        derivation, change, warning = self.manager.get_output_status(
            self.wallet, {self.wallet: {}}, out
        )
        self.assertEqual(derivation, (3, 0))
        self.assertFalse(change)
        self.assertIsNone(warning)

    def test_external_output_has_no_wallet_metadata_warning(self):
        out = self.output(output_script=script.p2wpkh(fake_pubkey(44)))
        self.assertEqual(
            self.manager.get_output_status(self.wallet, {self.wallet: {}}, out),
            (None, False, None),
        )

    def test_forged_change_claim_is_detected_before_ownership_is_discarded(self):
        attacker_script = script.p2wpkh(fake_pubkey(99))
        out = self.output(1, 9, attacker_script)
        # Descriptor.owns() rejects this output, which is why the normal
        # ownership result is None. The spending-wallet scan still detects
        # the descriptor-valid branch-1 claim and reports its mismatch.
        derivation, change, warning = self.manager.get_output_status(
            None, {self.wallet: {}}, out
        )
        self.assertIsNone(derivation)
        self.assertFalse(change)
        self.assertEqual(warning, INVALID_CHANGE_WARNING)

    def test_forged_change_claim_is_detected_with_valid_receive_claim(self):
        receive = self.wallet.descriptor.derive(3, branch_index=0)
        forged_change = self.wallet.descriptor.derive(9, branch_index=1)
        out = SimpleNamespace(
            bip32_derivations={
                receive.keys[0].get_public_key(): self.derivation(0, 3),
                forged_change.keys[0].get_public_key(): self.derivation(1, 9),
            },
            taproot_bip32_derivations={},
            script_pubkey=receive.script_pubkey(),
        )
        derivation, change, warning = self.manager.get_output_status(
            self.wallet, {self.wallet: {}}, out
        )
        self.assertEqual(derivation, (3, 0))
        self.assertFalse(change)
        self.assertEqual(warning, INVALID_CHANGE_WARNING)

    def test_unrelated_wallet_metadata_does_not_warn(self):
        other_keystore = get_keystore(mnemonic="zoo " * 11 + "wrong")
        other_origin = "m/84h/1h/0h"
        other_xpub = other_keystore.get_xpub(other_origin)
        other_desc = "wpkh([%s%s]%s/<0;1>/*)" % (
            other_keystore.fingerprint.hex(),
            other_origin[1:],
            other_xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        out = SimpleNamespace(
            bip32_derivations={
                fake_pubkey(99): DerivationPath(
                    other_keystore.fingerprint,
                    bip32.parse_path("%s/1/9" % other_origin),
                )
            },
            taproot_bip32_derivations={},
            script_pubkey=script.p2wpkh(fake_pubkey(99)),
        )
        self.assertIsNone(
            self.manager.get_output_status(None, {self.wallet: {}}, out)[2]
        )

    def test_conflicting_change_claim_on_other_wallet_output_warns(self):
        other_keystore = get_keystore(mnemonic="zoo " * 11 + "wrong")
        other_origin = "m/84h/1h/0h"
        other_xpub = other_keystore.get_xpub(other_origin)
        other_desc = "wpkh([%s%s]%s/<0;1>/*)" % (
            other_keystore.fingerprint.hex(),
            other_origin[1:],
            other_xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        other = Wallet.from_descriptor(other_desc, None)
        other.name = "Other"
        self.manager.wallets.append(other)

        other_derived = other.descriptor.derive(3, branch_index=1)
        forged_change = self.wallet.descriptor.derive(9, branch_index=1)
        tx = Transaction(
            vin=[TransactionInput(b"5" * 32, 0)],
            vout=[TransactionOutput(20_000, other_derived.script_pubkey())],
        )
        psbt = PSBT(tx)
        psbt.inputs[0].witness_utxo = TransactionOutput(
            25_000, self.wallet_script(self.wallet, 0, 0)
        )
        psbt.inputs[0].bip32_derivations[fake_pubkey(85)] = self.derivation(0, 0)
        psbt.outputs[0].bip32_derivations[
            other_derived.keys[0].get_public_key()
        ] = DerivationPath(
            other_keystore.fingerprint,
            bip32.parse_path("%s/1/3" % other_origin),
        )
        psbt.outputs[0].bip32_derivations[
            forged_change.keys[0].get_public_key()
        ] = self.derivation(1, 9)
        _, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), BytesIO())
        output = meta["outputs"][0]
        self.assertFalse(output["change"])
        self.assertIn("Other", output["label"])
        self.assertNotIn("change", output["label"])
        self.assertIn(INVALID_CHANGE_WARNING, output["warnings"])

    def test_shared_derivation_for_other_wallet_does_not_warn(self):
        xpub = self.keystore.get_xpub(self.origin)
        other_desc = "sh(wpkh([%s%s]%s/<0;1>/*))" % (
            self.fingerprint.hex(),
            self.origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        other = Wallet.from_descriptor(other_desc, None)
        other.name = "Nested"
        self.manager.wallets.append(other)

        derived = other.descriptor.derive(3, branch_index=1)
        tx = Transaction(
            vin=[TransactionInput(b"7" * 32, 0)],
            vout=[TransactionOutput(20_000, derived.script_pubkey())],
        )
        psbt = PSBT(tx)
        psbt.inputs[0].witness_utxo = TransactionOutput(
            25_000, self.wallet_script(self.wallet, 0, 0)
        )
        psbt.inputs[0].bip32_derivations[fake_pubkey(88)] = self.derivation(0, 0)
        psbt.outputs[0].bip32_derivations[
            derived.keys[0].get_public_key()
        ] = self.derivation(1, 3)

        _, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), BytesIO())
        output = meta["outputs"][0]
        self.assertFalse(output["change"])
        self.assertIn("Nested", output["label"])
        self.assertNotIn(INVALID_CHANGE_WARNING, output.get("warnings", []))

    def test_shared_taproot_output_key_derivation_does_not_warn(self):
        xpub = self.keystore.get_xpub(self.origin)
        other_desc = "tr([%s%s]%s/<0;1>/*)" % (
            self.fingerprint.hex(),
            self.origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        other = Wallet.from_descriptor(other_desc, None)
        other.name = "Taproot"
        self.manager.wallets.append(other)

        derived = other.descriptor.derive(3, branch_index=1)
        tx = Transaction(
            vin=[TransactionInput(b"8" * 32, 0)],
            vout=[TransactionOutput(20_000, derived.script_pubkey())],
        )
        psbt = PSBT(tx)
        psbt.inputs[0].witness_utxo = TransactionOutput(
            25_000, self.wallet_script(self.wallet, 0, 0)
        )
        psbt.inputs[0].bip32_derivations[fake_pubkey(89)] = self.derivation(0, 0)
        output_key = ec.PublicKey.from_xonly(derived.script_pubkey().data[2:])
        psbt.outputs[0].taproot_bip32_derivations[output_key] = (
            [],
            self.derivation(1, 3),
        )

        _, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), BytesIO())
        output = meta["outputs"][0]
        self.assertFalse(output["change"])
        self.assertIn("Taproot", output["label"])
        self.assertNotIn(INVALID_CHANGE_WARNING, output.get("warnings", []))

    def test_multipath_claim_is_bound_regardless_of_metadata_order(self):
        origin = "m/48h/1h/0h/2h"
        xpub = self.keystore.get_xpub(origin)
        key = "[%s%s]%s" % (
            self.fingerprint.hex(),
            origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        descriptor = "wsh(multi(2,%s/<0;1>/*,%s/<1;0>/*))" % (key, key)
        wallet = Wallet.from_descriptor(descriptor, None)
        derived = wallet.descriptor.derive(3, branch_index=0)
        out = SimpleNamespace(
            bip32_derivations={
                derived.keys[0].get_public_key(): DerivationPath(
                    self.fingerprint,
                    bip32.parse_path("%s/0/3" % origin),
                ),
                derived.keys[1].get_public_key(): DerivationPath(
                    self.fingerprint,
                    bip32.parse_path("%s/1/3" % origin),
                ),
            },
            taproot_bip32_derivations={},
            script_pubkey=derived.script_pubkey(),
        )

        derivation, change, warning = self.manager.get_output_status(
            wallet, {wallet: {}}, out
        )
        self.assertEqual(derivation, (3, 0))
        self.assertFalse(change)
        self.assertIsNone(warning)

        out.bip32_derivations = {
            derived.keys[1].get_public_key(): DerivationPath(
                self.fingerprint,
                bip32.parse_path("%s/1/3" % origin),
            ),
            derived.keys[0].get_public_key(): DerivationPath(
                self.fingerprint,
                bip32.parse_path("%s/0/3" % origin),
            ),
        }
        derivation, change, warning = self.manager.get_output_status(
            wallet, {wallet: {}}, out
        )
        self.assertEqual(derivation, (3, 0))
        self.assertFalse(change)
        self.assertIsNone(warning)

    def test_three_branch_descriptors_never_auto_change(self):
        xpub = self.keystore.get_xpub(self.origin)
        desc = "wpkh([%s%s]%s/<0;1;2>/*)" % (
            self.fingerprint.hex(),
            self.origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        wallet = Wallet.from_descriptor(desc, None)
        out = self.output(1, 3, self.wallet_script(wallet, 1, 3))
        self.assertFalse(
            self.manager.get_output_status(wallet, {wallet: {}}, out)[1]
        )

    def test_three_branch_forged_position_one_metadata_does_not_warn(self):
        # Sole spending wallet has a <0;1;2> descriptor, the host supplies a
        # descriptor-valid position-1 derivation, but the real output script
        # is unrelated. The output stays visible and non-change (as always
        # for a >2-branch descriptor), and because position 1 has no defined
        # "change" meaning here the device must NOT raise the invalid-change-
        # metadata warning: the host never claimed change, only a derivation.
        xpub = self.keystore.get_xpub(self.origin)
        desc = "wpkh([%s%s]%s/<0;1;2>/*)" % (
            self.fingerprint.hex(),
            self.origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        wallet = Wallet.from_descriptor(desc, None)
        wallet.name = "Three branch"
        out = self.output(1, 9, script.p2wpkh(fake_pubkey(99)))
        derivation, change, warning = self.manager.get_output_status(
            None, {wallet: {}}, out
        )
        self.assertIsNone(derivation)
        self.assertFalse(change)
        self.assertIsNone(warning)

    def test_one_branch_descriptor_never_auto_change(self):
        xpub = self.keystore.get_xpub(self.origin)
        desc = "wpkh([%s%s]%s/<0>/*)" % (
            self.fingerprint.hex(),
            self.origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        wallet = Wallet.from_descriptor(desc, None)
        out = self.output(0, 3, self.wallet_script(wallet, 0, 3))
        self.assertEqual(wallet.descriptor.num_branches, 1)
        self.assertFalse(self.manager.get_output_status(wallet, {wallet: {}}, out)[1])

    def test_unusual_three_branch_position_one_never_auto_change(self):
        xpub = self.keystore.get_xpub(self.origin)
        desc = "wpkh([%s%s]%s/<22;33;44>/*)" % (
            self.fingerprint.hex(),
            self.origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        wallet = Wallet.from_descriptor(desc, None)
        der = DerivationPath(
            self.fingerprint,
            bip32.parse_path("%s/33/4" % self.origin),
        )
        out = SimpleNamespace(
            bip32_derivations={fake_pubkey(2): der},
            taproot_bip32_derivations={},
            script_pubkey=self.wallet_script(wallet, 1, 4),
        )
        self.assertEqual(wallet.descriptor.num_branches, 3)
        self.assertFalse(self.manager.get_output_status(wallet, {wallet: {}}, out)[1])

    def test_two_branch_unusual_raw_value_uses_position_one(self):
        xpub = self.keystore.get_xpub(self.origin)
        desc = "wpkh([%s%s]%s/<22;33>/*)" % (
            self.fingerprint.hex(),
            self.origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        wallet = Wallet.from_descriptor(desc, None)
        der = DerivationPath(
            self.fingerprint,
            bip32.parse_path("%s/33/4" % self.origin),
        )
        out = SimpleNamespace(
            bip32_derivations={fake_pubkey(3): der},
            taproot_bip32_derivations={},
            script_pubkey=self.wallet_script(wallet, 1, 4),
        )
        self.assertTrue(self.manager.get_output_status(wallet, {wallet: {}}, out)[1])

    def test_taproot_change_and_forged_taproot_claim(self):
        origin = "m/86h/1h/0h"
        xpub = self.keystore.get_xpub(origin)
        desc = "tr([%s%s]%s/<0;1>/*)" % (
            self.fingerprint.hex(),
            origin[1:],
            xpub.to_base58(self.manager.Networks["regtest"]["xpub"]),
        )
        wallet = Wallet.from_descriptor(desc, None)
        der = DerivationPath(self.fingerprint, bip32.parse_path("%s/1/3" % origin))
        out = SimpleNamespace(
            bip32_derivations={},
            taproot_bip32_derivations={fake_pubkey(4): ([], der)},
            script_pubkey=self.wallet_script(wallet, 1, 3),
        )
        self.assertTrue(self.manager.get_output_status(wallet, {wallet: {}}, out)[1])
        out.script_pubkey = script.p2wpkh(fake_pubkey(88))
        self.assertEqual(
            self.manager.get_output_status(None, {wallet: {}}, out)[2],
            INVALID_CHANGE_WARNING,
        )

    def test_multiple_spending_wallets_and_unknown_wallet_fail_closed(self):
        other = Wallet.from_descriptor(str(self.wallet.descriptor), None)
        out = self.output(1, 3, self.wallet_script(self.wallet, 1, 3))
        self.assertFalse(
            self.manager.get_output_status(
                self.wallet, {self.wallet: {}, other: {}}, out
            )[1]
        )
        self.assertFalse(
            self.manager.get_output_status(self.wallet, {None: {}}, out)[1]
        )

    def test_output_warnings_are_accumulated(self):
        metaout = {"warnings": ["Existing warning!"]}
        self.manager.add_output_warning(metaout, INVALID_CHANGE_WARNING)
        self.manager.add_output_warning(metaout, "Existing warning!")
        self.assertEqual(
            metaout["warnings"], ["Existing warning!", INVALID_CHANGE_WARNING]
        )
        self.assertNotIn("warning", metaout)

    def test_exact_manual_five_transaction_warns_through_preprocess(self):
        wallet = self.wallet
        tx = Transaction(
            vin=[TransactionInput(b"3" * 32, 0)],
            vout=[
                TransactionOutput(95_000, script.p2wpkh(fake_pubkey(70))),
                TransactionOutput(24_000, script.p2wpkh(fake_pubkey(71))),
            ],
        )
        psbt = PSBT(tx)
        psbt.inputs[0].witness_utxo = TransactionOutput(
            120_000, self.wallet_script(wallet, 0, 0)
        )
        psbt.inputs[0].bip32_derivations[fake_pubkey(72)] = self.derivation(0, 0)
        # The metadata claims /1/9, while output 1 is the attacker script.
        psbt.outputs[1].bip32_derivations[fake_pubkey(73)] = self.derivation(1, 9)
        _, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), BytesIO())
        output = meta["outputs"][1]
        self.assertFalse(output["change"])
        self.assertNotIn("label", output)
        self.assertEqual(output["value"], 24_000)
        self.assertEqual(output["address"], self.manager.get_address(tx.vout[1]))
        self.assertEqual(output["warnings"], [INVALID_CHANGE_WARNING])

    def test_unknown_input_internal_change_warning_survives_preprocess(self):
        wallet = self.wallet
        tx = Transaction(
            vin=[TransactionInput(b"6" * 32, 0)],
            vout=[
                TransactionOutput(
                    95_000, self.wallet_script(wallet, 1, 10)
                )
            ],
        )
        psbt = PSBT(tx)
        psbt.inputs[0].witness_utxo = TransactionOutput(
            120_000, script.p2wpkh(fake_pubkey(91))
        )
        psbt.outputs[0].bip32_derivations[fake_pubkey(92)] = self.derivation(1, 10)
        _, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), BytesIO())
        output = meta["outputs"][0]
        self.assertFalse(output["change"])
        self.assertEqual(
            output["warnings"], [UNVERIFIED_CHANGE_WARNING % (1, 10)]
        )

    def test_two_suspicious_outputs_keep_warnings_separate(self):
        wallet = self.wallet
        tx = Transaction(
            vin=[TransactionInput(b"4" * 32, 0)],
            vout=[
                TransactionOutput(10_000, script.p2wpkh(fake_pubkey(80))),
                TransactionOutput(20_000, script.p2wpkh(fake_pubkey(81))),
            ],
        )
        psbt = PSBT(tx)
        psbt.inputs[0].witness_utxo = TransactionOutput(
            40_000, self.wallet_script(wallet, 0, 0)
        )
        psbt.inputs[0].bip32_derivations[fake_pubkey(82)] = self.derivation(0, 0)
        psbt.outputs[0].bip32_derivations[fake_pubkey(83)] = self.derivation(1, 4)
        psbt.outputs[1].bip32_derivations[fake_pubkey(84)] = self.derivation(1, 5)
        _, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), BytesIO())
        self.assertEqual(
            [out["warnings"] for out in meta["outputs"]],
            [[INVALID_CHANGE_WARNING], [INVALID_CHANGE_WARNING]],
        )

    def test_liquid_uses_the_same_conservative_change_rules(self):
        clear_testdir()
        liquid_keystore = get_keystore()
        liquid_app = get_wallets_app(liquid_keystore, "elementsregtest")
        liquid_manager = liquid_app.manager
        liquid_wallet = liquid_manager.wallets[0]
        origin = "m/84h/1h/0h"

        def liquid_output(branch, index):
            der = DerivationPath(
                liquid_keystore.fingerprint,
                bip32.parse_path("%s/%d/%d" % (origin, branch, index)),
            )
            return SimpleNamespace(
                bip32_derivations={fake_pubkey(90 + branch): der},
                taproot_bip32_derivations={},
                script_pubkey=liquid_wallet.descriptor.derive(
                    index, branch_index=branch
                ).script_pubkey(),
            )

        self.assertTrue(
            liquid_manager.get_output_status(
                liquid_wallet, {liquid_wallet: {}}, liquid_output(1, 3)
            )[1]
        )
        self.assertFalse(
            liquid_manager.get_output_status(
                liquid_wallet, {liquid_wallet: {}}, liquid_output(0, 3)
            )[1]
        )


class TransactionScreenSecurityTest(TestCase):
    """Guard the primary/details visibility contract without an LVGL device."""

    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "src" / "gui" / "screens" / "transaction.py"
        self.tree = ast.parse(path.read_text())

    def test_primary_page_shows_warning_bearing_outputs(self):
        guards = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == "out['change'] and (not out.get('warnings'))"
        ]
        self.assertEqual(len(guards), 1)
        self.assertTrue(any(isinstance(node, ast.Continue) for node in guards[0].body))
        source = ast.unparse(self.tree)
        self.assertIn("self.show_output(out, obj)", source)
        self.assertIn("warning_text = '\\n'.join(out.get('warnings', []))", source)

    def test_details_page_has_no_output_skip(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple):
                if any(isinstance(part, ast.Name) and part.id == "out" for part in node.target.elts):
                    for child in ast.walk(node):
                        self.assertNotIsInstance(child, (ast.Continue, ast.Break))
