from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CALLER = (ROOT / ".github/workflows/browser-simulator.yml").read_text()
PUBLISHER_WORKFLOW = (ROOT / ".github/workflows/publish-browser.yml").read_text()
PUBLISHER = (ROOT / ".github/simulator/publish_preview.py").read_text()


class WorkflowContractTests(unittest.TestCase):
    def test_reusable_workflow_pin_is_full_and_matches_trusted_publisher(self):
        caller = re.search(
            r"uses: cryptoadvance/specter-diy-web-simulator/\.github/workflows/build-preview\.yml@([a-f0-9]{40})",
            CALLER,
        )
        publisher = re.search(r"WEB_SIMULATOR_SHA: ([a-f0-9]{40})", PUBLISHER_WORKFLOW)
        self.assertIsNotNone(caller)
        self.assertIsNotNone(publisher)
        self.assertEqual(caller.group(1), publisher.group(1))
        self.assertNotIn("@main", CALLER)
        self.assertNotIn("@master", CALLER)

    def test_build_and_close_signal_are_read_only(self):
        self.assertIn("permissions:\n  contents: read", CALLER)
        self.assertNotRegex(CALLER, r"(?m)^\s+(?:contents|issues|pull-requests|pages):\s+write")
        self.assertNotIn("secrets: inherit", CALLER)
        self.assertIn("github.event.action == 'closed'", CALLER)

    def test_only_local_publisher_has_page_and_comment_permissions(self):
        for permission in ("actions: read", "contents: write", "issues: write", "pull-requests: read",
                          "pages: write", "id-token: write"):
            self.assertIn(permission, PUBLISHER_WORKFLOW)
        self.assertIn("workflow_run:", PUBLISHER_WORKFLOW)
        self.assertNotIn("pull_request_target", PUBLISHER_WORKFLOW)
        self.assertNotIn("secrets: inherit", PUBLISHER_WORKFLOW)

    def test_publisher_is_data_only_and_rejects_unsafe_inputs(self):
        self.assertNotIn("subprocess", PUBLISHER)
        self.assertNotIn("exec(", PUBLISHER)
        self.assertNotIn("eval(", PUBLISHER)
        for contract in (
            "workflow_run_id", "workflow_run_attempt", "schema_version", "source_repository",
            "source_sha", "web_simulator_sha", "sha256", "Special artifact file type",
            "Artifact path traversal", "Symlink in publication input", "is_newer_preview",
        ):
            self.assertIn(contract, PUBLISHER)

    def test_external_actions_in_publisher_use_commit_pins(self):
        actions = re.findall(r"(?m)^[ \t]*uses:[ \t]*[^@\s]+@([^\s]+)[ \t]*$", PUBLISHER_WORKFLOW)
        self.assertTrue(actions)
        self.assertTrue(all(re.fullmatch(r"[a-f0-9]{40}", action) for action in actions), actions)


if __name__ == "__main__":
    unittest.main()
