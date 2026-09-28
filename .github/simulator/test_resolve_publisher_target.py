#!/usr/bin/env python3
"""Tests for resolving trusted publisher tooling revisions."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_publisher_target import resolve_simulator_commit, should_publish

SIMULATOR_REPOSITORY = "cryptoadvance/specter-diy-web-simulator"
SIMULATOR_SHA = "b" * 40


class ResolvePublisherTargetTests(unittest.TestCase):
    def write_target(self, directory, data):
        path = Path(directory) / "target.json"
        path.write_text(data)
        return path

    def test_success_uses_the_trusted_build_target_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_target(
                directory,
                '{"simulator_repository": "cryptoadvance/specter-diy-web-simulator", '
                f'"simulator_commit": "{SIMULATOR_SHA}"}}',
            )
            result = resolve_simulator_commit(
                path, "success", SIMULATOR_REPOSITORY, SIMULATOR_SHA)
        self.assertEqual(result, SIMULATOR_SHA)

    def test_success_without_a_valid_target_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            with self.assertRaisesRegex(ValueError, "Successful build has no valid target"):
                resolve_simulator_commit(path, "success", SIMULATOR_REPOSITORY, SIMULATOR_SHA)

    def test_failed_run_without_target_uses_the_trusted_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            result = resolve_simulator_commit(
                path, "failure", SIMULATOR_REPOSITORY, SIMULATOR_SHA)
        self.assertEqual(result, SIMULATOR_SHA)

    def test_target_from_another_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_target(
                directory,
                '{"simulator_repository": "attacker/example", '
                f'"simulator_commit": "{SIMULATOR_SHA}"}}',
            )
            with self.assertRaisesRegex(ValueError, "unexpected simulator repository"):
                resolve_simulator_commit(path, "success", SIMULATOR_REPOSITORY, SIMULATOR_SHA)

    def test_target_commit_different_from_trusted_pin_is_rejected(self):
        other_sha = "c" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_target(
                directory,
                '{"simulator_repository": "cryptoadvance/specter-diy-web-simulator", '
                f'"simulator_commit": "{other_sha}"}}',
            )
            with self.assertRaisesRegex(ValueError, "does not match trusted"):
                resolve_simulator_commit(path, "success", SIMULATOR_REPOSITORY, SIMULATOR_SHA)

    def test_latest_default_branch_push_is_allowed(self):
        self.assertTrue(should_publish(
            "push", "master", SIMULATOR_SHA, "master", "owner/repo", "token",
            lambda repository, branch, token: SIMULATOR_SHA,
        ))

    def test_stale_default_branch_push_is_skipped(self):
        self.assertFalse(should_publish(
            "push", "master", SIMULATOR_SHA, "master", "owner/repo", "token",
            lambda repository, branch, token: "c" * 40,
        ))

    def test_non_default_branch_push_is_skipped_without_api_request(self):
        self.assertFalse(should_publish(
            "push", "main", SIMULATOR_SHA, "master", "owner/repo", "token",
            lambda *_: self.fail("non-default branch must not be queried"),
        ))

    def test_pr_publisher_does_not_need_default_branch_check(self):
        self.assertTrue(should_publish(
            "pull_request", "feature", SIMULATOR_SHA, "master", "owner/repo", "token",
            lambda *_: self.fail("PR runs use PR-specific stale checks"),
        ))

    def test_invalid_trusted_pin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "full 40-character SHA"):
            resolve_simulator_commit(Path("missing.json"), "failure", SIMULATOR_REPOSITORY, "main")


if __name__ == "__main__":
    unittest.main()
