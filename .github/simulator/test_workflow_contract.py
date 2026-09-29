#!/usr/bin/env python3
"""Static permissions and immutable reusable-workflow contract."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILD = (ROOT / ".github/workflows/build.yml").read_text()
PUBLISH = (ROOT / ".github/workflows/publish-browser.yml").read_text()


class WorkflowContractTests(unittest.TestCase):
    def test_direct_pr_chain_and_no_request_workflow(self):
        self.assertRegex(BUILD, r"(?m)^  pull_request:")
        self.assertNotRegex(BUILD, r"(?m)^  workflow_run:")
        self.assertRegex(PUBLISH, r"(?m)^  workflow_run:")
        self.assertFalse((ROOT / ".github/workflows/pr-build-request.yml").exists())

    def test_build_permissions_are_read_only(self):
        permissions = BUILD.split("permissions:", 1)[1].split("jobs:", 1)[0]
        self.assertEqual(permissions.strip(), "contents: read")
        self.assertNotIn("secrets:", BUILD)

    def test_immutable_workflow_and_tooling_pin_match(self):
        pins = re.findall(r"(?:browser-simulator|publish-browser)\.yml@([A-Za-z0-9_.-]+)",
                          BUILD + PUBLISH)
        self.assertEqual(len(pins), 2)
        self.assertTrue(all(re.fullmatch(r"[a-f0-9]{40}", pin) for pin in pins))
        self.assertEqual(pins[0], pins[1])
        self.assertIn(f"TARGET_SIMULATOR_COMMIT: {pins[0]}", BUILD)
        self.assertIn(f"simulator_commit: {pins[0]}", PUBLISH)
        self.assertIn(f"ref: {pins[0]}", BUILD)

    def test_pr_checkout_and_trusted_provenance_are_separate(self):
        self.assertIn("repository: ${{ needs.target.outputs.repository }}", BUILD)
        self.assertIn("ref: ${{ needs.target.outputs.sha }}", BUILD)
        self.assertIn("python3 simulator-tools/web/tools/source_info.py firmware", BUILD)
        self.assertNotIn("python3 .github/simulator/source_info.py", BUILD)
        self.assertNotIn("REQUEST_WORKFLOW_PATH", BUILD)


if __name__ == "__main__":
    unittest.main()
