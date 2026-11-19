import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

import asyncio
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch
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
            if len(shown_screens) == 1:
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
        self.assertIn("same output script", shown_screens[1].args[1])
        scanned_target_decodes = [
            call for call in decode_address.call_args_list
            if call.args[0] == unconfidential_address
        ]
        self.assertEqual(len(scanned_target_decodes), 1)

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
