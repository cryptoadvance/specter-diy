import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

import asyncio
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch
from apps.wallets.wallet import WalletError
from apps.wallets.screens import WalletScreen
import gc

import apps.wallets.manager as wallet_manager_module
import apps.wallets.liquid.manager as liquid_manager_module
from embit.liquid.addresses import to_unconfidential
from tests.util import clear_testdir, get_keystore, get_wallets_app


class _DummyScreen:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyMenu(_DummyScreen):
    pass


class _DummyPrompt(_DummyScreen):
    pass


class WalletAddressVerificationFlowTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def _process_qr(self, app, qr_payload):
        shown_screens = []

        async def show_screen(screen):
            shown_screens.append(screen)
            if isinstance(screen, _DummyMenu):
                return app.manager.wallets[0]
            if isinstance(screen, _DummyPrompt):
                return True
            return None

        with patch.object(wallet_manager_module, "Menu", _DummyMenu), patch.object(
            wallet_manager_module, "Prompt", _DummyPrompt
        ), patch.object(wallet_manager_module, "WalletScreen", _DummyScreen):
            result = asyncio.run(
                app.process_host_command(BytesIO(qr_payload.encode()), show_screen)
            )
        return result, shown_screens

    def test_bitcoin_qr_selects_wallet_and_verifies_derived_address(self):
        app = get_wallets_app(self.keystore, "regtest")
        address, _ = app.manager.wallets[0].get_address(0, app.manager.network)

        result, shown_screens = self._process_qr(app, "bitcoin:" + address)

        self.assertTrue(result)
        self.assertEqual(len(shown_screens), 2)

    def test_liquid_qr_verifies_unconfidential_form_of_wallet_address(self):
        app = get_wallets_app(self.keystore, "liquidv1")
        confidential_address, _ = app.manager.wallets[0].get_address(
            5, app.manager.network
        )
        unconfidential_address = to_unconfidential(confidential_address)

        original_to_unconfidential = liquid_manager_module.to_unconfidential
        with patch.object(
            liquid_manager_module,
            "to_unconfidential",
            wraps=original_to_unconfidential,
        ) as decode_address:
            result, shown_screens = self._process_qr(
                app, "liquid:" + unconfidential_address
            )

        self.assertTrue(result)
        self.assertEqual(len(shown_screens), 3)
        self.assertIsInstance(shown_screens[1], _DummyPrompt)
        self.assertIn("output script", shown_screens[1].args[1])
        scanned_target_decodes = [
            call for call in decode_address.call_args_list
            if call.args[0] == unconfidential_address
        ]
        self.assertEqual(len(scanned_target_decodes), 1)

    def test_indexed_liquid_unconfidential_scan_requires_warning(self):
        app = get_wallets_app(self.keystore, "liquidv1")
        address, _ = app.manager.wallets[0].get_address(5, app.manager.network)
        raw_address = to_unconfidential(address)
        payload = "liquidnetwork:" + raw_address + "?index=5"

        result, screens = self._process_qr(app, payload)

        self.assertTrue(result)
        self.assertEqual(len(screens), 2)
        self.assertIsInstance(screens[0], _DummyPrompt)
        self.assertIn("Script match only", screens[0].args[0])
        self.assertEqual(screens[1].kwargs["branch_index"], 0)

    def test_indexed_liquid_change_address_uses_change_branch(self):
        app = get_wallets_app(self.keystore, "liquidv1")
        address, _ = app.manager.wallets[0].get_address(2, app.manager.network, 1)
        payload = "liquidnetwork:" + address + "?index=2"

        result, screens = self._process_qr(app, payload)

        self.assertTrue(result)
        self.assertEqual(len(screens), 1)
        self.assertEqual(screens[0].kwargs["branch_index"], 1)

    def test_indexed_uppercase_bitcoin_address(self):
        app = get_wallets_app(self.keystore, "regtest")
        address, _ = app.manager.wallets[0].get_address(2, app.manager.network)
        result, screens = self._process_qr(
            app, "bitcoin:" + address.upper() + "?index=2"
        )

        self.assertTrue(result)
        self.assertEqual(len(screens), 1)
        self.assertEqual(screens[0].args[2], 2)

    def test_liquid_confidential_qr_exact_match_needs_no_script_prompt(self):
        app = get_wallets_app(self.keystore, "liquidv1")
        confidential_address, _ = app.manager.wallets[0].get_address(
            0, app.manager.network
        )

        result, shown_screens = self._process_qr(
            app, "liquid:" + confidential_address
        )

        self.assertTrue(result)
        self.assertEqual(len(shown_screens), 2)

    def test_wallet_qr_roundtrip(self):
        for network in ("main", "regtest", "liquidv1", "liquidtestnet", "elementsregtest"):
            app = get_wallets_app(self.keystore, network)
            address, _ = app.manager.wallets[0].get_address(2, network)
            payload = WalletScreen.address_qr_payload(network, address)
            result, screens = self._process_qr(app, payload)
            self.assertTrue(result, network)
            self.assertEqual(screens[-1].args[2], 2)

    def test_mismatched_uri_scheme_is_rejected(self):
        for network, scheme in (
            ("regtest", "liquid"),
            ("liquidv1", "bitcoin"),
            ("liquidv1", "liquidtestnet"),
            ("liquidtestnet", "liquidnetwork"),
        ):
            app = get_wallets_app(self.keystore, network)
            address, _ = app.manager.wallets[0].get_address(0, network)
            with self.assertRaises(WalletError) as err:
                self._process_qr(app, scheme + ":" + address)
            self.assertIn("scheme does not match", str(err.exception))

    def test_raw_address_search_continues_to_next_batch(self):
        app = get_wallets_app(self.keystore, "regtest")
        address, _ = app.manager.wallets[0].get_address(26, app.manager.network, 1)
        result, screens = self._process_qr(app, address)
        self.assertTrue(result)
        self.assertIsInstance(screens[1], _DummyPrompt)
        self.assertEqual(screens[-1].args[2], 26)
        self.assertEqual(screens[-1].kwargs["branch_index"], 1)
