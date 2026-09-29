#!/usr/bin/env python3
"""Regression tests for the firmware-to-simulator workflow contract."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILD = (ROOT / ".github/workflows/build.yml").read_text()
PUBLISH = (ROOT / ".github/workflows/publish-browser.yml").read_text()
REQUEST = (ROOT / ".github/workflows/pr-build-request.yml").read_text()


class WorkflowContractTests(unittest.TestCase):
    def test_reusable_workflows_follow_simulator_main(self):
        self.assertRegex(BUILD, r"browser-simulator\.yml@main\b")
        self.assertRegex(PUBLISH, r"publish-browser\.yml@main\b")
        self.assertNotRegex(BUILD + PUBLISH, r"\.yml@[a-f0-9]{40}\b")

    def test_simulator_revision_is_resolved_per_run_not_configured_as_a_pin(self):
        self.assertIn("simulator_commit: ${{ needs.target.outputs.simulator_commit }}", BUILD)
        self.assertNotIn("TARGET_SIMULATOR_COMMIT:", BUILD)
        self.assertNotIn("TRUSTED_SIMULATOR_COMMIT:", PUBLISH)

    def test_publisher_does_not_request_pull_request_permissions(self):
        root_permissions = re.search(r"(?ms)^permissions:\n(.*?)(?=^jobs:)", PUBLISH)
        self.assertIsNotNone(root_permissions)
        self.assertNotRegex(root_permissions.group(1), r"(?m)^\s*pull-requests:")
        self.assertRegex(root_permissions.group(1), r"(?m)^\s*issues:\s*write\s*$")

    def test_build_has_only_read_pull_request_permission(self):
        root_permissions = re.search(r"(?ms)^permissions:\n(.*?)(?=^jobs:)", BUILD)
        self.assertIsNotNone(root_permissions)
        self.assertRegex(root_permissions.group(1), r"(?m)^\s*pull-requests:\s*read\s*$")

    def test_pr_cannot_replace_the_build_or_publishing_workflows(self):
        self.assertRegex(REQUEST, r"(?m)^  pull_request:")
        self.assertRegex(BUILD, r"(?m)^  workflow_run:")
        self.assertNotRegex(BUILD, r"(?m)^  pull_request:")
        self.assertNotRegex(BUILD, r"(?m)^  pull_request_target:")
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", BUILD)
        self.assertRegex(PUBLISH, r"(?m)^  workflow_run:")


if __name__ == "__main__":
    unittest.main()
