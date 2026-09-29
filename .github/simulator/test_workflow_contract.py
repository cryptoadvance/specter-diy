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

    def test_reusable_workflows_are_immutable_and_tooling_uses_resolved_main(self):
        pins = re.findall(r"(?:browser-simulator|publish-browser)\.yml@([A-Za-z0-9_.-]+)",
                          BUILD + PUBLISH)
        self.assertEqual(len(pins), 2)
        self.assertTrue(all(re.fullmatch(r"[a-f0-9]{40}", pin) for pin in pins))
        self.assertEqual(pins[0], pins[1])
        self.assertIn("fetch_main(simulator_repository", (ROOT / ".github/simulator/resolve_build_target.py").read_text())
        self.assertIn("ref: ${{ needs.target.outputs.simulator_commit }}", BUILD)
        self.assertIn("ref: ${{ needs.resolve.outputs.simulator_commit }}", PUBLISH)
        self.assertIn("target.get(\"simulator_commit\") != current", (ROOT / ".github/simulator/resolve_publisher_target.py").read_text())

    def test_pr_checkout_and_trusted_provenance_are_separate(self):
        self.assertIn("repository: ${{ github.event.pull_request.head.repo.full_name || github.repository }}", BUILD)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.event.repository.default_branch }}", BUILD)
        self.assertIn("repository: ${{ needs.target.outputs.repository }}", BUILD)
        self.assertIn("ref: ${{ needs.target.outputs.sha }}", BUILD)
        self.assertIn("python3 simulator-tools/web/tools/source_info.py firmware", BUILD)
        self.assertNotIn("python3 .github/simulator/source_info.py", BUILD)
        self.assertNotIn("REQUEST_WORKFLOW_PATH", BUILD)


if __name__ == "__main__":
    unittest.main()
