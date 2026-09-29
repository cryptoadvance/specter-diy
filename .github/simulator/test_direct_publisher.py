#!/usr/bin/env python3
"""Publisher checks for the direct pull_request -> workflow_run chain."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from hashlib import sha256
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_preview as publisher

BASE = "cryptoadvance/specter-diy"
FORK = "contributor/specter-diy"
SHA = "a" * 40
PIN = "b" * 40


def pr(repository=BASE, sha=SHA, state="open", branch="master"):
    return {"number": 19, "state": state,
            "head": {"sha": sha, "ref": "feature",
                     "repo": {"full_name": repository}},
            "base": {"ref": branch, "repo": {"full_name": BASE}}}


def run(repository=BASE, sha=SHA, associated=True, conclusion="failure"):
    return {"id": 101, "html_url": "https://github.com/cryptoadvance/specter-diy/actions/runs/101",
            "path": ".github/workflows/build.yml@master", "event": "pull_request",
            "conclusion": conclusion, "head_sha": sha, "head_branch": "feature",
            "head_repository": {"full_name": repository},
            "pull_requests": ([{"number": 19, "head": {"sha": sha}}] if associated else [])}


def target(repository=BASE, sha=SHA, simulator=PIN):
    return {"event": "pull_request", "number": 19, "branch": "feature",
            "repository": repository, "commit": sha,
            "base_repository": BASE, "base_branch": "master",
            "simulator_repository": publisher.EXPECTED_SIMULATOR,
            "simulator_commit": simulator}


class DirectPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.event = self.root / "event.json"
        self.target = self.root / "target.json"
        self.pages = self.root / "pages"
        self.pages.mkdir()
        self.env = patch.dict("os.environ", {"GITHUB_REPOSITORY": BASE,
                              "APPROVED_SIMULATOR_COMMIT": PIN})
        self.env.start()
        self.addCleanup(self.env.stop)

    def args(self, build_run=None, build_target=None):
        self.event.write_text(json.dumps({"repository": {"full_name": BASE,
                                  "default_branch": "master"},
                                  "workflow_run": build_run or run()}))
        if build_target is not None:
            self.target.write_text(json.dumps(build_target))
        return SimpleNamespace(event=self.event, target=self.target,
                               browser=self.root / "browser", firmware=self.root / "firmware",
                               runtime=self.root / "runtime.js", pages=self.pages,
                               state=self.root / "state.json")

    def test_same_repository_pr_failure_removes_obsolete_preview(self):
        preview = self.pages / "pr/19"
        preview.mkdir(parents=True)
        (preview / "index.html").write_text("old")
        args = self.args()
        with patch.object(publisher, "api", return_value=pr()):
            result = publisher.prepare(args)
        self.assertFalse(result["published"])
        self.assertFalse(preview.exists())

    def test_older_failed_run_does_not_remove_newer_preview(self):
        preview = self.pages / "pr/19"
        preview.mkdir(parents=True)
        (preview / "index.html").write_text("newer")
        (preview / ".specter-build.json").write_text(json.dumps({"run_id": 102, "sha": SHA}))
        args = self.args()
        with patch.object(publisher, "api", return_value=pr()):
            result = publisher.prepare(args)
        self.assertTrue(result["skip"])
        self.assertEqual((preview / "index.html").read_text(), "newer")

    def test_fork_pr_without_association_uses_head_identity(self):
        args = self.args(run(FORK, associated=False))
        with patch.object(publisher, "api", return_value=[pr(FORK)]):
            result = publisher.prepare(args)
        self.assertEqual(result["repo"], FORK)
        self.assertEqual(result["number"], 19)

    def test_stale_updated_closed_and_retargeted_prs_are_skipped(self):
        for current in (pr(sha="c" * 40), pr(state="closed"), pr(branch="other")):
            with self.subTest(current=current):
                args = self.args()
                with patch.object(publisher, "api", return_value=current):
                    result = publisher.prepare(args)
                self.assertTrue(result["skip"])

    def test_success_requires_matching_target_and_pin(self):
        for changed in ({"repository": FORK}, {"commit": "c" * 40},
                        {"simulator_commit": "c" * 40},
                        {"base_repository": "attacker/specter-diy"}):
            with self.subTest(changed=changed):
                record = target()
                record.update(changed)
                args = self.args(run(conclusion="success"), record)
                with patch.object(publisher, "api", return_value=pr()):
                    result = publisher.prepare(args)
                self.assertFalse(result["published"])
                self.assertIn("Workflow target", result["reason"])

    def test_missing_and_malformed_target_fail_closed(self):
        args = self.args(run(conclusion="success"))
        with patch.object(publisher, "api", return_value=pr()):
            self.assertFalse(publisher.prepare(args)["published"])
        self.target.write_text("{")
        with patch.object(publisher, "api", return_value=pr()):
            self.assertFalse(publisher.prepare(args)["published"])

    def test_build_artifacts_must_match_same_commit(self):
        args = self.args(run(conclusion="success"), target())
        with patch.object(publisher, "api", return_value=pr()), \
                patch.object(publisher, "validate_bundles", side_effect=ValueError("firmware mismatch")):
            result = publisher.prepare(args)
        self.assertFalse(result["published"])

    def test_browser_javascript_must_match_read_only_runtime(self):
        args = self.args(run(conclusion="success"), target())
        build = self.root / "browser/web/builds/contributor/specter-diy" / SHA
        build.mkdir(parents=True)
        (self.root / "browser/web/browser").mkdir(parents=True)
        (self.root / "browser/web/browser/current.json").write_text(json.dumps({
            "build": f"builds/contributor/specter-diy/{SHA}/"}))
        (build / "micropython.js").write_bytes(b"untrusted")
        args.runtime.write_bytes(b"trusted")
        with patch.object(publisher, "api", return_value=pr()), \
                patch.object(publisher, "validate_bundles", return_value={
                    "simulator": {"repository": publisher.EXPECTED_SIMULATOR,
                                  "commit": PIN}}):
            result = publisher.prepare(args)
        self.assertFalse(result["published"])
        self.assertIn("differs from trusted runtime", result["reason"])

    def test_previous_double_workflow_run_event_is_rejected(self):
        old = run()
        old["event"] = "workflow_run"
        with self.assertRaisesRegex(ValueError, "Unrecognized workflow run"):
            publisher.prepare(self.args(old))

    def test_stale_and_latest_default_branch_runs(self):
        push = run()
        push.update(event="push", head_branch="master",
                    head_repository={"full_name": BASE})
        args = self.args(push)
        with patch.object(publisher, "api", return_value={"sha": "c" * 40}):
            self.assertTrue(publisher.prepare(args)["skip"])
        with patch.object(publisher, "api", return_value={"sha": SHA}):
            self.assertFalse(publisher.prepare(args)["skip"])

    def test_pr_updated_during_publisher_is_rejected_before_push(self):
        state = {"number": 19, "sha": SHA, "repo": BASE, "skip": False}
        with patch.object(publisher, "api", return_value=pr(sha="c" * 40)):
            with self.assertRaisesRegex(ValueError, "changed before publication"):
                publisher.recheck(state, "master")

    def test_default_branch_updated_during_publisher_is_rejected(self):
        state = {"number": None, "sha": SHA, "repo": BASE, "skip": False}
        with patch.object(publisher, "api", return_value={"sha": "c" * 40}):
            with self.assertRaisesRegex(ValueError, "advanced before publication"):
                publisher.recheck(state, "master")

    def test_source_metadata_rejects_other_commit_and_simulator(self):
        directory = self.root / "artifact"
        directory.mkdir()
        for changed in ({"commit": "c" * 40},
                        {"simulator": {"repository": publisher.EXPECTED_SIMULATOR,
                                       "commit": "c" * 40}}):
            data = {"kind": "firmware", "repository": BASE, "commit": SHA,
                    "simulator": {"repository": publisher.EXPECTED_SIMULATOR,
                                  "commit": PIN}}
            data.update(changed)
            (directory / "source.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "different source commit"):
                publisher.read_source(directory, "firmware", SHA, BASE, PIN)

    def test_firmware_hash_mismatch_is_rejected(self):
        browser = self.root / "browser"
        firmware = self.root / "firmware"
        (firmware / "bin").mkdir(parents=True)
        browser.mkdir()
        source = {"repository": BASE, "commit": SHA,
                  "simulator": {"repository": publisher.EXPECTED_SIMULATOR,
                                "commit": PIN}}
        (browser / "source.json").write_text(json.dumps({"kind": "browser", **source}))
        (firmware / "source.json").write_text(json.dumps({"kind": "firmware", **source,
                                        "sha256": {"bin/specter-diy.bin": sha256(b"expected").hexdigest()}}))
        (firmware / "bin/specter-diy.bin").write_bytes(b"wrong")
        (firmware / "bin/specter-diy.hex").write_bytes(b"hex")
        with self.assertRaisesRegex(ValueError, "Firmware hash mismatch"):
            publisher.validate_bundles(browser, firmware, SHA, BASE, PIN)

    def test_traversal_build_pointer_is_rejected(self):
        tree = self.root / "web"
        (tree / "browser").mkdir(parents=True)
        (tree / "browser/current.json").write_text(json.dumps({"build": "../../escape/"}))
        with self.assertRaisesRegex(ValueError, "Invalid build pointer"):
            publisher.verify(tree)

    def test_privileged_workflow_never_executes_pr_artifact(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    "workflows/publish-browser.yml").read_text()
        publish = workflow.split("  publish:\n", 1)[1]
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", workflow)
        self.assertIn("ref: ${{ needs.resolve.outputs.simulator_commit }}", workflow)
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", publish)
        self.assertNotIn("python3 /tmp/specter-artifacts", publish)
        self.assertNotIn("bash /tmp/specter-artifacts", publish)
        self.assertNotIn("build-browser.sh", publish)

    def test_unexpected_browser_file_and_symlink_are_rejected(self):
        tree = self.root / "web"
        tree.mkdir()
        (tree / "evil.sh").write_text("echo bad")
        with self.assertRaisesRegex(ValueError, "Unexpected browser artifact"):
            publisher.validate_artifact_tree(tree, "builds/x/y/" + SHA + "/")
        (tree / "evil.sh").unlink()
        try:
            (tree / "escape").symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires privileges on this Windows host")
        with self.assertRaisesRegex(ValueError, "Unsafe artifact path"):
            publisher.validate_artifact_tree(tree, "builds/x/y/" + SHA + "/")


if __name__ == "__main__":
    unittest.main()
