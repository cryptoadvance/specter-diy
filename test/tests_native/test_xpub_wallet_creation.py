"""
Regression tests for on-device single-sig wallet creation
(``src/apps/xpubs/xpubs.py``).

Covers:
* issue #393 - fresh Taproot wallets must use BIP86 (m/86'), with the account
  key genuinely re-derived, not relabelled;
* the standard script -> BIP-purpose mapping for all four single-sig types;
* the generic "recover using the displayed key" path that reproduces the
  valid-but-non-standard script/derivation pairs older Specter DIY firmware
  could create (issues #393, #281);
* coin_type normalisation, accounts, testnet, Liquid, deep BIP48 paths,
  cancel/back/decline.
"""
import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

import asyncio
import gc
import json
from binascii import hexlify
from io import BytesIO
from unittest import TestCase

from embit import bip32
from embit.descriptor import Descriptor
# liquid.networks is a superset of the Bitcoin NETWORKS (adds liquidv1, ...) -
# xpubs.py imports it too, so the tests must agree on coin_type / version bytes
from embit.liquid.networks import NETWORKS

from tests.util import get_keystore, get_xpubs_app, clear_testdir

# Official BIP86 test vector (mnemonic + first receive address).
BIP86_MNEMONIC = "abandon " * 11 + "about"
BIP86_FIRST_ADDR = "bc1p5cyxnuxmeuwuvkwfem96lqzszd02n6xdcjrs20cac6yqjjwudpxqkedrcr"


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class ScriptedScreens:
    """Scriptable show_screen double. Answers keyed by screen class name."""

    def __init__(self, answers):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.log = []

    async def __call__(self, screen):
        name = type(screen).__name__
        self.log.append(name)
        queue = self.answers.get(name)
        if queue:
            return queue.pop(0)
        return None


class WalletSink:
    """Captures `addwallet` descriptors sent to the wallets app."""

    def __init__(self, existing=None):
        self.existing = existing or []
        self.added = []

    async def __call__(self, stream, app=None):
        data = stream.read()
        if data == b"listwallets":
            return BytesIO(json.dumps(self.existing).encode()), {}
        text = data.decode()
        assert text.startswith("addwallet "), text
        name, desc = text[len("addwallet "):].split("&", 1)
        self.added.append((name, desc))
        return BytesIO(b""), {}


def _shown_xpub(app, derivation):
    """Reproduce exactly what show_xpub() hands to create_wallet()."""
    net = NETWORKS[app.network]
    x = app.keystore.get_xpub(derivation)
    canonical = x.to_base58(net["xpub"])
    fp = hexlify(app.keystore.fingerprint).decode()
    prefix = "[%s%s]" % (fp, derivation[1:])
    return derivation, canonical, prefix


def _origin_xpub(app, derivation):
    """(key-origin string, base58 xpub) for a path, as the app would emit it."""
    net = NETWORKS[app.network]
    x = app.keystore.get_xpub(derivation).to_base58(net["xpub"])
    fp = hexlify(app.keystore.fingerprint).decode()
    return "[%s/%s]" % (fp, derivation[2:]), x


def _expected_descriptor(app, derivation, script_tmpl):
    origin, x = _origin_xpub(app, derivation)
    return script_tmpl % (origin, x)


def _address(descriptor, net_name, branch, index):
    net = NETWORKS[net_name]
    d = Descriptor.from_string(descriptor)
    return d.derive(index, branch_index=branch).address(net)


class WalletCreationTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.app = get_xpubs_app(self.keystore, "main")

    def tearDown(self):
        clear_testdir()
        gc.collect()

    # -- helpers --------------------------------------------------------
    def _create(self, derivation, answers, network="main", account=0,
                keystore=None):
        if keystore is not None:
            self.keystore = keystore
        self.app = get_xpubs_app(self.keystore, network)
        self.app.account = account
        sink = WalletSink()
        self.app.communicate = sink
        screens = ScriptedScreens(answers)
        d, x, p = _shown_xpub(self.app, derivation)
        run(self.app.create_wallet(d, x, p, screens))
        return sink, screens

    def _desc(self, *a, **k):
        sink, _ = self._create(*a, **k)
        self.assertEqual(len(sink.added), 1)
        return sink.added[0][1]

    # ================================================================
    # standard creation: script type -> BIP purpose, genuine derivation
    # ================================================================
    def test_standard_types_derive_from_their_bip_purpose(self):
        cases = {
            "legacy":  (44, "pkh("),
            "nested":  (49, "sh(wpkh("),
            "wpkh":    (84, "wpkh("),
            "taproot": (86, "tr("),
        }
        # display a key on a foreign purpose so a real re-derivation must happen
        for key, (purpose, head) in cases.items():
            desc = self._desc(
                "m/45h/0h/0h",
                {"Menu": [key, "standard"], "InputScreen": ["w"]},
            )
            self.assertTrue(desc.startswith(head), desc)
            self.assertIn("/%dh/0h/0h]" % purpose, desc)
            std_origin, std_xpub = _origin_xpub(self.app, "m/%dh/0h/0h" % purpose)
            self.assertIn(std_xpub, desc)
            # the displayed m/45' key must not appear
            shown = self.keystore.get_xpub("m/45h/0h/0h").to_base58(
                NETWORKS["main"]["xpub"])
            self.assertNotIn(shown, desc)

    def test_standard_taproot_uses_bip86_no_extra_prompt(self):
        # key already on the standard path -> straight to naming, no dialog
        sink, screens = self._create(
            "m/86h/0h/0h", {"Menu": ["taproot"], "InputScreen": ["TR"]},
        )
        _, desc = sink.added[0]
        self.assertEqual(screens.log.count("Menu"), 1)
        self.assertEqual(
            desc, _expected_descriptor(self.app, "m/86h/0h/0h", "tr(%s%s/{0,1}/*)"))
        self.assertNotIn("/84h/", desc)

    def test_bip86_official_vector(self):
        ks = get_keystore(mnemonic=BIP86_MNEMONIC)
        desc = self._desc(
            "m/84h/0h/0h",
            {"Menu": ["taproot", "standard"], "InputScreen": ["v"]},
            keystore=ks,
        )
        self.assertIn("/86h/0h/0h]", desc)
        self.assertEqual(_address(desc, "main", 0, 0), BIP86_FIRST_ADDR)

    def test_issue393_single_key_taproot_rederives_m86(self):
        # "Single key" is an m/84' key; Standard Taproot must re-derive m/86'
        sink, screens = self._create(
            "m/84h/0h/0h",
            {"Menu": ["taproot", "standard"], "InputScreen": ["m"]},
        )
        _, desc = sink.added[0]
        self.assertEqual(screens.log.count("Menu"), 2)
        m86 = self.keystore.get_xpub("m/86h/0h/0h").to_base58(NETWORKS["main"]["xpub"])
        m84 = self.keystore.get_xpub("m/84h/0h/0h").to_base58(NETWORKS["main"]["xpub"])
        self.assertIn("/86h/0h/0h]", desc)
        self.assertIn(m86, desc)
        self.assertNotIn(m84, desc)

    # ================================================================
    # generic recovery: displayed key wrapped in the chosen script
    # ================================================================
    def _recover(self, derivation, wtype, network="main", account=0):
        sink, _ = self._create(
            derivation,
            {"Menu": [wtype, "recover"], "Prompt": [True], "InputScreen": ["r"]},
            network=network, account=account,
        )
        self.assertEqual(len(sink.added), 1)
        return sink.added[0][1]

    def test_recover_m84_with_legacy(self):
        desc = self._recover("m/84h/0h/0h", "legacy")
        self.assertEqual(
            desc, _expected_descriptor(self.app, "m/84h/0h/0h", "pkh(%s%s/{0,1}/*)"))
        self.assertNotIn("/44h/", desc)

    def test_recover_m49_with_taproot(self):
        desc = self._recover("m/49h/0h/0h", "taproot")
        self.assertEqual(
            desc, _expected_descriptor(self.app, "m/49h/0h/0h", "tr(%s%s/{0,1}/*)"))
        self.assertNotIn("/86h/", desc)

    def test_recover_bip48_multisig_path_with_native_segwit(self):
        desc = self._recover("m/48h/0h/0h/2h", "wpkh")
        # the full four-level path is preserved, not collapsed to m/84'
        self.assertEqual(
            desc,
            _expected_descriptor(self.app, "m/48h/0h/0h/2h", "wpkh(%s%s/{0,1}/*)"))
        self.assertIn("/48h/0h/0h/2h]", desc)
        self.assertNotIn("/84h/", desc)
        Descriptor.from_string(desc)  # parses

    def test_recover_m84_with_nested_segwit(self):
        desc = self._recover("m/84h/0h/0h", "nested")
        self.assertEqual(
            desc,
            _expected_descriptor(self.app, "m/84h/0h/0h", "sh(wpkh(%s%s/{0,1}/*))"))

    def test_recover_custom_path_with_taproot(self):
        desc = self._recover("m/1234h/5h/6h", "taproot")
        self.assertEqual(
            desc,
            _expected_descriptor(self.app, "m/1234h/5h/6h", "tr(%s%s/{0,1}/*)"))
        self.assertIn("/1234h/5h/6h]", desc)
        Descriptor.from_string(desc)

    def test_recover_taproot_m84_reproduces_pre_pr405_wallet(self):
        # the case PR #405 special-cased; the generic path must match exactly
        desc = self._recover("m/84h/0h/0h", "taproot")
        expected = _expected_descriptor(self.app, "m/84h/0h/0h", "tr(%s%s/{0,1}/*)")
        self.assertEqual(desc, expected)
        self.assertEqual(_address(desc, "main", 0, 0),
                         _address(expected, "main", 0, 0))

    # ================================================================
    # standard vs recovery differ
    # ================================================================
    def test_standard_vs_recovery_same_key_differ(self):
        # displayed m/84'/0'/0', wallet type Legacy
        std = self._desc("m/84h/0h/0h",
                         {"Menu": ["legacy", "standard"], "InputScreen": ["s"]})
        rec = self._recover("m/84h/0h/0h", "legacy")
        self.assertIn("/44h/0h/0h]", std)
        self.assertIn("/84h/0h/0h]", rec)
        self.assertNotEqual(_address(std, "main", 0, 0), _address(rec, "main", 0, 0))

    def test_change_branch_addresses(self):
        for desc in (
            self._desc("m/86h/0h/0h", {"Menu": ["taproot"], "InputScreen": ["x"]}),
            self._recover("m/84h/0h/0h", "taproot"),
        ):
            self.assertNotEqual(_address(desc, "main", 0, 0),
                                _address(desc, "main", 1, 0))

    # ================================================================
    # coin_type
    # ================================================================
    def test_standard_normalises_coin_type_to_network(self):
        # mainnet: displayed m/84'/1'/5' -> standard m/86'/0'/5'
        desc = self._desc("m/84h/1h/5h",
                          {"Menu": ["taproot", "standard"], "InputScreen": ["x"]},
                          account=5)
        self.assertIn("/86h/0h/5h]", desc)
        self.assertNotIn("/1h/", desc.split("]", 1)[0])
        # testnet: displayed m/84'/0'/5' -> standard m/86'/1'/5'
        desc = self._desc("m/84h/0h/5h",
                          {"Menu": ["taproot", "standard"], "InputScreen": ["x"]},
                          network="test", account=5)
        self.assertIn("/86h/1h/5h]", desc)

    def test_recovery_preserves_coin_type(self):
        desc = self._recover("m/84h/1h/0h", "taproot")
        self.assertIn("/84h/1h/0h]", desc)
        self.assertEqual(
            desc, _expected_descriptor(self.app, "m/84h/1h/0h", "tr(%s%s/{0,1}/*)"))

    def test_wrong_coin_type_is_not_recommended(self):
        # mainnet, displayed m/84'/1'/5' - purpose matches wpkh but coin_type
        # does not: the wallet-type menu must not preselect it, so picking wpkh
        # still routes through the standard/recovery choice.
        sink, screens = self._create(
            "m/84h/1h/5h",
            {"Menu": ["wpkh", "standard"], "InputScreen": ["x"]},
            account=5,
        )
        self.assertEqual(screens.log.count("Menu"), 2)
        self.assertIn("/84h/0h/5h]", sink.added[0][1])

    # ================================================================
    # accounts
    # ================================================================
    def test_account_zero_and_non_zero(self):
        d0 = self._desc("m/86h/0h/0h", {"Menu": ["taproot"], "InputScreen": ["a"]})
        self.assertIn("/86h/0h/0h]", d0)
        d5 = self._desc("m/86h/0h/5h", {"Menu": ["taproot"], "InputScreen": ["a"]},
                        account=5)
        self.assertIn("/86h/0h/5h]", d5)
        # account carried across a re-derivation
        d7 = self._desc("m/84h/0h/7h",
                        {"Menu": ["taproot", "standard"], "InputScreen": ["a"]},
                        account=7)
        self.assertIn("/86h/0h/7h]", d7)

    def test_bip48_account_carried_into_standard_wallet(self):
        # m/48'/0'/3'/2' -> Native Segwit standard uses account 3
        desc = self._desc("m/48h/0h/3h/2h",
                          {"Menu": ["wpkh", "standard"], "InputScreen": ["x"]})
        self.assertIn("/84h/0h/3h]", desc)

    # ================================================================
    # testnet
    # ================================================================
    def test_testnet_standard_and_recovery(self):
        std = self._desc("m/86h/1h/0h", {"Menu": ["taproot"], "InputScreen": ["t"]},
                         network="test")
        self.assertIn("/86h/1h/0h]", std)
        rec = self._recover("m/84h/1h/0h", "taproot", network="test")
        self.assertIn("/84h/1h/0h]", rec)

    # ================================================================
    # Liquid
    # ================================================================
    def test_liquid_standard_uses_registered_coin_type(self):
        # liquidv1's coin_type is 1776 (embit NETWORKS), not 0
        self.assertEqual(NETWORKS["liquidv1"]["bip32"], 1776)
        desc = self._desc("m/84h/1776h/0h",
                          {"Menu": ["wpkh"], "InputScreen": ["l"]},
                          network="liquidv1")
        self.assertTrue(desc.startswith("blinded(slip77("))
        self.assertIn("wpkh([", desc)
        self.assertIn("/84h/1776h/0h]", desc)

    def test_liquid_recovery_preserves_displayed_path(self):
        desc = self._recover("m/84h/0h/0h", "taproot", network="liquidv1")
        self.assertTrue(desc.startswith("blinded(slip77("))
        self.assertIn("tr([", desc)
        self.assertIn("/84h/0h/0h]", desc)

    # ================================================================
    # cancel / back / decline -> nothing created
    # ================================================================
    def test_wallet_type_menu_back(self):
        sink, _ = self._create("m/86h/0h/0h", {"Menu": [255]})
        self.assertEqual(sink.added, [])

    def test_choice_menu_cancel(self):
        sink, _ = self._create("m/84h/0h/0h", {"Menu": ["taproot", 255]})
        self.assertEqual(sink.added, [])

    def test_recovery_warning_declined(self):
        sink, _ = self._create(
            "m/84h/0h/0h",
            {"Menu": ["taproot", "recover"], "Prompt": [False]},
        )
        self.assertEqual(sink.added, [])

    def test_name_prompt_cancelled(self):
        sink, _ = self._create(
            "m/86h/0h/0h", {"Menu": ["taproot"], "InputScreen": [""]},
        )
        self.assertEqual(sink.added, [])

    def test_unknown_menu_value_creates_nothing(self):
        sink, _ = self._create("m/86h/0h/0h", {"Menu": ["bogus"]})
        self.assertEqual(sink.added, [])


class LegacyDescriptorImportTest(TestCase):
    """Old-style non-standard descriptors must still import and match keys."""

    def setUp(self):
        clear_testdir()
        from tests.util import get_wallets_app
        self.keystore = get_keystore()
        self.wallets_app = get_wallets_app(self.keystore, "main")
        self.manager = self.wallets_app.manager

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def _roundtrip(self, name, tmpl, der):
        net = NETWORKS["main"]
        x = self.keystore.get_xpub(der).to_base58(net["xpub"])
        fp = hexlify(self.keystore.fingerprint).decode()
        desc = "%s&%s" % (name, tmpl % ("[%s/%s]" % (fp, der[2:]), x))
        w = self.manager.parse_wallet(desc)
        self.assertEqual(w.name, name)
        self.assertIn(der[2:], str(w.descriptor))
        return w

    def test_legacy_m84_taproot_descriptor_parses(self):
        self._roundtrip("Legacy TR", "tr(%s%s/{0,1}/*)", "m/84h/0h/0h")

    def test_legacy_m84_pkh_descriptor_parses(self):
        self._roundtrip("Legacy PKH", "pkh(%s%s/{0,1}/*)", "m/84h/0h/0h")

    def test_legacy_bip48_wpkh_descriptor_parses(self):
        self._roundtrip("Legacy 48", "wpkh(%s%s/{0,1}/*)", "m/48h/0h/0h/2h")
