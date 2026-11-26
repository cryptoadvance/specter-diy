import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

import asyncio
from unittest import TestCase
from unittest.mock import patch
from app import BaseApp
from io import BytesIO
import gc

from embit import ec, script, base58
from embit.liquid.addresses import address as liquid_address
from embit.liquid.networks import NETWORKS as LIQUID_NETWORKS
from embit.networks import NETWORKS
from tests.util import get_keystore, get_wallets_app, clear_testdir
from apps.wallets.manager import (
    ADDRESS_URI_SCHEMES,
    ADD_WALLET,
    SIGN_PSBT,
    VERIFY_ADDRESS,
    address_uri_scheme,
)
from apps.wallets.liquid.manager import LWalletManager
from apps.wallets.wallet import WalletError

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
        # Keep the URI scheme intact until address/network verification.
        self.assertEqual(stream.read().decode(), DOC_ADDRESS_REQUEST)

    def test_address_uri_scheme_requires_colon(self):
        for scheme in ADDRESS_URI_SCHEMES:
            with self.subTest(scheme=scheme):
                self.assertIsNone(address_uri_scheme(scheme))
                self.assertIsNone(address_uri_scheme(scheme.encode()))

    def test_regtest_legacy_address_hint_includes_regtest(self):
        public_key = ec.PrivateKey(b"\x00" * 31 + b"\x01").get_public_key()
        regtest_address = script.p2pkh(public_key).address(NETWORKS["regtest"])

        networks, name = self.manager.address_network_hint(regtest_address)

        self.manager.validate_address(regtest_address)
        self.assertIn("regtest", networks)
        self.assertIn("Regtest", name)
        invalid_address = regtest_address[:-1] + (
            "1" if regtest_address[-1] != "1" else "2"
        )
        with self.assertRaises(WalletError):
            self.manager.validate_address(invalid_address)

    def test_testnet_bech32_hint_does_not_include_regtest(self):
        networks, name = self.manager.address_network_hint("tb1qexample")

        self.assertEqual(networks, ("test", "signet"))
        self.assertEqual(name, "Bitcoin Testnet or Signet")

    def test_bitcoin_mainnet_hint_recognizes_base58_and_bech32(self):
        for address in ("1example", "3example", "bc1qexample"):
            self.assertEqual(
                self.manager.address_network_hint(address),
                ("main", "Bitcoin Mainnet"),
            )

    def test_address_prefix_checks_work_with_micropython_strings(self):
        class StrictString(str):
            def lower(self):
                return StrictString(super().lower())

            def startswith(self, prefix, *args):
                if not isinstance(prefix, str):
                    raise TypeError("MicroPython requires a string prefix")
                return super().startswith(prefix, *args)

        for prefix, expected in (
            ("bc1", "main"), ("1", "main"), ("3", "main"),
            ("tb1", ("test", "signet")), ("bcrt1", "regtest"),
            ("m", ("test", "signet", "regtest")),
            ("n", ("test", "signet", "regtest")),
            ("2", ("test", "signet", "regtest")),
            ("ex1", "liquidv1"), ("lq1", "liquidv1"),
            ("tex1", "liquidtestnet"), ("tlq1", "liquidtestnet"),
            ("ert1", "elementsregtest"), ("el1", "elementsregtest"),
        ):
            address = StrictString(prefix + "example")
            self.assertEqual(self.manager.address_network_hint(address)[0], expected)
        for prefix in ("bc1", "tb1", "bcrt1"):
            address = StrictString(prefix.upper() + "EXAMPLE")
            self.assertEqual(self.manager.normalize_verification_address(address), address.lower())

        liquid = LWalletManager.__new__(LWalletManager)
        output_script = script.Script(b"\\x00\\x14" + b"\\x11" * 20)
        key = ec.PrivateKey(b"\\x00" * 31 + b"\\x01").get_public_key()
        for network in ("liquidv1", "liquidtestnet", "elementsregtest"):
            address = liquid_address(output_script, key, network=LIQUID_NETWORKS[network])
            strict = StrictString(address.upper())
            with patch("apps.wallets.liquid.manager.to_unconfidential", return_value=address):
                liquid.validate_address(strict)
            self.assertEqual(liquid.address_match_type(strict, address), "exact")

    def test_invalid_address_is_rejected_before_wallet_selection(self):
        shown_screens = []

        async def show_screen(screen):
            shown_screens.append(screen)
            return self.manager.wallets[0]

        with self.assertRaises(WalletError):
            asyncio.run(
                self.wallets_app.process_host_command(
                    BytesIO(b"bitcoin:bcrt1invalid"), show_screen
                )
            )

        self.assertEqual(shown_screens, [])

    def test_invalid_index_value_raises_wallet_error(self):
        address, _ = self.manager.wallets[0].get_address(0, self.manager.network)
        shown_screens = []

        async def show_screen(screen):
            shown_screens.append(screen)
            return self.manager.wallets[0]

        with self.assertRaises(WalletError):
            asyncio.run(
                self.wallets_app.process_host_command(
                    BytesIO(
                        ("bitcoin:%s?index=not-an-integer" % address).encode()
                    ),
                    show_screen,
                )
            )

        self.assertEqual(shown_screens, [])

    def test_seed_payloads_are_not_claimed_by_wallet_manager(self):
        for network in ("regtest", "liquidv1"):
            manager = get_wallets_app(self.keystore, network).manager
            with patch.object(BaseApp, "get_prefix", BaseApp._native_original_get_prefix):
                for payload in (
                    b"0000" * 11 + b"0003",
                    b"0000" * 23 + b"0102",
                    b"ABCD1234EFGH5678",
                    b"0123456789ABCDEF0123456789ABCDEF",
                    b"\x00" * 16,
                    b"\x00" * 32,
                ):
                    self.assertFalse(manager.can_process(BytesIO(payload)), (network, payload))

    def test_raw_address_and_late_index_are_detected(self):
        for network in ("regtest", "liquidv1", "liquidtestnet", "elementsregtest"):
            manager = get_wallets_app(self.keystore, network).manager
            address, _ = manager.wallets[0].get_address(2, network)
            for payload in (address, address + "?index=2"):
                with patch.object(BaseApp, "get_prefix", BaseApp._native_original_get_prefix):
                    self.assertTrue(manager.can_process(BytesIO(payload.encode())), network)

    def test_mixed_case_uri_scheme_is_detected(self):
        cmd, stream = self._parse_command(DOC_ADDRESS_REQUEST.replace("bitcoin:", "BiTcOiN:").encode())
        self.assertEqual(cmd, VERIFY_ADDRESS)
        self.assertTrue(stream.read().startswith(b"BiTcOiN:"))

    def test_raw_addresses_are_recognized_across_networks(self):
        public_key = ec.PrivateKey(b"\x00" * 31 + b"\x01").get_public_key()
        output_script = script.p2sh(script.p2wpkh(public_key))
        for network in ("liquidv1", "liquidtestnet", "elementsregtest"):
            net = LIQUID_NETWORKS[network]
            for key in (None, public_key):
                address = liquid_address(output_script, key, network=net)
                self.assertTrue(self.manager.can_process(BytesIO(address.encode())))
                self.assertEqual(self.manager.address_network_hint(address)[0], network)

    def test_malformed_raw_address_is_not_claimed(self):
        address, _ = self.manager.wallets[0].get_address(2, self.manager.network)
        invalid = address[:-1] + ("q" if address[-1] != "q" else "p")
        self.assertFalse(self.manager.can_process(BytesIO(invalid.encode())))
        invalid_liquid = base58.encode_check(LIQUID_NETWORKS["liquidv1"]["p2sh"] + b"\x01" * 19)
        self.assertFalse(self.manager.can_process(BytesIO(invalid_liquid.encode())))
