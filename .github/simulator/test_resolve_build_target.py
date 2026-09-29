#!/usr/bin/env python3
"""Test source resolution and per-run simulator-main resolution."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_build_target import resolve

SHA = "a" * 40
SIMULATOR_SHA = "b" * 40
REPOSITORY = "cryptoadvance/specter-diy"


class ResolveBuildTargetTests(unittest.TestCase):
    def env(self):
        return {
            "TARGET_EVENT": "workflow_dispatch",
            "TARGET_PR": "19",
            "TARGET_SHA": SHA,
            "TARGET_BRANCH": "master",
            "TARGET_REPOSITORY": REPOSITORY,
            "TARGET_DEFAULT_BRANCH": "master",
            "GITHUB_REF": "refs/heads/master",
            "GITHUB_REPOSITORY": REPOSITORY,
            "GH_TOKEN": "test-token",
            "TARGET_SIMULATOR_REPOSITORY": "cryptoadvance/specter-diy-web-simulator",
        }

    def simulator_main(self, repository, token):
        self.assertEqual(repository, "cryptoadvance/specter-diy-web-simulator")
        self.assertEqual(token, "test-token")
        return SIMULATOR_SHA

    def pr(self):
        return {
            "state": "open",
            "head": {
                "sha": SHA,
                "ref": "feature",
                "repo": {"full_name": "contributor/specter-diy"},
            },
            "base": {
                "ref": "master",
                "repo": {"full_name": REPOSITORY},
            },
        }

    def test_manual_dispatch_resolves_fork_source_and_simulator_main(self):
        env = self.env()
        env["TARGET_SHA"] = SHA[:8]
        target = resolve(env, lambda repository, number, token: self.pr(), self.simulator_main)
        self.assertEqual(target["repository"], "contributor/specter-diy")
        self.assertEqual(target["commit"], SHA)
        self.assertEqual(target["simulator_repository"], "cryptoadvance/specter-diy-web-simulator")
        self.assertEqual(target["simulator_commit"], SIMULATOR_SHA)

    def test_manual_dispatch_rejects_stale_or_untrusted_targets(self):
        pr = self.pr()
        pr["head"]["sha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "currently points to"):
            resolve(self.env(), lambda repository, number, token: pr, self.simulator_main)
        env = self.env()
        env["GITHUB_REF"] = "refs/heads/feature"
        with self.assertRaisesRegex(ValueError, "default branch"):
            resolve(env, lambda repository, number, token: self.pr(), self.simulator_main)
        pr = self.pr()
        pr["base"]["repo"]["full_name"] = "attacker/specter-diy"
        with self.assertRaisesRegex(ValueError, "another repository or branch"):
            resolve(self.env(), lambda repository, number, token: pr, self.simulator_main)

    def test_pr_and_push_use_exact_source_and_current_simulator_main(self):
        env = self.env()
        env.update({"TARGET_EVENT": "workflow_run",
                    "REQUEST_WORKFLOW_PATH": ".github/workflows/pr-build-request.yml@feature",
                    "REQUEST_EVENT": "pull_request", "REQUEST_CONCLUSION": "success",
                    "REQUEST_HEAD_REPOSITORY": "contributor/specter-diy",
                    "REQUEST_HEAD_BRANCH": "feature", "REQUEST_HEAD_SHA": SHA})
        pr = self.pr()
        pr["number"] = 19
        target = resolve(env, fetch_main=self.simulator_main,
                         fetch_head=lambda *_: [pr])
        self.assertEqual((target["commit"], target["repository"]), (SHA, "contributor/specter-diy"))
        self.assertEqual(target["simulator_commit"], SIMULATOR_SHA)
        env.update({"TARGET_EVENT": "push", "TARGET_PR": "0", "TARGET_REPOSITORY": REPOSITORY})
        self.assertEqual(resolve(env, fetch_main=self.simulator_main)["number"], 0)

    def test_request_cannot_choose_another_pr_or_workflow(self):
        env = self.env()
        env.update({"TARGET_EVENT": "workflow_run",
                    "REQUEST_WORKFLOW_PATH": ".github/workflows/pr-build-request.yml@feature",
                    "REQUEST_EVENT": "pull_request", "REQUEST_CONCLUSION": "success",
                    "REQUEST_HEAD_REPOSITORY": "contributor/specter-diy",
                    "REQUEST_HEAD_BRANCH": "feature", "REQUEST_HEAD_SHA": SHA})
        pr = self.pr()
        pr["number"] = 19
        env["REQUEST_WORKFLOW_PATH"] = ".github/workflows/attacker.yml"
        with self.assertRaisesRegex(ValueError, "Unrecognized PR build request"):
            resolve(env, fetch_main=self.simulator_main, fetch_head=lambda *_: [pr])
        env["REQUEST_WORKFLOW_PATH"] = ".github/workflows/pr-build-request.yml"
        env["REQUEST_HEAD_SHA"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "stale"):
            resolve(env, fetch_main=self.simulator_main, fetch_head=lambda *_: [pr])
        env["REQUEST_HEAD_SHA"] = SHA
        env["REQUEST_HEAD_REPOSITORY"] = "attacker/specter-diy"
        with self.assertRaisesRegex(ValueError, "does not identify one open PR"):
            resolve(env, fetch_main=self.simulator_main, fetch_head=lambda *_: [pr])

    def test_each_build_resolves_the_then_current_main_commit(self):
        env = self.env()
        env["TARGET_EVENT"] = "push"
        env["TARGET_PR"] = "0"
        revisions = iter(("b" * 40, "c" * 40))
        fetch_main = lambda repository, token: next(revisions)

        first = resolve(env, fetch_main=fetch_main)
        second = resolve(env, fetch_main=fetch_main)

        self.assertEqual(first["simulator_commit"], "b" * 40)
        self.assertEqual(second["simulator_commit"], "c" * 40)

    def test_rejects_a_non_commit_simulator_main_response(self):
        with self.assertRaisesRegex(ValueError, "full commit SHA"):
            resolve(self.env(), lambda repository, number, token: self.pr(),
                    lambda repository, token: "not-a-commit")


if __name__ == "__main__":
    unittest.main()
