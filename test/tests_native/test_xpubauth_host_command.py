import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase
from io import BytesIO
from binascii import hexlify
import gc

from tests.util import get_keystore, get_xpubs_app, clear_testdir
from apps.xpubs.xpubs import MAX_XPUB_PATH_LEN
from embit import bip32
from embit.liquid.networks import NETWORKS
from gui.screens import Prompt


class XpubAuthHostCommandTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.app = get_xpubs_app(self.keystore, "main")

    def tearDown(self):
        clear_testdir()
        gc.collect()

    # ---- test harness helpers (mirrors test_xpubs_host_command.py) ----

    def _show_screen(self, *responses):
        """Returns (show_screen, seen) where show_screen replies with
        `responses` in order (repeating the last one if exhausted)."""
        seen = []
        responses = list(responses)

        async def show_screen(scr):
            seen.append(scr)
            if len(responses) > 1:
                return responses.pop(0)
            return responses[0]

        return show_screen, seen

    def _run(self, coro):
        try:
            coro.send(None)
        except StopIteration as e:
            return e.value
        raise AssertionError("coroutine did not complete in one step")

    def _xpub(self, path, show_screen):
        stream = BytesIO(b"xpub " + path.encode())
        return self._run(self.app.process_host_command(stream, show_screen))

    def _begin(self, scope, show_screen):
        stream = BytesIO(b"xpubauth begin " + scope.encode())
        return self._run(self.app.process_host_command(stream, show_screen))

    def _end(self, show_screen):
        stream = BytesIO(b"xpubauth end")
        return self._run(self.app.process_host_command(stream, show_screen))

    def _expected_xpub(self, path, network="main"):
        return self.keystore.get_xpub(path).to_base58(NETWORKS[network]["xpub"])

    # ---- begin: happy paths ----

    def test_begin_exact_single_path(self):
        show_screen, seen = self._show_screen(True)
        res = self._begin("m/84h/0h/0h", show_screen)
        self.assertTrue(res)
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0], Prompt)

    def test_begin_shows_network_paths_and_count(self):
        show_screen, seen = self._show_screen(True)
        self._begin("m/84h/0h/{0-9}h", show_screen)
        shown = seen[0]
        message = shown.args[1] if len(shown.args) > 1 else shown.kwargs.get("message")
        self.assertIn(NETWORKS["main"]["name"], message)
        self.assertIn("m/84h/0h/{0-9}h", message)
        self.assertIn("10", message)

    def test_begin_exactly_one_confirmation_for_bip138_scope(self):
        scope = ";".join([
            "m/44h/0h/{0-9}h", "m/49h/0h/{0-9}h", "m/84h/0h/{0-9}h",
            "m/86h/0h/{0-9}h", "m/87h/0h/{0-9}h",
            "m/48h/0h/{0-9}h/1h", "m/48h/0h/{0-9}h/2h",
        ])
        show_screen, seen = self._show_screen(True)
        res = self._begin(scope, show_screen)
        self.assertTrue(res)
        self.assertEqual(len(seen), 1)

    def test_begin_cancel_leaves_no_authorization(self):
        show_screen, seen = self._show_screen(False)
        res = self._begin("m/84h/0h/{0-9}h", show_screen)
        self.assertFalse(res)
        self.assertIsNone(self.app._authorization)

    def test_begin_invalid_scope_leaves_no_authorization(self):
        show_screen, seen = self._show_screen(True)
        with self.assertRaises(Exception):
            self._begin("garbage", show_screen)
        self.assertEqual(seen, [])
        self.assertIsNone(self.app._authorization)

    def test_begin_locked_device_rejected(self):
        from unittest.mock import patch, PropertyMock
        show_screen, seen = self._show_screen(True)
        with patch.object(
            type(self.keystore), "is_locked", new_callable=PropertyMock, return_value=True
        ):
            with self.assertRaises(Exception):
                self._begin("m/84h/0h/0h", show_screen)
        self.assertEqual(seen, [])

    # ---- in-scope requests bypass confirmation ----

    def test_in_scope_first_boundary_no_prompt(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        res = self._xpub("m/84h/0h/0h", show_screen)
        stream, meta = res
        self.assertEqual(stream.read().decode(), self._expected_xpub("m/84h/0h/0h"))
        self.assertEqual(seen, [])

    def test_in_scope_middle_no_prompt(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        res = self._xpub("m/84h/0h/5h", show_screen)
        stream, meta = res
        self.assertEqual(stream.read().decode(), self._expected_xpub("m/84h/0h/5h"))
        self.assertEqual(seen, [])

    def test_in_scope_last_boundary_no_prompt(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        res = self._xpub("m/84h/0h/9h", show_screen)
        stream, meta = res
        self.assertEqual(stream.read().decode(), self._expected_xpub("m/84h/0h/9h"))
        self.assertEqual(seen, [])

    def test_in_scope_matches_hardened_prime_notation(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        res = self._xpub("m/84'/0'/3'", show_screen)
        stream, meta = res
        self.assertEqual(stream.read().decode(), self._expected_xpub("m/84h/0h/3h"))
        self.assertEqual(seen, [])

    def test_exact_four_paths_all_retrievable_without_prompt(self):
        paths = ["m/84h/0h/0h", "m/86h/0h/0h", "m/48h/0h/0h/2h", "m/48h/0h/1h/2h"]
        self._begin(";".join(paths), self._show_screen(True)[0])
        for path in paths:
            show_screen, seen = self._show_screen(True)
            res = self._xpub(path, show_screen)
            stream, meta = res
            self.assertEqual(stream.read().decode(), self._expected_xpub(path))
            self.assertEqual(seen, [])

    def test_fifth_unrelated_path_still_prompts(self):
        paths = ["m/84h/0h/0h", "m/86h/0h/0h", "m/48h/0h/0h/2h", "m/48h/0h/1h/2h"]
        self._begin(";".join(paths), self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        self._xpub("m/49h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0], Prompt)

    # ---- out-of-scope requests fall back to normal confirmation ----

    def test_out_of_range_index_prompts_normally(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/10h", show_screen)
        self.assertEqual(len(seen), 1)

    def test_out_of_scope_does_not_widen_authorization(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        # approve an unrelated path individually
        self._xpub("m/85h/0h/0h", self._show_screen(True)[0])
        # it must not have joined the scope - still prompts every time
        show_screen, seen = self._show_screen(True)
        self._xpub("m/85h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)

    def test_different_account_out_of_scope_prompts(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        for bad in ["m/85h/0h/0h", "m", "m/0h"]:
            show_screen, seen = self._show_screen(True)
            self._xpub(bad, show_screen)
            self.assertEqual(len(seen), 1, "expected a prompt for %r" % bad)

    def test_out_of_scope_wrong_network_path_is_refused_not_prompted(self):
        # a testnet-style path is out of the (mainnet) authorized scope,
        # but it's also a network mismatch on this "main" device - that
        # takes precedence over the usual "just ask" fallback: refused
        # with the dedicated screen, not the normal "Share Xpub?" prompt
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(False)  # tap "OK"
        with self.assertRaises(Exception):
            self._xpub("m/84h/1h/0h", show_screen)
        self.assertEqual(len(seen), 1)
        title = seen[0].args[0] if seen[0].args else seen[0].kwargs.get("title", "")
        self.assertIn("Host tried to get access", title)

    def test_prefix_child_is_not_silently_authorized(self):
        self._begin("m/84h/0h/1h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/1h/999h", show_screen)
        self.assertEqual(len(seen), 1)

    # ---- budget: consumable, single-use permissions ----

    def test_repeated_request_for_consumed_path_reprompts(self):
        self._begin("m/84h/0h/0h", self._show_screen(True)[0])
        show_screen1, seen1 = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen1)
        self.assertEqual(seen1, [])
        # second request for the same, already-consumed path
        show_screen2, seen2 = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen2)
        self.assertEqual(len(seen2), 1)

    def test_authorization_ends_after_full_consumption(self):
        self._begin("m/84h/0h/{0-1}h", self._show_screen(True)[0])
        self._xpub("m/84h/0h/0h", self._show_screen(True)[0])
        self.assertIsNotNone(self.app._authorization)
        self._xpub("m/84h/0h/1h", self._show_screen(True)[0])
        self.assertIsNone(self.app._authorization)

    # ---- explicit end ----

    def test_end_clears_authorization(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        self.assertTrue(self._end(self._show_screen(True)[0]))
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)

    def test_end_without_active_authorization_is_a_noop_success(self):
        self.assertTrue(self._end(self._show_screen(True)[0]))

    # ---- a second begin replaces, never merges ----

    def test_second_begin_replaces_after_fresh_confirmation(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        self._begin("m/86h/0h/{0-9}h", self._show_screen(True)[0])
        # old scope no longer authorized
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)
        # new scope is
        show_screen2, seen2 = self._show_screen(True)
        self._xpub("m/86h/0h/0h", show_screen2)
        self.assertEqual(seen2, [])

    def test_cancelled_second_begin_revokes_first_authorization(self):
        # fail closed: a new begin drops the old authorization up front,
        # so cancelling the new request leaves NO authorization active
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        res = self._begin("m/86h/0h/{0-9}h", self._show_screen(False)[0])
        self.assertFalse(res)
        self.assertIsNone(self.app._authorization)
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)

    def test_invalid_second_begin_revokes_first_authorization(self):
        # a malformed replacement scope also leaves no authorization
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        with self.assertRaises(Exception):
            self._begin("garbage", self._show_screen(True)[0])
        self.assertIsNone(self.app._authorization)

    # ---- host input is bounded before it is decoded/parsed ----

    def test_oversized_xpubauth_request_rejected_before_parsing(self):
        from apps.xpubs import scope as scope_mod
        # a valid-looking prefix followed by megabytes of padding
        huge = "begin m/84h/0h/0h" + ("A" * (scope_mod.MAX_SCOPE_COMMAND_LEN + 4096))
        show_screen, seen = self._show_screen(True)
        stream = BytesIO(b"xpubauth " + huge.encode())
        with self.assertRaises(Exception):
            self._run(self.app.process_host_command(stream, show_screen))
        self.assertEqual(seen, [])
        self.assertIsNone(self.app._authorization)

    def test_oversized_xpub_path_rejected_before_parsing(self):
        show_screen, seen = self._show_screen(True)
        stream = BytesIO(b"xpub m/84h/0h/" + b"1" * (MAX_XPUB_PATH_LEN + 4096))
        with self.assertRaises(Exception):
            self._run(self.app.process_host_command(stream, show_screen))
        self.assertEqual(seen, [])

    def test_malformed_xpub_path_raises_apperror_not_bare_exception(self):
        from app import AppError
        show_screen, seen = self._show_screen(True)
        for bad in (b"m/84h/zz", b"m/84h//0h", b"\xff\xfe not utf-8"):
            stream = BytesIO(b"xpub " + bad)
            with self.assertRaises(AppError):
                self._run(self.app.process_host_command(stream, show_screen))
        self.assertEqual(seen, [])

    # ---- invalidation ----

    def test_lock_clears_authorization(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        self.app.on_lock()
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)

    def test_network_switch_clears_authorization(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        self.app.init(self.keystore, "test", self.app.show_loader, self.app.communicate)
        self.app.init(self.keystore, "main", self.app.show_loader, self.app.communicate)
        # back on the original network, but the authorization is gone -
        # the very same path that used to be in-scope must re-prompt
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)

    def test_network_switch_invalidates_even_when_authorization_object_survives(self):
        # defense in depth: directly exercise the network check inside
        # try_consume, independent of the init()-triggered reset above
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        auth = self.app._authorization
        self.assertIsNotNone(auth)
        auth.network = "test"  # simulate a stale authorization surviving
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)

    def test_reinit_same_network_clears_authorization(self):
        # covers seed reload / passphrase change / storage switch, which
        # all funnel through init()
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        self.app.init(self.keystore, "main", self.app.show_loader, self.app.communicate)
        show_screen, seen = self._show_screen(True)
        self._xpub("m/84h/0h/0h", show_screen)
        self.assertEqual(len(seen), 1)

    # ---- cancellation never leaks xpubs ----

    def test_out_of_scope_cancel_leaks_nothing(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(False)
        res = self._xpub("m/84h/0h/50h", show_screen)
        self.assertFalse(res)

    # ---- fingerprint is unaffected by any of this ----

    def test_fingerprint_stays_non_interactive_with_active_authorization(self):
        self._begin("m/84h/0h/{0-9}h", self._show_screen(True)[0])
        show_screen, seen = self._show_screen(True)
        stream = BytesIO(b"fingerprint")
        res = self._run(self.app.process_host_command(stream, show_screen))
        result_stream, meta = res
        self.assertEqual(result_stream.read().decode(), hexlify(self.keystore.fingerprint).decode())
        self.assertEqual(seen, [])


class Bip138LikeIntegrationTest(TestCase):
    """End-to-end walk-through of the motivating BIP-0138 use case:
    one authorization confirmation, many silent per-path lookups,
    an early stop, then an explicit end."""

    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore()
        self.app = get_xpubs_app(self.keystore, "main")

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def _show_screen(self, response):
        seen = []

        async def show_screen(scr):
            seen.append(scr)
            return response

        return show_screen, seen

    def _run(self, coro):
        try:
            coro.send(None)
        except StopIteration as e:
            return e.value
        raise AssertionError("coroutine did not complete in one step")

    def test_full_bip138_like_flow(self):
        # 1: fingerprint without UI
        show_screen, seen = self._show_screen(True)
        stream = BytesIO(b"fingerprint")
        self._run(self.app.process_host_command(stream, show_screen))
        self.assertEqual(seen, [])

        # 2-5: one authorization confirmation for the discovery scope
        scope = ";".join([
            "m/44h/0h/{0-9}h", "m/49h/0h/{0-9}h", "m/84h/0h/{0-9}h",
            "m/86h/0h/{0-9}h", "m/87h/0h/{0-9}h",
            "m/48h/0h/{0-9}h/1h", "m/48h/0h/{0-9}h/2h",
        ])
        begin_show, begin_seen = self._show_screen(True)
        stream = BytesIO(b"xpubauth begin " + scope.encode())
        self.assertTrue(self._run(self.app.process_host_command(stream, begin_show)))
        self.assertEqual(len(begin_seen), 1)

        # 6-8: sequential per-path lookups with no further prompts
        for path in ["m/84h/0h/0h", "m/84h/0h/1h", "m/49h/0h/0h"]:
            show_screen, seen = self._show_screen(True)
            stream = BytesIO(b"xpub " + path.encode())
            res = self._run(self.app.process_host_command(stream, show_screen))
            result_stream, meta = res
            expected = self.keystore.get_xpub(path).to_base58(NETWORKS["main"]["xpub"])
            self.assertEqual(result_stream.read().decode(), expected)
            self.assertEqual(seen, [])

        # 9: recovery "succeeds" and stops early - the remaining ~67
        # authorized paths are simply never requested

        # 10: host ends the authorization explicitly
        end_show, _ = self._show_screen(True)
        stream = BytesIO(b"xpubauth end")
        self.assertTrue(self._run(self.app.process_host_command(stream, end_show)))

        # 11: a formerly in-scope path requires normal confirmation again
        show_screen, seen = self._show_screen(True)
        stream = BytesIO(b"xpub m/84h/0h/2h")
        self._run(self.app.process_host_command(stream, show_screen))
        self.assertEqual(len(seen), 1)
