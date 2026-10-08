#!/usr/bin/env python3
"""Unit tests for preview dispatch authorization, comments, and timeout contracts."""
from pathlib import Path
from unittest.mock import patch
import json
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch_browser_preview as dispatcher


ROOT = Path(__file__).resolve().parents[2]


class BrowserPreviewDispatcherTests(unittest.TestCase):
    def test_fork_pr_dispatches_without_approval_label(self):
        workflow = (ROOT / ".github/workflows/browser-preview.yml").read_text()
        source = (ROOT / ".github/scripts/dispatch_browser_preview.py").read_text()
        self.assertIn("closed", workflow)
        self.assertIn("github.event.action == 'closed' && 'delete'", workflow)
        self.assertNotIn("preview-approved", workflow + source)
        self.assertNotIn("PR_LABELS_JSON", workflow + source)

        sha = "a" * 40
        request_id = f"specter-pr-12-{sha}-123-1"
        status = {
            "request_id": request_id,
            "source_sha": sha,
            "pr_number": 12,
            "status": "cancelled",
            "run_url": "https://github.com/cryptoadvance/specter-diy-web-simulator/actions/runs/456",
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(status).encode()

        calls = []

        def fake_gh(method, path, token="", data=None):
            calls.append((method, path, token, data))
            if method == "GET" and path == "/repos/cryptoadvance/specter-diy-web-simulator":
                return {"default_branch": "main"}
            return None

        environment = {
            "BASE_REPOSITORY": "cryptoadvance/specter-diy",
            "PR_NUMBER": "12",
            "BASE_SHA": "b" * 40,
            "BASE_REF": "master",
            "HEAD_REPOSITORY": "contributor/specter-diy",
            "HEAD_SHA": sha,
            "HEAD_REF": "feature",
            "SOURCE_UPDATED_AT": "2026-10-02T12:00:00Z",
            "ACTION": "build",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_TOKEN": "workflow-token",
            "WEB_SIMULATOR_DISPATCH_TOKEN": "dispatch-token",
            "WEB_SIMULATOR_REPOSITORY": "cryptoadvance/specter-diy-web-simulator",
        }
        with patch.dict(os.environ, environment), \
                patch.object(dispatcher, "current", return_value=True), \
                patch.object(dispatcher, "gh", side_effect=fake_gh), \
                patch.object(dispatcher, "comment"), \
                patch.object(dispatcher, "urlopen", return_value=Response()):
            dispatcher.main()

        dispatches = [call for call in calls if call[0] == "POST"]
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(dispatches[0][2], "dispatch-token")
        self.assertEqual(dispatches[0][3]["inputs"]["head_repository"], "contributor/specter-diy")
        self.assertEqual(dispatches[0][3]["inputs"]["base_sha"], "b" * 40)
        self.assertEqual(dispatches[0][3]["inputs"]["base_ref"], "master")

    def test_unknown_or_stale_pr_state_never_authorizes_a_comment(self):
        with patch.object(dispatcher, "current", return_value=None), \
                patch.object(dispatcher, "comment") as write_comment:
            self.assertFalse(dispatcher._comment_if_current(
                "cryptoadvance/specter-diy", 12, "build", "a" * 40, "token", "text"))
            write_comment.assert_not_called()
        with patch.object(dispatcher, "current", return_value=False), \
                patch.object(dispatcher, "comment") as write_comment:
            self.assertFalse(dispatcher._comment_if_current(
                "cryptoadvance/specter-diy", 12, "build", "a" * 40, "token", "text"))
            write_comment.assert_not_called()
        with patch.object(dispatcher, "current", return_value=True), \
                patch.object(dispatcher, "comment") as write_comment:
            self.assertTrue(dispatcher._comment_if_current(
                "cryptoadvance/specter-diy", 12, "build", "a" * 40, "token", "text"))
            write_comment.assert_called_once()

    def test_bot_comment_searches_all_api_pages(self):
        first = [{"id": index, "body": "other", "user": {"login": "someone"}}
                 for index in range(100)]
        second = [{"id": 900, "body": "previous " + dispatcher.MARKER,
                   "user": {"login": "github-actions[bot]"}}]
        calls = []

        def fake_gh(method, path, _token, data=None):
            calls.append((method, path, data))
            if method == "GET" and path.endswith("page=1"):
                return first
            if method == "GET" and path.endswith("page=2"):
                return second
            return None

        with patch.object(dispatcher, "gh", side_effect=fake_gh):
            dispatcher.comment("cryptoadvance/specter-diy", 12, "token", "updated")
        self.assertIn(("GET", "/repos/cryptoadvance/specter-diy/issues/12/comments?per_page=100&page=1", None), calls)
        self.assertIn(("GET", "/repos/cryptoadvance/specter-diy/issues/12/comments?per_page=100&page=2", None), calls)
        patch_calls = [call for call in calls if call[0] == "PATCH"]
        self.assertEqual(len(patch_calls), 1)
        self.assertEqual(patch_calls[0][1], "/repos/cryptoadvance/specter-diy/issues/comments/900")

    def test_timeout_constants_fit_remote_chain_and_caller_workflow(self):
        self.assertEqual(dispatcher.REMOTE_VALIDATE_TIMEOUT_MINUTES, 5)
        self.assertEqual(dispatcher.REMOTE_BUILD_TIMEOUT_MINUTES, 180)
        self.assertEqual(dispatcher.REMOTE_FINALIZE_TIMEOUT_MINUTES, 10)
        self.assertGreater(dispatcher.POLL_TIMEOUT_MINUTES,
                            dispatcher.REMOTE_VALIDATE_TIMEOUT_MINUTES +
                            dispatcher.REMOTE_BUILD_TIMEOUT_MINUTES +
                            dispatcher.REMOTE_FINALIZE_TIMEOUT_MINUTES)
        self.assertLess(dispatcher.POLL_TIMEOUT_MINUTES,
                        dispatcher.CALLER_WORKFLOW_TIMEOUT_MINUTES)
        workflow = (ROOT / ".github/workflows/browser-preview.yml").read_text()
        self.assertIn(f"timeout-minutes: {dispatcher.CALLER_WORKFLOW_TIMEOUT_MINUTES}", workflow)

    def test_close_cleanup_remains_wired_without_label_trigger(self):
        workflow = (ROOT / ".github/workflows/browser-preview.yml").read_text()
        self.assertIn("closed", workflow)
        self.assertNotIn("labeled", workflow)
        self.assertNotIn("PR_LABELS_JSON", workflow)
        self.assertIn("github.event.action == 'closed' && 'delete'", workflow)


if __name__ == "__main__":
    unittest.main()
