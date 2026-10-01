from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import io
import json
import os
import shutil
import stat
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_preview as publisher

CALLER = "cryptoadvance/specter-diy"
FORK = "alice/specter-diy"
SIMULATOR = publisher.SIMULATOR_REPOSITORY
SIMULATOR_SHA = "d" * 40
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def make_target(root, run_id=100, sha=SHA_A, repository=FORK, simulator_sha=SIMULATOR_SHA):
    root.mkdir(parents=True, exist_ok=True)
    target = {
        "event": "pull_request", "number": 7, "branch": "feature",
        "repository": repository, "commit": sha, "base_repository": CALLER,
        "base_branch": "master", "simulator_repository": SIMULATOR,
        "simulator_commit": simulator_sha, "workflow_run_id": run_id,
        "workflow_run_attempt": 1,
    }
    (root / "target.json").write_text(json.dumps(target))
    return target


def make_bundle(root, target, simulator_sha=SIMULATOR_SHA):
    build = f"builds/{target['repository']}/{target['commit']}/"
    (root / "browser").mkdir(parents=True)
    (root / build).mkdir(parents=True)
    payload = {name: ("payload:" + name).encode() for name in publisher.PAYLOAD_FILES}
    records = {name: {"bytes": len(data), "sha256": sha256(data).hexdigest()}
               for name, data in payload.items()}
    artifact_set = sha256("".join(records[name]["sha256"] for name in sorted(records)).encode()).hexdigest()
    manifest = {
        "source": {"repository": target["repository"], "commit": target["commit"]},
        "simulator": {"repository": SIMULATOR, "commit": simulator_sha},
        "experimental": True, "artifacts": records, "artifact_set_sha256": artifact_set,
    }
    (root / "browser/current.json").write_text(json.dumps({"build": build, "version": artifact_set[:16]}))
    (root / build / "build-info.json").write_text(json.dumps(manifest))
    for name, data in payload.items():
        (root / build / name).write_bytes(data)
    files = ["browser/current.json", *(build + name for name in publisher.BUILD_FILES)]
    file_records = {}
    for name in files:
        data = (root / name).read_bytes()
        file_records[name] = {"bytes": len(data), "sha256": sha256(data).hexdigest()}
    provenance = {
        "schema_version": 1,
        "source_repository": target["repository"],
        "source_sha": target["commit"],
        "pr_number": target["number"],
        "web_simulator_repository": SIMULATOR,
        "web_simulator_sha": simulator_sha,
        "workflow_run_id": target["workflow_run_id"],
        "workflow_run_attempt": target["workflow_run_attempt"],
        "files": file_records,
    }
    (root / "provenance.json").write_text(json.dumps(provenance))
    return provenance


def bundle_names(root):
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


class ArchiveValidationTests(TestCase):
    def extract(self, entries):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            for name, data, mode in entries:
                info = zipfile.ZipInfo(name)
                if mode:
                    info.create_system = 3
                    info.external_attr = mode << 16
                output.writestr(info, data)
        destination = Path(self.temp.name) / "extracted"
        return publisher.extract_archive(archive.getvalue(), destination)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_accepts_regular_data_archive(self):
        names = self.extract([("target.json", b"{}", stat.S_IFREG | 0o644)])
        self.assertEqual(names, {"target.json"})

    def test_rejects_traversal_absolute_drive_and_malformed_archives(self):
        for entry in ("../outside", "/absolute", "C:/outside", "a/../../outside"):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                self.extract([(entry, b"unsafe", stat.S_IFREG | 0o644)])
        with self.assertRaises(ValueError):
            publisher.extract_archive(b"not a zip archive", Path(self.temp.name) / "bad")

    def test_rejects_symlink_archive_entry(self):
        with self.assertRaisesRegex(ValueError, "Special artifact file type"):
            self.extract([("link", b"../../outside", stat.S_IFLNK | 0o777)])

    def test_rejects_extra_or_empty_archive_directories(self):
        with self.assertRaisesRegex(ValueError, "Unexpected empty"):
            self.extract([("target.json", b"{}", 0), ("unused/", b"", stat.S_IFDIR | 0o755)])


class BrowserArtifactTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = make_target(self.root / "target")
        self.bundle = self.root / "bundle"
        make_bundle(self.bundle, self.target)
        trusted = self.root / "trusted-web"
        trusted.mkdir()
        (trusted / "index.html").write_text("<strong>NEVER ENTER A REAL SEED PHRASE</strong>")
        self.old_trusted = os.environ.get("TRUSTED_WEB")
        os.environ["TRUSTED_WEB"] = str(trusted)
        self.addCleanup(self.restore_trusted)

    def restore_trusted(self):
        if self.old_trusted is None:
            os.environ.pop("TRUSTED_WEB", None)
        else:
            os.environ["TRUSTED_WEB"] = self.old_trusted

    def test_accepts_complete_provenance_and_matching_payload(self):
        result = publisher.validate_browser_bundle(self.bundle, bundle_names(self.bundle),
                                                   self.target, SIMULATOR_SHA)
        self.assertEqual(result, {"repository": SIMULATOR, "commit": SIMULATOR_SHA})

    def test_rejects_wrong_specter_sha_repository_and_simulator_pin(self):
        for change in (
            {"commit": SHA_C},
            {"repository": "alice/other-repo"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                wrong = dict(self.target, **change)
                publisher.validate_browser_bundle(self.bundle, bundle_names(self.bundle), wrong, SIMULATOR_SHA)
        with self.assertRaises(ValueError):
            publisher.validate_browser_bundle(self.bundle, bundle_names(self.bundle), self.target, SHA_C)

    def test_rejects_bad_hash_wrong_build_manifest_and_extra_files(self):
        build = self.bundle / f"builds/{FORK}/{SHA_A}"
        payload = build / "micropython.wasm"
        payload.write_bytes(b"x" * payload.stat().st_size)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            publisher.validate_browser_bundle(self.bundle, bundle_names(self.bundle), self.target, SIMULATOR_SHA)
        shutil.rmtree(self.bundle)
        make_bundle(self.bundle, self.target)
        (self.bundle / "unexpected.txt").write_text("extra")
        with self.assertRaisesRegex(ValueError, "structure"):
            publisher.validate_browser_bundle(self.bundle, bundle_names(self.bundle), self.target, SIMULATOR_SHA)

    def test_rejects_symlink_and_escaped_publication_tree(self):
        outside = self.root / "outside"
        outside.write_text("outside")
        link = self.root / "link"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Symlink creation is not available")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            publisher.validate_tree_no_symlinks(self.root)


class PreviewOrderingTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pages = self.root / "pages"
        self.pages.mkdir()
        self.preview = self.pages / "pr" / "7"
        self.preview.mkdir(parents=True)

    def write_marker(self, run_id, sha):
        (self.preview / ".specter-build.json").write_text(json.dumps({
            "run_id": run_id, "sha": sha, "repository": FORK, "simulator_sha": SIMULATOR_SHA,
        }))

    def test_old_run_cannot_remove_or_replace_newer_preview(self):
        self.write_marker(200, SHA_B)
        self.assertTrue(publisher.is_newer_preview(self.pages, 7, 100))
        self.assertFalse(publisher.remove_preview(self.pages, 7, 100))
        self.assertEqual(publisher.read_marker(self.preview)["sha"], SHA_B)

    def test_latest_invalid_build_removes_old_preview(self):
        self.write_marker(100, SHA_A)
        self.assertTrue(publisher.remove_preview(self.pages, 7, 200))
        self.assertFalse(self.preview.exists())

    def test_closed_pr_cleanup_removes_its_current_preview(self):
        self.write_marker(100, SHA_A)
        self.assertTrue(publisher.remove_preview(self.pages, 7, 150))
        self.assertFalse(self.preview.exists())


class PublisherFlowTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pages = self.root / "pages"
        self.pages.mkdir()
        self.trusted = self.root / "trusted-web"
        self.trusted.mkdir()
        (self.trusted / "index.html").write_text(
            "NEVER ENTER A REAL SEED PHRASE https://github.com/cryptoadvance/specter-diy"
        )
        (self.trusted / "assets").mkdir()
        (self.trusted / "assets" / "image.svg").write_text("<svg />")
        (self.trusted / "browser").mkdir()
        for name in ("site.js", "runtime-worker.js", "demo-data.js"):
            (self.trusted / "browser" / name).write_text("static shell")
        old_trusted = os.environ.get("TRUSTED_WEB")
        os.environ["TRUSTED_WEB"] = str(self.trusted)
        self.addCleanup(lambda: os.environ.pop("TRUSTED_WEB", None) if old_trusted is None
                        else os.environ.__setitem__("TRUSTED_WEB", old_trusted))
        (self.root / "event.json").write_text("{}")
        self.target_root = self.root / "target"
        self.target = make_target(self.target_root, run_id=201, sha=SHA_B)
        self.run = {
            "id": 201, "run_attempt": 1, "event": "pull_request", "head_sha": SHA_B,
            "head_branch": "feature", "conclusion": "failure", "html_url": "https://github.com/run/201",
            "pull_requests": [{"number": 7}],
        }
        self.pr = {
            "number": 7, "state": "open",
            "base": {"ref": "master", "repo": {"full_name": CALLER}},
            "head": {"ref": "feature", "sha": SHA_B, "repo": {"full_name": FORK}},
        }
        self.state_path = self.root / "state.json"

    def args(self):
        return type("Args", (), {
            "event": self.root / "event.json", "pages": self.pages,
            "trusted_web": self.trusted, "artifacts_root": self.root / "artifacts",
            "state": self.state_path, "simulator_sha": SIMULATOR_SHA,
        })()

    def marker(self, run_id, sha):
        preview = self.pages / "pr" / "7"
        preview.mkdir(parents=True, exist_ok=True)
        (preview / ".specter-build.json").write_text(json.dumps({
            "run_id": run_id, "sha": sha, "repository": FORK, "simulator_sha": SIMULATOR_SHA,
        }))

    def patch_prepare(self, pr=None):
        pr = pr or self.pr
        return (
            patch.object(publisher, "read_run_context", return_value=({}, self.run, CALLER, "master")),
            patch.object(publisher, "download_matching_artifact", return_value=(self.target_root, {"target.json"})),
            patch.object(publisher, "find_pr_for_run", return_value=pr),
        )

    def test_old_success_cannot_replace_preview_for_current_newer_head(self):
        self.run.update({"id": 100, "head_sha": SHA_A, "conclusion": "success"})
        self.target = make_target(self.target_root, run_id=100, sha=SHA_A)
        self.marker(200, SHA_B)
        patches = self.patch_prepare()
        with patches[0], patches[1], patches[2]:
            state = publisher.prepare(self.args())
        self.assertEqual(state["action"], "skip")
        self.assertEqual(publisher.read_marker(self.pages / "pr/7")["sha"], SHA_B)

    def test_latest_failed_build_cleans_stale_preview_and_sets_failure_comment(self):
        self.marker(100, SHA_A)
        patches = self.patch_prepare()
        with patches[0], patches[1], patches[2]:
            state = publisher.prepare(self.args())
        self.assertEqual(state["mode"], "pr_failure")
        self.assertFalse(state["published"])
        self.assertTrue(state["comment"])
        self.assertFalse((self.pages / "pr/7").exists())

    def test_validated_preview_copies_only_static_shell_and_hashed_data(self):
        bundle = self.root / "bundle"
        make_bundle(bundle, self.target)
        publisher.publish_payload(bundle, self.pages, self.trusted, self.target, SIMULATOR_SHA, self.run)
        preview = self.pages / "pr" / "7"
        self.assertTrue((preview / "index.html").is_file())
        self.assertIn("https://github.com/alice/specter-diy", (preview / "index.html").read_text())
        self.assertEqual((preview / "browser/site.js").read_text(), "static shell")
        self.assertTrue((preview / f"builds/{FORK}/{SHA_B}/micropython.wasm").is_file())
        self.assertTrue((preview / "provenance.json").is_file())
        marker = json.loads((preview / ".specter-build.json").read_text())
        self.assertEqual(marker["run_id"], self.run["id"])

    def test_comment_updates_existing_bot_comment_instead_of_posting_another(self):
        state = {
            "comment": True, "number": 7, "source_sha": SHA_B, "source_repository": FORK,
            "repository": CALLER, "run_url": "https://github.com/run/201", "published": False,
        }
        self.state_path.write_text(json.dumps(state))
        old_repo = os.environ.get("GITHUB_REPOSITORY")
        old_token = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_REPOSITORY"] = CALLER
        os.environ["GITHUB_TOKEN"] = "test"
        self.addCleanup(lambda: os.environ.pop("GITHUB_REPOSITORY", None) if old_repo is None
                        else os.environ.__setitem__("GITHUB_REPOSITORY", old_repo))
        self.addCleanup(lambda: os.environ.pop("GITHUB_TOKEN", None) if old_token is None
                        else os.environ.__setitem__("GITHUB_TOKEN", old_token))
        calls = []
        def fake_api(method, path, body=None):
            calls.append((method, path, body))
            if method == "GET" and path == "pulls/7":
                return self.pr
            if method == "GET" and path.startswith("issues/7/comments"):
                return [{"id": 55, "body": publisher.COMMENT_MARKER, "user": {"login": "github-actions[bot]"}}]
            return None
        with patch.object(publisher, "api_request", side_effect=fake_api):
            publisher.update_comment(type("Args", (), {"state": self.state_path})())
        self.assertEqual(sum(call[0] == "POST" for call in calls), 0)
        self.assertEqual(sum(call[0] == "PATCH" for call in calls), 1)


if __name__ == "__main__":
    main()
