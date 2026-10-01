#!/usr/bin/env python3
"""Static permissions and single-resolution simulator contract."""
from pathlib import Path
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

    def test_build_uses_current_simulator_and_publisher_stays_local(self):
        self.assertNotIn("specter-diy-web-simulator/.github/workflows/", BUILD)
        self.assertIn("needs: [target, browser_runtime]", BUILD)
        self.assertEqual(BUILD.count("ref: ${{ needs.target.outputs.simulator_commit }}"), 3)
        self.assertIn("python3 simulator-tools/web/browser/replace_glue.py", BUILD)
        self.assertNotIn("specter-diy-web-simulator/.github/workflows/publish-browser.yml@", PUBLISH)
        self.assertNotIn("be15b999", BUILD + PUBLISH)
        self.assertNotIn("05256b9", BUILD + PUBLISH)
        self.assertIn("fetch_main(simulator_repository", (ROOT / ".github/simulator/resolve_build_target.py").read_text())
        self.assertIn("SIMULATOR_COMMIT: ${{ needs.target.outputs.simulator_commit }}", BUILD)
        self.assertIn("ref: ${{ needs.resolve.outputs.simulator_commit }}", PUBLISH)
        self.assertIn("target.get(\"simulator_commit\") != current", (ROOT / ".github/simulator/resolve_publisher_target.py").read_text())

    def test_privileged_job_only_validates_read_only_runtime(self):
        runtime = PUBLISH.split("  runtime:\n", 1)[1].split("  publish:\n", 1)[0]
        publish = PUBLISH.split("  publish:\n", 1)[1]
        self.assertIn("permissions:\n      contents: read", runtime)
        self.assertIn("bash web/browser/build-browser.sh", runtime)
        self.assertNotIn("build-browser.sh", publish)
        self.assertIn("name: publisher-runtime", PUBLISH)
        self.assertNotIn("--name trusted-runtime", PUBLISH)

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
