#!/usr/bin/env python3
"""Security and behavior tests for the approval-gated paired preview dispatcher."""
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch_browser_preview as app

ROOT = Path(__file__).resolve().parents[2]
BASE = "cryptoadvance/specter-diy"
SERVICE = "cryptoadvance/specter-diy-web-simulator"
HEAD = "a" * 40
BASE_SHA = "b" * 40
UPDATED = "2026-11-20T10:00:00Z"


def environ(event="workflow_run"):
    return {
        "BASE_REPOSITORY": BASE,
        "PR_NUMBER": "",
        "CI_RUN_ID": "777",
        "EVENT_NAME": event,
        "COMMENT_ID": "",
        "ACTION": "build",
        "GITHUB_ACTOR": "maintainer",
        "GITHUB_RUN_ID": "888",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_TOKEN": "ci-token",
        "WEB_SIMULATOR_DISPATCH_TOKEN": "dispatch-token",
        "WEB_SIMULATOR_REPOSITORY": SERVICE,
    }


def live_pr(state="open", sha=HEAD):
    return {
        "number": 391, "state": state, "updated_at": UPDATED,
        "head": {"repo": {"full_name": "contributor/specter-diy"}, "sha": sha, "ref": "feature"},
        "base": {"repo": {"full_name": BASE}, "sha": BASE_SHA, "ref": "master"},
    }


def ci_run(status="in_progress", conclusion=None, sha=HEAD):
    return {"id": 777, "name": "CI", "event": "pull_request", "status": status,
            "conclusion": conclusion, "head_sha": sha,
            "head_repository": {"full_name": "contributor/specter-diy"},
            "repository": {"full_name": BASE},
            "path": ".github/workflows/test.yml", "pull_requests": []}


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.pr = live_pr()
        self.run = ci_run()
        self.calls = []
        self.permission = "write"

    def gh(self, method, path, token, data=None):
        self.calls.append((method, path, token, data))
        if path == f"/repos/{BASE}/actions/runs/777":
            return self.run
        if path.startswith(f"/repos/{BASE}/pulls?"):
            return [self.pr]
        if path == f"/repos/{BASE}/pulls/391":
            return self.pr
        if path == f"/repos/{SERVICE}":
            return {"default_branch": "main"}
        if path == f"/repos/{BASE}/issues/comments/55":
            return {"issue_url": f"https://api.github.com/repos/{BASE}/issues/391",
                    "body": "/Build", "user": {"login": "maintainer"}}
        if path == f"/repos/{BASE}/collaborators/maintainer/permission":
            return {"permission": self.permission}
        if method == "POST":
            return None
        self.fail(f"Unexpected API: {method} {path}")

    def invoke(self, event="workflow_run", **changes):
        env = {**environ(event), **changes}
        with patch.dict(os.environ, env), patch.object(app, "gh", side_effect=self.gh):
            app.main()

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]

    def test_started_native_pr_ci_dispatches_full_combined_build(self):
        self.invoke()
        self.assertEqual(len(self.posts()), 1)
        method, url, token, body = self.posts()[0]
        self.assertEqual(token, "dispatch-token")
        self.assertEqual(url, f"/repos/{SERVICE}/actions/workflows/preview.yml/dispatches")
        self.assertEqual(body["inputs"]["action"], "build")
        self.assertEqual(body["inputs"]["head_sha"], HEAD)
        self.assertEqual(body["inputs"]["base_sha"], BASE_SHA)
        self.assertEqual(body["inputs"]["pr_number"], "391")

    def test_pending_or_unrelated_ci_cannot_start_build(self):
        for run in (ci_run(status="completed", conclusion="action_required"),
                    ci_run(sha="c" * 40),
                    dict(ci_run(), path=".github/workflows/other.yml"),
                    dict(ci_run(), event="workflow_dispatch")):
            with self.subTest(run=run):
                self.run = run
                self.calls = []
                self.invoke()
                self.assertFalse(self.posts())
        self.run = ci_run()

    def test_stale_commit_cannot_be_built(self):
        self.pr = live_pr(sha="f" * 40)
        self.invoke()
        self.assertFalse(self.posts())

    def test_maintainer_build_command_bypasses_native_gate(self):
        self.invoke("issue_comment", PR_NUMBER="391", COMMENT_ID="55")
        self.assertEqual(len(self.posts()), 1)
        self.assertIn("/preview.yml/dispatches", self.posts()[0][1])

    def test_read_only_cannot_dispatch(self):
        self.permission = "read"
        self.invoke("issue_comment", PR_NUMBER="391", COMMENT_ID="55")
        self.assertFalse(self.posts())

    def test_noncommand_comment_is_rejected(self):
        c = {"issue_url": f"https://api.github.com/repos/{BASE}/issues/391",
             "body": "/build please", "user": {"login": "maintainer"}}
        with patch.object(app, "gh") as api:
            self.assertFalse(app.is_maintainer_command(BASE, 391, c, "token"))
            api.assert_not_called()

    def test_untrusted_pr_requests_only_approval_notice(self):
        self.invoke("pull_request_target", PR_NUMBER="391")
        self.assertEqual(len(self.posts()), 1)
        self.assertIn("/approval.yml/dispatches", self.posts()[0][1])
        self.assertEqual(self.posts()[0][3]["inputs"]["head_sha"], HEAD)

    def test_close_event_requests_cleanup(self):
        self.pr = live_pr(state="closed")
        self.invoke("pull_request_target", PR_NUMBER="391", ACTION="delete")
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.posts()[0][3]["inputs"]["action"], "delete")

    def test_workflow_dispatch_requires_writer(self):
        self.invoke("workflow_dispatch", PR_NUMBER="391")
        self.assertEqual(len(self.posts()), 1)
        self.calls = []
        self.permission = "read"
        self.invoke("workflow_dispatch", PR_NUMBER="391")
        self.assertFalse(self.posts())

    def test_workflow_and_trust_boundary(self):
        workflow = (ROOT / ".github/workflows/pr-build-dispatch.yml").read_text()
        self.assertIn("workflow_run:", workflow)
        self.assertIn("types: [in_progress]", workflow)
        self.assertIn("issue_comment:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("github.event.comment.body == '/build'", workflow)
        self.assertIn("ref: @@{{ github.event.repository.default_branch }}".replace("@@", "$"), workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("pull_request.head.repo.full_name", workflow)
        self.assertNotIn("pull_request_target:\n    types: [edited", workflow)


if __name__ == "__main__":
    unittest.main()
