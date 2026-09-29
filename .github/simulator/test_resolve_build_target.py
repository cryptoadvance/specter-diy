#!/usr/bin/env python3
"""Direct PR event and current simulator-main target tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_build_target import resolve

SHA = "a" * 40
PIN = "b" * 40
BASE = "cryptoadvance/specter-diy"
SIMULATOR = "cryptoadvance/specter-diy-web-simulator"


def env(event="pull_request", repository=BASE):
    return {"TARGET_EVENT": event, "TARGET_PR": "19", "TARGET_SHA": SHA,
            "TARGET_BRANCH": "feature", "TARGET_REPOSITORY": repository,
            "TARGET_BASE_REPOSITORY": BASE, "TARGET_BASE_BRANCH": "master",
            "TARGET_DEFAULT_BRANCH": "master", "GITHUB_REF": "refs/pull/19/merge",
            "GITHUB_REPOSITORY": BASE, "TARGET_SIMULATOR_REPOSITORY": SIMULATOR,
            "GH_TOKEN": "test-token"}


class ResolveBuildTargetTests(unittest.TestCase):
    def test_same_repository_pr_uses_event_metadata_without_api(self):
        target = resolve(env(), lambda *_: self.fail("PR event must not call PR API"),
                         lambda *_: PIN)
        self.assertEqual((target["event"], target["number"], target["commit"]),
                         ("pull_request", 19, SHA))
        self.assertEqual(target["base_repository"], BASE)

    def test_fork_pr_uses_exact_head_repository_and_commit(self):
        target = resolve(env(repository="contributor/specter-diy"),
                         lambda *_: self.fail("fork PR event must not call PR API"),
                         lambda *_: PIN)
        self.assertEqual(target["repository"], "contributor/specter-diy")
        self.assertEqual(target["simulator_commit"], PIN)

    def test_pr_cannot_target_another_base(self):
        values = env()
        values["TARGET_BASE_REPOSITORY"] = "attacker/specter-diy"
        with self.assertRaisesRegex(ValueError, "default branch"):
            resolve(values, fetch_main=lambda *_: PIN)
        values = env()
        values["TARGET_BASE_BRANCH"] = "other"
        with self.assertRaisesRegex(ValueError, "default branch"):
            resolve(values, fetch_main=lambda *_: PIN)

    def test_manual_build_rechecks_current_pr_head(self):
        values = env("workflow_dispatch")
        values["GITHUB_REF"] = "refs/heads/master"
        values["TARGET_SHA"] = SHA[:10]
        pr = {"state": "open", "head": {"sha": SHA, "ref": "feature",
              "repo": {"full_name": "contributor/specter-diy"}},
              "base": {"repo": {"full_name": BASE}, "ref": "master"}}
        self.assertEqual(resolve(values, lambda *_: pr, lambda *_: PIN)["commit"], SHA)
        pr["head"]["sha"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "stale"):
            resolve(values, lambda *_: pr, lambda *_: PIN)

    def test_push_uses_default_branch_only(self):
        values = env("push")
        values.update(TARGET_PR="0", GITHUB_REF="refs/heads/master",
                      TARGET_BRANCH="master")
        self.assertEqual(resolve(values, fetch_main=lambda *_: PIN)["number"], 0)
        values["GITHUB_REF"] = "refs/heads/feature"
        with self.assertRaisesRegex(ValueError, "default branch"):
            resolve(values, fetch_main=lambda *_: PIN)

    def test_old_double_workflow_run_event_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Build event"):
            resolve(env("workflow_run"), fetch_main=lambda *_: PIN)

    def test_simulator_main_must_resolve_to_full_sha(self):
        values = env()
        with self.assertRaisesRegex(ValueError, "full commit SHA"):
            resolve(values, fetch_main=lambda *_: "main")


if __name__ == "__main__":
    unittest.main()
