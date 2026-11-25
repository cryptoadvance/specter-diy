"""
End-to-end regression tests for issue #302 / PR #399.

These drive the real Specter signing path (``preprocess_psbt`` ->
``sign_psbtview`` -> ``keystore.sign_input`` -> ``embit.psbtview``) and
inspect the *serialized* signature bytes, not just the sighash helpers.

The central regression: ``SIGHASH.DEFAULT == 0`` used to be treated as
falsy, so Specter fell back to ``SIGHASH.ALL`` and a taproot key-path
signature came out 65 bytes long ending in ``0x01`` instead of a bare
64-byte BIP341 signature.
"""
import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

import gc
from binascii import hexlify
from io import BytesIO
from unittest import TestCase

from embit.descriptor import Descriptor
from embit.ec import PublicKey, SchnorrSig
from embit.liquid.pset import PSET
from embit.liquid.psetview import PSETView
from embit.liquid.transaction import (
    LSIGHASH, LTransaction, LTransactionInput, LTransactionOutput,
)
from embit.networks import NETWORKS
from embit.psbt import PSBT, DerivationPath
from embit.psbtview import PSBTView
from embit.script import Script
from embit.transaction import SIGHASH, Transaction, TransactionInput, TransactionOutput

from apps.wallets.wallet import WalletError
from tests.util import get_keystore, get_wallets_app, clear_testdir

H = 0x80000000
PREV_TXID = bytes(range(32))


def _run(coro):
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value


class _FakePrompt:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _Screens:
    """show_screen double that records Prompt dialogs."""

    def __init__(self, response=True):
        self.log = []
        self.screens = []
        self.response = response

    async def __call__(self, screen):
        self.log.append(type(screen).__name__)
        self.screens.append(screen)
        return self.response


def _tr_descriptor(keystore, network):
    net = NETWORKS[network]
    xpub = keystore.get_xpub("m/86h/1h/0h").to_base58(net["xpub"])
    fp = hexlify(keystore.fingerprint).decode()
    return "tr([%s/86h/1h/0h]%s/{0,1}/*)" % (fp, xpub)


class _Fixture:
    """Builds a signable PSBT for a freshly imported taproot wallet."""

    def __init__(self, network="regtest"):
        self.keystore = get_keystore()
        self.wapp = get_wallets_app(self.keystore, network)
        self.manager = self.wapp.manager
        self.network = network
        self.mfp = self.keystore.fingerprint

        self.tr_desc_str = _tr_descriptor(self.keystore, network)
        self.tr_desc = Descriptor.from_string(self.tr_desc_str)
        w = self.manager.parse_wallet("TR&" + self.tr_desc_str)
        self.manager.add_wallet(w)
        # the wpkh "Default" wallet is created automatically
        self.wpkh_wallet = self.manager.wallets[0]
        self.wpkh_desc = Descriptor.from_string(str(self.wpkh_wallet.descriptor))

    # -- scope builders -------------------------------------------------
    def _taproot_input(self, psbt, i, idx=0, branch=0, sighash_type=None):
        derived = self.tr_desc.derive(idx, branch_index=branch)
        pub = derived.keys[0].get_public_key()
        inp = psbt.inputs[i]
        inp.witness_utxo = TransactionOutput(100_000, derived.script_pubkey())
        inp.taproot_bip32_derivations[pub] = (
            [],
            DerivationPath(self.mfp, [H + 86, H + 1, H + 0, branch, idx]),
        )
        if sighash_type is not None:
            inp.sighash_type = sighash_type

    def _wpkh_input(self, psbt, i, idx=0, branch=0, sighash_type=None):
        derived = self.wpkh_desc.derive(idx, branch_index=branch)
        pub = derived.keys[0].get_public_key()
        inp = psbt.inputs[i]
        inp.witness_utxo = TransactionOutput(100_000, derived.script_pubkey())
        inp.bip32_derivations[pub] = DerivationPath(
            self.mfp, [H + 84, H + 1, H + 0, branch, idx]
        )
        if sighash_type is not None:
            inp.sighash_type = sighash_type

    def build(self, specs):
        """specs: list of ("taproot"|"wpkh", sighash_type or None)."""
        n = len(specs)
        tx = Transaction(
            vin=[TransactionInput(PREV_TXID, k) for k in range(n)],
            vout=[TransactionOutput(90_000 * n, self.tr_desc.derive(0, branch_index=1).script_pubkey())],
        )
        psbt = PSBT(tx)
        for i, (kind, sh) in enumerate(specs):
            if kind == "taproot":
                self._taproot_input(psbt, i, sighash_type=sh)
            else:
                self._wpkh_input(psbt, i, sighash_type=sh)
        return psbt

    # -- run the real signing path -----------------------------------
    def sign(self, psbt, forced_sighash=None):
        fout = BytesIO()
        wallets, meta = self.manager.preprocess_psbt(BytesIO(psbt.serialize()), fout)
        fout.seek(0)
        psbtv = PSBTView.view(fout)
        out = BytesIO()
        self.manager.sign_psbtview(psbtv, out, wallets, forced_sighash)
        return PSBT.parse(out.getvalue()), meta

    def cleanup(self):
        clear_testdir()
        gc.collect()


def _taproot_keypath_sig(signed_input):
    assert signed_input.final_scriptwitness is not None, "no taproot key-path witness"
    items = signed_input.final_scriptwitness.items
    assert len(items) == 1, items
    return items[0]


def _verify_taproot_sig(psbt, index, sig, sighash):
    values = [inp.utxo.value for inp in psbt.inputs]
    scripts = [inp.utxo.script_pubkey for inp in psbt.inputs]
    digest = psbt.tx.sighash_taproot(
        index, script_pubkeys=scripts, values=values, sighash=sighash
    )
    pub = PublicKey.from_xonly(scripts[index].data[2:])
    return pub.schnorr_verify(SchnorrSig.parse(sig[:64]), digest)


class TaprootDefaultSighashE2ETest(TestCase):
    def setUp(self):
        clear_testdir()
        self.fx = _Fixture()

    def tearDown(self):
        self.fx.cleanup()

    def test_implicit_default_produces_bare_64_byte_schnorr_sig(self):
        """Case 1: taproot PSBT with no PSBT_IN_SIGHASH_TYPE."""
        psbt = self.fx.build([("taproot", None)])
        signed, meta = self.fx.sign(psbt)

        # SIGHASH.DEFAULT selected -> not flagged as a custom sighash
        self.assertNotIn("sighash", meta["inputs"][0])

        sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(sig), 64)
        self.assertTrue(_verify_taproot_sig(psbt, 0, sig, SIGHASH.DEFAULT))
        self.assertFalse(_verify_taproot_sig(psbt, 0, sig, SIGHASH.ALL))

    def test_explicit_default_zero_is_preserved(self):
        """Case 2: taproot PSBT with explicit SIGHASH.DEFAULT (0x00)."""
        psbt = self.fx.build([("taproot", SIGHASH.DEFAULT)])
        signed, meta = self.fx.sign(psbt)

        # explicit 0 must not fall back to ALL and must not be "custom"
        self.assertNotIn("sighash", meta["inputs"][0])

        sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(sig), 64)
        self.assertTrue(_verify_taproot_sig(psbt, 0, sig, SIGHASH.DEFAULT))

    def test_explicit_zero_override_is_preserved(self):
        psbt = self.fx.build([("taproot", None)])
        signed, _ = self.fx.sign(psbt, forced_sighash=SIGHASH.DEFAULT)

        sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(sig), 64)
        self.assertTrue(_verify_taproot_sig(psbt, 0, sig, SIGHASH.DEFAULT))

    def test_explicit_all_produces_65_byte_sig_ending_in_0x01(self):
        """Case 3: taproot PSBT with explicit SIGHASH.ALL (0x01)."""
        psbt = self.fx.build([("taproot", SIGHASH.ALL)])
        signed, meta = self.fx.sign(psbt)

        # taproot ALL is non-default -> flagged for the confirmation UI
        self.assertEqual(meta["inputs"][0].get("sighash"), "ALL")

        sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(sig), 65)
        self.assertEqual(sig[-1], SIGHASH.ALL)
        self.assertTrue(_verify_taproot_sig(psbt, 0, sig, SIGHASH.ALL))
        self.assertFalse(_verify_taproot_sig(psbt, 0, sig, SIGHASH.DEFAULT))

    def test_old_falsy_zero_bug_would_regress_this(self):
        """
        Explicit reproduction of the #302 bug: the pre-fix expression
        ``sighash or inp.sighash_type or self.DEFAULT_SIGHASH`` collapses
        an implicit taproot 0 to SIGHASH.ALL.
        """
        psbt = self.fx.build([("taproot", None)])
        fout = BytesIO()
        wallets, _ = self.fx.manager.preprocess_psbt(BytesIO(psbt.serialize()), fout)
        fout.seek(0)
        psbtv = PSBTView.view(fout)

        buggy = None or (psbtv.input(0).sighash_type) or self.fx.manager.DEFAULT_SIGHASH
        fixed = self.fx.manager.default_sighash(psbtv.input(0))
        self.assertEqual(buggy, SIGHASH.ALL)
        self.assertEqual(fixed, SIGHASH.DEFAULT)


class NonTaprootRegressionE2ETest(TestCase):
    def setUp(self):
        clear_testdir()
        self.fx = _Fixture()

    def tearDown(self):
        self.fx.cleanup()

    def test_wpkh_without_sighash_still_uses_sighash_all(self):
        """Case 4: PR #399 must not change legacy/segwit behaviour."""
        psbt = self.fx.build([("wpkh", None)])
        signed, meta = self.fx.sign(psbt)

        self.assertNotIn("sighash", meta["inputs"][0])
        sigs = list(signed.inputs[0].partial_sigs.values())
        self.assertEqual(len(sigs), 1)
        # DER sig + trailing SIGHASH_ALL byte
        self.assertEqual(sigs[0][-1], SIGHASH.ALL)
        self.assertNotEqual(len(sigs[0]), 64)


class MixedInputSighashE2ETest(TestCase):
    def setUp(self):
        clear_testdir()
        self.fx = _Fixture()

    def tearDown(self):
        self.fx.cleanup()

    def test_per_input_default_is_applied_independently(self):
        """
        Case 5: one taproot + one wpkh input, neither carrying an explicit
        sighash. The taproot input must resolve to DEFAULT (64-byte bare
        sig) and the wpkh input to ALL (trailing 0x01) in the SAME psbt.
        """
        psbt = self.fx.build([("taproot", None), ("wpkh", None)])
        signed, meta = self.fx.sign(psbt)

        tr_sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(tr_sig), 64)

        wpkh_sig = list(signed.inputs[1].partial_sigs.values())[0]
        self.assertEqual(wpkh_sig[-1], SIGHASH.ALL)

        self.assertNotIn("sighash", meta["inputs"][0])
        self.assertNotIn("sighash", meta["inputs"][1])

    def test_taproot_all_flagged_but_wpkh_default_not(self):
        psbt = self.fx.build([("taproot", SIGHASH.ALL), ("wpkh", None)])
        signed, meta = self.fx.sign(psbt)

        self.assertEqual(meta["inputs"][0].get("sighash"), "ALL")
        self.assertNotIn("sighash", meta["inputs"][1])

        self.assertEqual(len(_taproot_keypath_sig(signed.inputs[0])), 65)
        self.assertEqual(
            list(signed.inputs[1].partial_sigs.values())[0][-1], SIGHASH.ALL
        )


class ConfirmSighashesE2ETest(TestCase):
    """
    confirm_sighashes() must treat a taproot input carrying an explicit
    SIGHASH_ALL as a custom sighash - it is non-default for taproot and
    the transaction screen already shows it as such.
    """

    def setUp(self):
        clear_testdir()
        self.fx = _Fixture()
        from apps.wallets import manager as _mgr
        self._mgr_mod = _mgr
        self._orig_prompt = _mgr.Prompt
        _mgr.Prompt = _FakePrompt

    def tearDown(self):
        self._mgr_mod.Prompt = self._orig_prompt
        self.fx.cleanup()

    def _meta(self, specs):
        fout = BytesIO()
        _, meta = self.fx.manager.preprocess_psbt(
            BytesIO(self.fx.build(specs).serialize()), fout
        )
        return meta

    def test_taproot_all_triggers_custom_sighash_prompt(self):
        meta = self._meta([("taproot", SIGHASH.ALL)])
        screens = _Screens()
        res = _run(self.fx.manager.confirm_sighashes(meta, screens))
        self.assertEqual(len(screens.log), 1)  # custom-sighash Prompt shown
        self.assertIsNone(res)  # user confirmed -> sign as provided

    def test_taproot_default_does_not_trigger_prompt(self):
        meta = self._meta([("taproot", None)])
        screens = _Screens()
        res = _run(self.fx.manager.confirm_sighashes(meta, screens))
        self.assertEqual(screens.log, [])  # no Prompt shown
        self.assertIsNone(res)

    def test_plain_wpkh_does_not_trigger_prompt(self):
        meta = self._meta([("wpkh", None)])
        screens = _Screens()
        res = _run(self.fx.manager.confirm_sighashes(meta, screens))
        self.assertEqual(screens.log, [])  # no Prompt shown
        self.assertIsNone(res)

    def test_only_sign_all_when_taproot_all_is_only_input(self):
        psbt = self.fx.build([("taproot", SIGHASH.ALL)])
        meta = self._meta([("taproot", SIGHASH.ALL)])
        screens = _Screens(response=False)
        sighash = _run(self.fx.manager.confirm_sighashes(meta, screens))

        self.assertEqual(screens.screens[0].kwargs["cancel_text"], "Only sign ALL")
        self.assertEqual(sighash, SIGHASH.ALL)
        signed, _ = self.fx.sign(psbt, forced_sighash=sighash)
        sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(sig), 65)
        self.assertEqual(sig[-1], SIGHASH.ALL)
        self.assertTrue(_verify_taproot_sig(psbt, 0, sig, SIGHASH.ALL))

    def test_only_sign_all_when_every_input_is_custom(self):
        specs = [("taproot", SIGHASH.ALL), ("taproot", SIGHASH.NONE)]
        psbt = self.fx.build(specs)
        meta = self._meta(specs)
        screens = _Screens(response=False)
        sighash = _run(self.fx.manager.confirm_sighashes(meta, screens))

        self.assertEqual(screens.screens[0].kwargs["cancel_text"], "Only sign ALL")
        self.assertEqual(sighash, SIGHASH.ALL)
        signed, _ = self.fx.sign(psbt, forced_sighash=sighash)
        sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(sig), 65)
        self.assertEqual(sig[-1], SIGHASH.ALL)
        self.assertTrue(_verify_taproot_sig(psbt, 0, sig, SIGHASH.ALL))
        self.assertIsNone(signed.inputs[1].final_scriptwitness)

    def test_only_sign_all_includes_explicit_taproot_all(self):
        psbt = self.fx.build([("taproot", SIGHASH.ALL), ("wpkh", None)])
        meta = self._meta([("taproot", SIGHASH.ALL), ("wpkh", None)])
        screens = _Screens(response=False)
        sighash = _run(self.fx.manager.confirm_sighashes(meta, screens))

        self.assertEqual(screens.screens[0].kwargs["cancel_text"], "Only sign ALL")
        self.assertEqual(sighash, SIGHASH.ALL)
        signed, _ = self.fx.sign(psbt, forced_sighash=sighash)
        sig = _taproot_keypath_sig(signed.inputs[0])
        self.assertEqual(len(sig), 65)
        self.assertEqual(sig[-1], SIGHASH.ALL)
        self.assertTrue(_verify_taproot_sig(psbt, 0, sig, SIGHASH.ALL))
        self.assertEqual(list(signed.inputs[1].partial_sigs.values())[0][-1], SIGHASH.ALL)

    def test_only_sign_all_skips_taproot_none(self):
        psbt = self.fx.build([("taproot", SIGHASH.NONE), ("wpkh", None)])
        meta = self._meta([("taproot", SIGHASH.NONE), ("wpkh", None)])
        screens = _Screens(response=False)
        sighash = _run(self.fx.manager.confirm_sighashes(meta, screens))

        self.assertEqual(screens.screens[0].kwargs["cancel_text"], "Only sign ALL")
        self.assertEqual(sighash, SIGHASH.ALL)
        signed, _ = self.fx.sign(psbt, forced_sighash=sighash)
        self.assertIsNone(signed.inputs[0].final_scriptwitness)
        self.assertEqual(list(signed.inputs[1].partial_sigs.values())[0][-1], SIGHASH.ALL)

    def test_declining_when_all_inputs_are_custom_cancels(self):
        meta = self._meta([("taproot", SIGHASH.NONE)])
        screens = _Screens(response=False)
        self.assertIs(_run(self.fx.manager.confirm_sighashes(meta, screens)), False)
        self.assertEqual(screens.screens[0].kwargs["cancel_text"], "Cancel")


class LiquidSighashE2ETest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.manager = get_wallets_app(self.keystore, "elementsregtest").manager
        from apps.wallets.liquid import manager as liquid_manager
        self._liquid_manager = liquid_manager
        self._get_preallocated_ram = liquid_manager.get_preallocated_ram
        # This unblinded fixture does not use the firmware's proof buffer.
        liquid_manager.get_preallocated_ram = lambda: (0, 0)

    def tearDown(self):
        self._liquid_manager.get_preallocated_ram = self._get_preallocated_ram
        clear_testdir()
        gc.collect()

    def _pset(self, sighash=None):
        desc = self.manager.wallets[0].descriptor.derive(0, branch_index=0)
        pub = desc.keys[0].get_public_key()
        asset = bytes(range(32))
        tx = LTransaction(
            vin=[LTransactionInput(PREV_TXID, 0)],
            vout=[
                LTransactionOutput(asset, 90_000, desc.script_pubkey()),
                LTransactionOutput(asset, 10_000, Script()),
            ],
        )
        pset = PSET(tx)
        inp = pset.inputs[0]
        inp.witness_utxo = LTransactionOutput(asset, 100_000, desc.script_pubkey())
        inp.bip32_derivations[pub] = DerivationPath(
            self.keystore.fingerprint, [H + 84, H + 1, H, 0, 0]
        )
        inp.sighash_type = sighash
        return pset

    def test_implicit_default_signs_with_all_and_rangeproof(self):
        pset = self._pset()
        filled = BytesIO()
        wallets, meta = self.manager.preprocess_psbt(BytesIO(pset.serialize()), filled)
        self.assertNotIn("sighash", meta["inputs"][0])

        filled.seek(0)
        out = BytesIO()
        self.manager.sign_psbtview(PSETView.view(filled), out, wallets, None)
        signed = PSET.parse(out.getvalue())
        sigs = list(signed.inputs[0].partial_sigs.values())
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0][-1], LSIGHASH.ALL | LSIGHASH.RANGEPROOF)

    def test_explicit_zero_is_rejected_during_preprocessing(self):
        pset = self._pset(SIGHASH.DEFAULT)
        with self.assertRaises(WalletError):
            self.manager.preprocess_psbt(BytesIO(pset.serialize()), BytesIO())
