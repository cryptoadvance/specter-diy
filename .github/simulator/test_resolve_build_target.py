#!/usr/bin/env python3
"""Test exact source resolution and fixed simulator-tooling inputs."""
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
            "TARGET_SIMULATOR_COMMIT": SIMULATOR_SHA,
        }

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

    def test_manual_dispatch_resolves_fork_source_and_keeps_trusted_tooling(self):
        env = self.env()
        env["TARGET_SHA"] = SHA[:8]
        target = resolve(env, lambda repository, number, token: self.pr())
        self.assertEqual(target["repository"], "contributor/specter-diy")
        self.assertEqual(target["commit"], SHA)
        self.assertEqual(target["simulator_repository"], "cryptoadvance/specter-diy-web-simulator")
        self.assertEqual(target["simulator_commit"], SIMULATOR_SHA)

    def test_manual_dispatch_rejects_stale_or_untrusted_targets(self):
        pr = self.pr()
        pr["head"]["sha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "currently points to"):
            resolve(self.env(), lambda repository, number, token: pr)
        env = self.env()
        env["GITHUB_REF"] = "refs/heads/feature"
        with self.assertRaisesRegex(ValueError, "default branch"):
            resolve(env, lambda repository, number, token: self.pr())
        pr = self.pr()
        pr["base"]["repo"]["full_name"] = "attacker/specter-diy"
        with self.assertRaisesRegex(ValueError, "another repository or branch"):
            resolve(self.env(), lambda repository, number, token: pr)

    def test_pr_and_push_use_exact_source_and_configured_simulator_commit(self):
        env = self.env()
        env.update({"TARGET_EVENT": "pull_request", "TARGET_SHA": SHA,
                    "TARGET_REPOSITORY": "contributor/specter-diy", "TARGET_BRANCH": "feature"})
        target = resolve(env)
        self.assertEqual((target["commit"], target["repository"]), (SHA, "contributor/specter-diy"))
        self.assertEqual(target["simulator_commit"], SIMULATOR_SHA)
        env.update({"TARGET_EVENT": "push", "TARGET_PR": "0", "TARGET_REPOSITORY": REPOSITORY})
        self.assertEqual(resolve(env)["number"], 0)

    def test_rejects_a_non_commit_simulator_pin(self):
        env = self.env()
        env["TARGET_SIMULATOR_COMMIT"] = "not-a-commit"
        with self.assertRaisesRegex(ValueError, "full simulator commit SHA"):
            resolve(env, lambda repository, number, token: self.pr())


if __name__ == "__main__":
    unittest.main()
