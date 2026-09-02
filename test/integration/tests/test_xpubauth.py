from unittest import TestCase
from util.controller import sim


class XpubAuthIntegrationTest(TestCase):
    def test_begin_end_and_in_scope_requests(self):
        # one confirmation for the scope...
        res = sim.query(b"xpubauth begin m/84h/1h/{0-2}h", [True])
        self.assertEqual(res, b"success")

        # ...then in-scope requests need no further confirmation at all.
        # sim.query() is called here with no "commands" to send to the
        # GUI socket - if the device were to show a prompt, nothing
        # would confirm it and the USB read below would time out empty,
        # so a real tpub coming back proves no prompt was shown.
        res = sim.query(b"xpub m/84h/1h/0h")
        self.assertTrue(res.startswith(b"tpub"), res)
        res = sim.query(b"xpub m/84h/1h/2h")
        self.assertTrue(res.startswith(b"tpub"), res)

        # a path outside the approved scope still requires confirmation
        res = sim.query(b"xpub m/84h/1h/9h", [True])
        self.assertTrue(res.startswith(b"tpub"), res)

        # explicit end
        res = sim.query(b"xpubauth end")
        self.assertEqual(res, b"success")

        # the same in-scope path now requires confirmation again -
        # without it, the request would time out instead of succeeding
        res = sim.query(b"xpub m/84h/1h/0h", [True])
        self.assertTrue(res.startswith(b"tpub"), res)

    def test_exact_four_paths(self):
        scope = b"m/84h/1h/0h;m/86h/1h/0h;m/48h/1h/0h/2h;m/48h/1h/1h/2h"
        res = sim.query(b"xpubauth begin " + scope, [True])
        self.assertEqual(res, b"success")

        for path in [b"m/84h/1h/0h", b"m/86h/1h/0h", b"m/48h/1h/0h/2h", b"m/48h/1h/1h/2h"]:
            res = sim.query(b"xpub " + path)
            self.assertTrue(res.startswith(b"tpub"), res)

        # a fifth, unrelated path is not covered and needs confirmation
        res = sim.query(b"xpub m/49h/1h/0h", [True])
        self.assertTrue(res.startswith(b"tpub"), res)

        sim.query(b"xpubauth end")

    def test_repeated_request_for_consumed_path_reprompts(self):
        res = sim.query(b"xpubauth begin m/84h/1h/0h", [True])
        self.assertEqual(res, b"success")

        # first silent use consumes the single-path authorization
        res = sim.query(b"xpub m/84h/1h/0h")
        self.assertTrue(res.startswith(b"tpub"), res)

        # authorization is fully consumed and self-clears - a repeat
        # request needs confirmation again
        res = sim.query(b"xpub m/84h/1h/0h", [True])
        self.assertTrue(res.startswith(b"tpub"), res)

    def test_cancelled_begin_grants_nothing(self):
        res = sim.query(b"xpubauth begin m/84h/1h/{0-2}h", [False])
        self.assertEqual(res, b"error: User cancelled")

        # nothing was authorized - a matching path still prompts
        res = sim.query(b"xpub m/84h/1h/0h", [True])
        self.assertTrue(res.startswith(b"tpub"), res)

    def test_invalid_scope_is_rejected_without_prompting(self):
        res = sim.query(b"xpubauth begin m/84h/0h/*")
        self.assertTrue(res.startswith(b"error:"), res)

    def test_cancelled_replacement_begin_revokes_prior_authorization(self):
        # an authorization is active...
        res = sim.query(b"xpubauth begin m/84h/1h/{0-2}h", [True])
        self.assertEqual(res, b"success")

        # ...a new begin arrives and the user cancels it
        res = sim.query(b"xpubauth begin m/86h/1h/{0-2}h", [False])
        self.assertEqual(res, b"error: User cancelled")

        # fail closed: the prior authorization is gone too, so a
        # formerly in-scope path now requires normal confirmation again
        res = sim.query(b"xpub m/84h/1h/0h", [True])
        self.assertTrue(res.startswith(b"tpub"), res)

    def test_bip138_like_discovery_flow(self):
        scope = b";".join([
            b"m/44h/1h/{0-9}h", b"m/49h/1h/{0-9}h", b"m/84h/1h/{0-9}h",
            b"m/86h/1h/{0-9}h", b"m/87h/1h/{0-9}h",
            b"m/48h/1h/{0-9}h/1h", b"m/48h/1h/{0-9}h/2h",
        ])
        res = sim.query(b"xpubauth begin " + scope, [True])
        self.assertEqual(res, b"success")

        # sequential lookups, no further prompts, stopping early
        for path in [b"m/84h/1h/0h", b"m/84h/1h/1h", b"m/49h/1h/0h"]:
            res = sim.query(b"xpub " + path)
            self.assertTrue(res.startswith(b"tpub"), res)

        sim.query(b"xpubauth end")

        res = sim.query(b"xpub m/84h/1h/2h", [True])
        self.assertTrue(res.startswith(b"tpub"), res)
