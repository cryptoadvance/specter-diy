#!/usr/bin/env python3
"""Tests for exact PR validation and short-lived preview dispatch."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import json
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch_browser_preview as dispatcher


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
BASE_SHA = "b" * 40
UPDATED = "2026-10-02T12:00:00Z"


def environment():
    return {
        "BASE_REPOSITORY": "cryptoadvance/specter-diy",
        "PR_NUMBER": "12",
        "BASE_SHA": BASE_SHA,
        "BASE_REF": "master",
        "HEAD_REPOSITORY": "contributor/specter-diy",
        "HEAD_SHA": SHA,
        "HEAD_REF": "feature",
        "SOURCE_UPDATED_AT": UPDATED,
        "ACTION": "build",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_TOKEN": "workflow-token",
        "WEB_SIMULATOR_DISPATCH_TOKEN": "dispatch-token",
        "WEB_SIMULATOR_REPOSITORY": "cryptoadvance/specter-diy-web-simulator",
    }


def live_pr(**changes):
    result = {
        "number": 12,
        "state": "open",
        "updated_at": UPDATED,
        "base": {"repo": {"full_name": "cryptoadvance/specter-diy"},
                 "sha": BASE_SHA, "ref": "master"},
        "head": {"repo": {"full_name": "contributor/specter-diy"},
                 "sha": SHA, "ref": "feature"},
    }
    for key, value in changes.items():
        result[key] = value
    return result


class BrowserPreviewDispatcherTests(unittest.TestCase):
    def test_dispatches_exact_fork_pr_metadata_and_returns_without_polling(self):
        calls = []

        def fake_gh(method, path, token="", data=None):
            calls.append((method, path, token, data))
            if path == "/repos/cryptoadvance/specter-diy/pulls/12":
                return live_pr()
            if path == "/repos/cryptoadvance/specter-diy-web-simulator":
                return {"default_branch": "main"}
            return None

        with patch.dict(os.environ, environment()), patch.object(dispatcher, "gh", side_effect=fake_gh):
            dispatcher.main()

        posts = [call for call in calls if call[0] == "POST"]
        self.assertEqual(len(posts), 1)
        method, path, token, body = posts[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/repos/cryptoadvance/specter-diy-web-simulator/actions/workflows/preview.yml/dispatches")
        self.assertEqual(token, "dispatch-token")
        self.assertEqual(body["ref"], "main")
        self.assertEqual(body["inputs"], {
            "request_id": f"specter-pr-12-{SHA}-123-2",
            "action": "build",
            "base_repository": "cryptoadvance/specter-diy",
            "base_sha": BASE_SHA,
            "base_ref": "master",
            "pr_number": "12",
            "head_repository": "contributor/specter-diy",
            "head_sha": SHA,
            "head_ref": "feature",
            "source_updated_at": UPDATED,
        })
        self.assertEqual([call[1] for call in calls].count("/repos/cryptoadvance/specter-diy/pulls/12"), 1)

    def test_stale_live_pr_is_not_dispatched(self):
        for pr in (live_pr(head={"repo": {"full_name": "other/specter-diy"},
                             "sha": SHA, "ref": "feature"}),
                   live_pr(head={"repo": {"full_name": "contributor/specter-diy"},
                                 "sha": "c" * 40, "ref": "feature"}),
                   live_pr(base={"repo": {"full_name": "cryptoadvance/specter-diy"},
                                 "sha": "d" * 40, "ref": "master"}),
                   live_pr(state="closed")):
            with self.subTest(pr=pr), patch.dict(os.environ, environment()), \
                    patch.object(dispatcher, "gh", side_effect=[pr]) as api:
                dispatcher.main()
                api.assert_called_once()

    def test_request_metadata_requires_full_exact_identity(self):
        for key, value in (("PR_NUMBER", "0"), ("HEAD_SHA", "A" * 40),
                           ("BASE_SHA", "short"), ("BASE_REF", "../main"),
                           ("HEAD_REF", "feature\\branch"),
                           ("SOURCE_UPDATED_AT", "2026-10-02T12:00:00"),
                           ("GITHUB_RUN_ATTEMPT", "0"),
                           ("WEB_SIMULATOR_REPOSITORY", "attacker/example")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                dispatcher.request_from_environment({**environment(), key: value})

    def test_renamed_fork_is_allowed_when_it_matches_live_pr(self):
        env = {**environment(), "HEAD_REPOSITORY": "contributor/renamed-specter-fork"}
        pr = live_pr(head={"repo": {"full_name": env["HEAD_REPOSITORY"]},
                           "sha": SHA, "ref": "feature"})
        with patch.dict(os.environ, env), patch.object(dispatcher, "gh",
                side_effect=[pr, {"default_branch": "main"}, None]) as api:
            dispatcher.main()
        self.assertEqual(api.call_args_list[-1].args[0], "POST")

    def test_default_pairing_uses_the_base_repository_owner(self):
        env = environment()
        env.pop("WEB_SIMULATOR_REPOSITORY")
        with patch.dict(os.environ, env), patch.object(dispatcher, "gh") as api:
            api.side_effect = [live_pr(), {"default_branch": "main"}, None]
            dispatcher.main()
        self.assertEqual(api.call_args_list[-1].args[1],
                         "/repos/cryptoadvance/specter-diy-web-simulator/actions/workflows/preview.yml/dispatches")

    def test_close_dispatch_requires_live_closed_pr(self):
        env = {**environment(), "ACTION": "delete", "HEAD_REPOSITORY": "",
               "HEAD_REF": ""}
        request = dispatcher.request_from_environment(env)
        self.assertFalse(dispatcher.current(request, "token", lambda *_: live_pr()))
        closed = live_pr(state="closed", head={"repo": None, "sha": SHA, "ref": "feature"})
        self.assertTrue(dispatcher.current(request, "token", lambda *_: closed))

    def test_edit_events_do_not_start_builds_and_closed_event_dispatches_cleanup(self):
        workflow = (ROOT / ".github/workflows/browser-preview.yml").read_text(encoding="utf-8")
        types = next(line for line in workflow.splitlines() if "types:" in line)
        self.assertNotIn("edited", types)
        self.assertIn("closed", types)
        self.assertIn("github.event.action == 'closed' && 'delete'", workflow)

    def test_http_error_does_not_expose_response_body(self):
        error = HTTPError("https://api.github.com/private", 403, "denied", {},
                          BytesIO(b"sensitive response content"))
        with patch.object(dispatcher, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403") as raised:
                dispatcher.gh("POST", "/repos/example/repo/dispatches", "token", {})
        self.assertNotIn("sensitive response content", str(raised.exception))

    def test_workflow_is_short_trusted_and_has_no_polling_or_pr_comment_write(self):
        workflow = (ROOT / ".github/workflows/browser-preview.yml").read_text(encoding="utf-8")
        source = (ROOT / ".github/scripts/dispatch_browser_preview.py").read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 10", workflow)
        self.assertIn("pull-requests: read", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("github.event.pull_request.head", workflow.split("run:", 1)[-1])
        self.assertNotIn("sleep(", source)
        self.assertNotIn("status/pr/", source)
        self.assertNotIn("comments", source)
        self.assertNotIn("poll", source.lower())
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", workflow)


if __name__ == "__main__":
    unittest.main()
