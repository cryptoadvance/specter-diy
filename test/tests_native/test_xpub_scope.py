import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase
from embit import bip32

from apps.xpubs import scope as xpubauth_scope


MAIN = ("main", 0)
TEST = ("test", 1)


class ScopeParsingTest(TestCase):
    def test_single_exact_path(self):
        entries, total = xpubauth_scope.parse_scope("m/84h/0h/0h", *MAIN)
        self.assertEqual(total, 1)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].format(), "m/84h/0h/0h")

    def test_four_exact_paths(self):
        entries, total = xpubauth_scope.parse_scope(
            "m/84h/0h/0h;m/86h/0h/0h;m/48h/0h/0h/2h;m/48h/0h/1h/2h", *MAIN
        )
        self.assertEqual(total, 4)
        self.assertEqual(len(entries), 4)

    def test_bounded_range_count(self):
        entries, total = xpubauth_scope.parse_scope("m/84h/0h/{0-9}h", *MAIN)
        self.assertEqual(total, 10)

    def test_multiple_ranges_count(self):
        entries, total = xpubauth_scope.parse_scope(
            "m/84h/0h/{0-9}h;m/86h/0h/{0-2}h;m/48h/0h/{0-4}h/2h", *MAIN
        )
        self.assertEqual(total, 10 + 3 + 5)

    def test_bip138_like_scope_count(self):
        # roughly the BIP-0138 common discovery space for one network
        scope = ";".join([
            "m/44h/0h/{0-9}h",
            "m/49h/0h/{0-9}h",
            "m/84h/0h/{0-9}h",
            "m/86h/0h/{0-9}h",
            "m/87h/0h/{0-9}h",
            "m/48h/0h/{0-9}h/1h",
            "m/48h/0h/{0-9}h/2h",
        ])
        entries, total = xpubauth_scope.parse_scope(scope, *MAIN)
        self.assertEqual(total, 70)
        self.assertLessEqual(total, xpubauth_scope.MAX_TOTAL_XPUBS)

    def test_hardened_notation_is_equivalent(self):
        a, _ = xpubauth_scope.parse_scope("m/84h/0h/{0-9}h", *MAIN)
        b, _ = xpubauth_scope.parse_scope("m/84'/0'/{0-9}'", *MAIN)
        self.assertEqual(a[0].components, b[0].components)
        self.assertEqual(a[0].format(), b[0].format())

    def test_zero_width_range_is_valid(self):
        entries, total = xpubauth_scope.parse_scope("m/84h/0h/{0-0}h", *MAIN)
        self.assertEqual(total, 1)

    def test_reversed_range_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{9-0}h", *MAIN)

    def test_negative_range_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{-1-5}h", *MAIN)

    def test_value_at_hardened_boundary_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/2147483648", *MAIN)

    def test_huge_decimal_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/123456789012h", *MAIN)

    def test_range_too_wide_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{0-500}h", *MAIN)

    def test_huge_range_is_rejected_before_expansion(self):
        # the canonical "don't even try to expand this" example
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{0-2147483647}h", *MAIN)

    def test_malformed_braces_are_rejected(self):
        for bad in ["m/84h/0h/{0-9", "m/84h/0h/0-9}h", "m/84h/0h/{0-9]h"]:
            with self.assertRaises(xpubauth_scope.ScopeError):
                xpubauth_scope.parse_scope(bad, *MAIN)

    def test_missing_boundary_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{-9}h", *MAIN)

    def test_extra_boundary_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{0-5-9}h", *MAIN)

    def test_unexpected_characters_are_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{0-9x}h", *MAIN)
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/5x", *MAIN)

    def test_too_many_path_components_is_rejected(self):
        deep = "m/" + "/".join(["0h"] * (xpubauth_scope.MAX_PATH_DEPTH + 1))
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope(deep, *MAIN)

    def test_too_many_scope_entries_is_rejected(self):
        entries = ";".join(
            "m/84h/0h/%dh" % i for i in range(xpubauth_scope.MAX_ENTRIES + 1)
        )
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope(entries, *MAIN)

    def test_total_expansion_over_budget_is_rejected(self):
        scope = ";".join([
            "m/84h/0h/{0-99}h",
            "m/86h/0h/{0-99}h",
            "m/49h/0h/{0-99}h",
        ])
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope(scope, *MAIN)

    def test_wildcards_are_not_a_grammar_construct(self):
        for bad in ["*", "m/*", "m/84h/0h/*"]:
            with self.assertRaises(xpubauth_scope.ScopeError):
                xpubauth_scope.parse_scope(bad, *MAIN)

    def test_multiple_ranges_in_one_entry_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/{0-1}h/{0-9}h", *MAIN)

    def test_empty_scope_is_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("", *MAIN)
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("   ;  ", *MAIN)

    def test_oversized_scope_string_is_rejected(self):
        huge = "m/84h/0h/0h;" * (xpubauth_scope.MAX_SCOPE_LEN // 10)
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope(huge, *MAIN)


class ScopeOverlapTest(TestCase):
    def test_duplicate_exact_paths_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/5h;m/84h/0h/5h", *MAIN)

    def test_exact_path_inside_range_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/{0-9}h;m/84h/0h/5h", *MAIN)

    def test_overlapping_ranges_rejected(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope(
                "m/84h/0h/{0-9}h;m/84h/0h/{5-15}h", *MAIN
            )

    def test_non_overlapping_ranges_allowed(self):
        entries, total = xpubauth_scope.parse_scope(
            "m/84h/0h/{0-9}h;m/84h/0h/{10-15}h", *MAIN
        )
        self.assertEqual(total, 16)

    def test_different_depth_entries_never_overlap(self):
        entries, total = xpubauth_scope.parse_scope(
            "m/84h/0h/0h;m/84h/0h/0h/1h", *MAIN
        )
        self.assertEqual(total, 2)


class ScopeNetworkValidationTest(TestCase):
    def test_mainnet_standard_path_accepted(self):
        xpubauth_scope.parse_scope("m/84h/0h/{0-9}h", *MAIN)

    def test_testnet_style_path_rejected_on_mainnet(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/1h/0h", *MAIN)

    def test_mainnet_style_path_rejected_on_testnet(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope("m/84h/0h/0h", *TEST)

    def test_testnet_style_path_accepted_on_testnet(self):
        xpubauth_scope.parse_scope("m/84h/1h/{0-9}h", *TEST)

    def test_mixed_network_scope_rejected_as_whole(self):
        with self.assertRaises(xpubauth_scope.ScopeError):
            xpubauth_scope.parse_scope(
                "m/84h/0h/{0-9}h;m/84h/1h/{0-9}h", *MAIN
            )

    def test_non_standard_purpose_has_no_coin_policy(self):
        # an unusual/custom path is not a recognized BIP44-style form,
        # so no coin-type policy is enforced on it either way
        xpubauth_scope.parse_scope("m/123456h/0h/0h", *MAIN)
        xpubauth_scope.parse_scope("m/123456h/1h/0h", *MAIN)

    def test_non_hardened_purpose_has_no_coin_policy(self):
        xpubauth_scope.parse_scope("m/84/1h/0h", *MAIN)


class StandardPathCoinTypeMismatchTest(TestCase):
    """standard_path_coin_type_mismatch() applies the same rule
    _validate_standard_coin_type() applies to an xpubauth scope entry, but
    to a single already-parsed path - used to guard plain, non-scoped
    `xpub <path>` requests."""

    def test_matching_mainnet_path_is_not_a_mismatch(self):
        path = bip32.parse_path("m/84h/0h/0h")
        self.assertFalse(xpubauth_scope.standard_path_coin_type_mismatch(path, 0))

    def test_testnet_style_path_mismatches_on_mainnet(self):
        path = bip32.parse_path("m/84h/1h/0h")
        self.assertTrue(xpubauth_scope.standard_path_coin_type_mismatch(path, 0))

    def test_mainnet_style_path_mismatches_on_testnet(self):
        path = bip32.parse_path("m/84h/0h/0h")
        self.assertTrue(xpubauth_scope.standard_path_coin_type_mismatch(path, 1))

    def test_matching_testnet_path_is_not_a_mismatch(self):
        path = bip32.parse_path("m/84h/1h/0h")
        self.assertFalse(xpubauth_scope.standard_path_coin_type_mismatch(path, 1))

    def test_every_standard_purpose_is_covered(self):
        for purpose in xpubauth_scope.STANDARD_PURPOSES:
            path = bip32.parse_path("m/%dh/1h/0h" % purpose)
            self.assertTrue(
                xpubauth_scope.standard_path_coin_type_mismatch(path, 0),
                "purpose %dh not enforced" % purpose,
            )

    def test_non_standard_purpose_is_never_a_mismatch(self):
        path = bip32.parse_path("m/123456h/1h/0h")
        self.assertFalse(xpubauth_scope.standard_path_coin_type_mismatch(path, 0))

    def test_non_hardened_purpose_is_never_a_mismatch(self):
        path = bip32.parse_path("m/84/1h/0h")
        self.assertFalse(xpubauth_scope.standard_path_coin_type_mismatch(path, 0))

    def test_path_shorter_than_two_components_is_never_a_mismatch(self):
        path = bip32.parse_path("m/84h")
        self.assertFalse(xpubauth_scope.standard_path_coin_type_mismatch(path, 0))

    def test_liquid_coin_type_is_covered(self):
        path = bip32.parse_path("m/84h/1776h/0h")
        self.assertTrue(xpubauth_scope.standard_path_coin_type_mismatch(path, 0))
        self.assertFalse(xpubauth_scope.standard_path_coin_type_mismatch(path, 1776))


class NetworkHintForPathTest(TestCase):
    def test_mainnet_coin_type_names_mainnet(self):
        self.assertEqual(
            xpubauth_scope.network_hint_for_path(bip32.parse_path("m/84h/0h/0h")),
            "Mainnet",
        )

    def test_liquid_coin_type_names_liquid(self):
        self.assertEqual(
            xpubauth_scope.network_hint_for_path(bip32.parse_path("m/84h/1776h/0h")),
            "Liquid",
        )

    def test_testnet_coin_type_names_the_candidates(self):
        hint = xpubauth_scope.network_hint_for_path(bip32.parse_path("m/84h/1h/0h"))
        self.assertIn("Testnet", hint)
        self.assertIn("Signet", hint)
        self.assertIn("Regtest", hint)

    def test_unknown_coin_type_has_no_hint(self):
        self.assertIsNone(
            xpubauth_scope.network_hint_for_path(bip32.parse_path("m/84h/999h/0h"))
        )

    def test_short_or_soft_path_has_no_hint(self):
        self.assertIsNone(
            xpubauth_scope.network_hint_for_path(bip32.parse_path("m/84h"))
        )
        self.assertIsNone(
            xpubauth_scope.network_hint_for_path(bip32.parse_path("m/84h/1/0h"))
        )


class ScopeMatchingTest(TestCase):
    def _entry(self, scope_str, network=MAIN):
        entries, _ = xpubauth_scope.parse_scope(scope_str, *network)
        return entries[0]

    def test_match_boundaries_of_a_range(self):
        entry = self._entry("m/84h/0h/{0-9}h")
        for value in (0, 5, 9):
            path = bip32.parse_path("m/84h/0h/%dh" % value)
            self.assertIsNotNone(entry.match(path))
        for value in (10,):
            path = bip32.parse_path("m/84h/0h/%dh" % value)
            self.assertIsNone(entry.match(path))

    def test_match_uses_normalized_hardened_notation(self):
        entry = self._entry("m/84h/0h/{0-9}h")
        path = bip32.parse_path("m/84'/0'/3'")
        self.assertIsNotNone(entry.match(path))

    def test_out_of_scope_paths_do_not_match(self):
        entry = self._entry("m/84h/0h/{0-9}h")
        for bad in ["m/84h/0h/10h", "m/84h/1h/0h", "m/85h/0h/0h", "m", "m/0h"]:
            try:
                path = bip32.parse_path(bad)
            except Exception:
                continue
            self.assertIsNone(entry.match(path))

    def test_prefix_is_not_authorized(self):
        entry = self._entry("m/84h/0h/1h")
        path = bip32.parse_path("m/84h/0h/1h/999h")
        self.assertIsNone(entry.match(path))


class AuthorizationBudgetTest(TestCase):
    def test_consumable_permission_is_single_use(self):
        entries, _ = xpubauth_scope.parse_scope("m/84h/0h/0h", *MAIN)
        auth = xpubauth_scope.Authorization(entries, "main")
        path = bip32.parse_path("m/84h/0h/0h")
        self.assertTrue(auth.try_consume("main", path))
        self.assertFalse(auth.try_consume("main", path))

    def test_each_value_in_range_consumable_once(self):
        entries, _ = xpubauth_scope.parse_scope("m/84h/0h/{0-2}h", *MAIN)
        auth = xpubauth_scope.Authorization(entries, "main")
        for value in (0, 1, 2):
            path = bip32.parse_path("m/84h/0h/%dh" % value)
            self.assertTrue(auth.try_consume("main", path))
        for value in (0, 1, 2):
            path = bip32.parse_path("m/84h/0h/%dh" % value)
            self.assertFalse(auth.try_consume("main", path))

    def test_remaining_reaches_zero_after_full_consumption(self):
        entries, total = xpubauth_scope.parse_scope("m/84h/0h/{0-2}h", *MAIN)
        auth = xpubauth_scope.Authorization(entries, "main")
        self.assertEqual(auth.remaining, total)
        for value in (0, 1, 2):
            auth.try_consume("main", bip32.parse_path("m/84h/0h/%dh" % value))
        self.assertEqual(auth.remaining, 0)

    def test_network_mismatch_never_consumes(self):
        entries, _ = xpubauth_scope.parse_scope("m/84h/0h/0h", *MAIN)
        auth = xpubauth_scope.Authorization(entries, "main")
        path = bip32.parse_path("m/84h/0h/0h")
        self.assertFalse(auth.try_consume("test", path))
        self.assertEqual(auth.remaining, 1)
        # still consumable on the correct network afterwards
        self.assertTrue(auth.try_consume("main", path))

    def test_unrelated_path_never_consumes(self):
        entries, _ = xpubauth_scope.parse_scope("m/84h/0h/{0-9}h", *MAIN)
        auth = xpubauth_scope.Authorization(entries, "main")
        path = bip32.parse_path("m/85h/0h/0h")
        self.assertFalse(auth.try_consume("main", path))
        self.assertEqual(auth.remaining, 10)
