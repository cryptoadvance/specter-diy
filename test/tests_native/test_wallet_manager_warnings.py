import gc
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import asyncio

from unittest import TestCase

from tests.util import clear_testdir, get_keystore, get_wallets_app

HIGH_FEE = "Fee is 10.00% of the send amount - unusually high!"
LIQUID_UNASSESSABLE = (
    "Fee cannot be assessed automatically for this multi-asset transaction. "
    "Please verify the fee manually!"
)


class WalletManagerWarningsTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.manager = get_wallets_app(get_keystore(), "regtest").manager

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def warnings_for(self, fee, outputs, inputs=None, warnings=None):
        meta = {"fee": fee, "outputs": outputs, "inputs": inputs or []}
        if warnings is not None:
            meta["warnings"] = warnings
        self.manager.add_warnings(meta)
        return meta

    # --- threshold behaviour (fixed 10%) ------------------------------------

    def test_fee_below_threshold_does_not_warn(self):
        meta = self.warnings_for(999, [{"value": 10_000, "change": False}])
        self.assertEqual(meta.get("warnings", []), [])
        self.assertNotIn("fee_warning", meta)

    def test_fee_exactly_at_threshold_warns(self):
        meta = self.warnings_for(1_000, [{"value": 10_000, "change": False}])
        self.assertEqual(meta["warnings"], [HIGH_FEE])
        self.assertEqual(meta["fee_warning"], HIGH_FEE)

    def test_fee_above_threshold_warns(self):
        meta = self.warnings_for(1_001, [{"value": 10_000, "change": False}])
        self.assertEqual(
            meta["warnings"],
            ["Fee is 10.01% of the send amount - unusually high!"],
        )

    # --- fee basis --------------------------------------------------------

    def test_self_transfer_falls_back_to_verified_total_inputs(self):
        # every output goes back to an input wallet -> no send amount,
        # so the fee is compared against the verified input total
        meta = self.warnings_for(
            2_000,
            [{"value": 18_000, "change": True, "owned": True}],
            inputs=[{"value": 12_000}, {"value": 8_000}],
        )
        self.assertEqual(meta["fee_basis"], 20_000)
        self.assertFalse(meta["fee_basis_is_send_amount"])
        self.assertEqual(
            meta["warnings"],
            ["Fee is 10.00% of total inputs (self-transfer) - unusually high!"],
        )

    def test_multi_wallet_owned_outputs_excluded_from_fee_basis(self):
        # output 1 is a real recipient (1_000), output 2 is a wallet-to-wallet
        # transfer owned by an input wallet and must NOT inflate the basis
        meta = self.warnings_for(
            100,
            [
                {"value": 1_000, "change": False, "owned": False},
                {"value": 50_000, "change": False, "owned": True},
            ],
            inputs=[{"value": 51_100}],
        )
        self.assertEqual(meta["fee_basis"], 1_000)
        self.assertTrue(meta["fee_basis_is_send_amount"])
        self.assertEqual(meta["warnings"], [HIGH_FEE])

    def test_fee_percent_is_precomputed_for_reuse_by_the_screen(self):
        # the confirmation screen must not recompute the percentage; it
        # reads meta["fee_percent"] so it can never disagree with the warning
        meta = self.warnings_for(1_000, [{"value": 10_000, "change": False}])
        self.assertEqual(meta["fee_percent"], 10.0)

        below = self.warnings_for(500, [{"value": 10_000, "change": False}])
        self.assertEqual(below["fee_percent"], 5.0)
        self.assertNotIn("fee_warning", below)

        nofee = {"outputs": [{"value": 10_000, "change": False}], "inputs": []}
        self.manager.add_warnings(nofee)
        self.assertIsNone(nofee["fee_percent"])

    def test_fee_output_excluded_from_send_amount_basis(self):
        # an explicit fee output (as on Liquid) must not count as "sent"
        meta = self.warnings_for(
            1_000,
            [
                {"value": 10_000, "change": False, "owned": False},
                {"value": 1_000, "change": False, "fee_output": True},
            ],
        )
        self.assertEqual(meta["fee_basis"], 10_000)
        self.assertTrue(meta["fee_basis_is_send_amount"])
        self.assertEqual(meta["warnings"], [HIGH_FEE])

    # --- warning list handling ------------------------------------------

    def test_existing_warnings_are_preserved(self):
        meta = self.warnings_for(
            1_000,
            [{"value": 10_000, "change": False}],
            warnings=["Mixed inputs from different wallets!"],
        )
        self.assertEqual(
            meta["warnings"],
            ["Mixed inputs from different wallets!", HIGH_FEE],
        )

    def test_high_fee_warning_is_not_duplicated(self):
        meta = {
            "fee": 1_000,
            "outputs": [{"value": 10_000, "change": False}],
            "inputs": [],
        }
        self.manager.add_warnings(meta)
        self.manager.add_warnings(meta)
        self.assertEqual(meta["warnings"], [HIGH_FEE])

    def test_no_fee_or_zero_basis_does_not_warn(self):
        meta = {"outputs": [{"value": 0, "change": False}], "inputs": []}
        self.manager.add_warnings(meta)
        self.assertEqual(meta.get("warnings", []), [])

    def test_high_fee_sets_acknowledgement_flag(self):
        # a normal fee must not set the gate that confirm_transaction() checks
        normal = self.warnings_for(10, [{"value": 10_000, "change": False}])
        self.assertIsNone(normal.get("fee_warning"))

        high = self.warnings_for(1_000, [{"value": 10_000, "change": False}])
        self.assertEqual(high["fee_warning"], HIGH_FEE)

    # --- explicit acknowledgement before signing --------------------------

    @staticmethod
    def _run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _confirm_transaction(self, fee_ack, meta_extra=None):
        """Drive confirm_transaction() with everything stubbed except the
        fee-warning gate, and record whether the final confirmation is
        reached. Returns (result, final_reached)."""
        manager = self.manager
        reached = []

        async def show_screen(scr):
            return True

        async def fake_fee_warning(meta, show):
            return fee_ack

        async def fake_final(wallets, meta, show):
            reached.append(True)
            return True

        manager.confirm_fee_warning = fake_fee_warning
        manager.confirm_transaction_final = fake_final

        meta = {"inputs": [{}], "outputs": [], "signed_inputs": 0}
        if meta_extra:
            meta.update(meta_extra)
        wallets = {object(): {"amount": 0}}
        result = self._run(manager.confirm_transaction(wallets, meta, show_screen))
        return result, bool(reached)

    def test_confirm_transaction_aborts_when_high_fee_not_acknowledged(self):
        result, final_reached = self._confirm_transaction(fee_ack=False)
        self.assertIsNone(result)
        self.assertFalse(final_reached)

    def test_confirm_transaction_proceeds_once_high_fee_acknowledged(self):
        result, final_reached = self._confirm_transaction(fee_ack=True)
        self.assertEqual(result, {"sighash": None})
        self.assertTrue(final_reached)

    def test_confirm_fee_warning_is_noop_without_warning(self):
        shown = []

        async def show_screen(scr):
            shown.append(scr)
            return True

        proceed = self._run(
            self.manager.confirm_fee_warning({}, show_screen)
        )
        self.assertTrue(proceed)
        self.assertEqual(shown, [])

    def test_liquid_same_asset_uses_percentage_warning(self):
        liquid = get_wallets_app(get_keystore(), "elementsregtest").manager
        asset = b"a" * 32
        meta = {
            "fee": 1_000,
            "fee_asset": asset,
            "outputs": [
                {"value": 10_000, "asset_id": asset, "owned": False},
                {"value": 1_000, "asset_id": asset, "fee_output": True},
            ],
            "inputs": [{"value": 11_000, "asset_id": asset}],
        }
        liquid.add_warnings(meta)
        self.assertEqual(meta["fee_warning"], HIGH_FEE)
        self.assertEqual(meta["fee_percent"], 10.0)

    def test_liquid_different_asset_uses_manual_review_warning(self):
        liquid = get_wallets_app(get_keystore(), "elementsregtest").manager
        fee_asset = b"a" * 32
        sent_asset = b"b" * 32
        meta = {
            "fee": 1_000,
            "fee_asset": fee_asset,
            "outputs": [
                {"value": 10_000, "asset_id": sent_asset, "owned": False},
                {"value": 1_000, "asset_id": fee_asset, "fee_output": True},
            ],
            "inputs": [
                {"value": 10_000, "asset_id": sent_asset},
                {"value": 1_000, "asset_id": fee_asset},
            ],
        }
        liquid.add_warnings(meta)
        self.assertEqual(meta["fee_warning"], LIQUID_UNASSESSABLE)
        self.assertIsNone(meta["fee_percent"])
