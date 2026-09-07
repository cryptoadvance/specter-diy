import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "embed_git_info.py"


def load_embed_git_info():
    """Load tools/embed_git_info.py as a module."""
    spec = importlib.util.spec_from_file_location("embed_git_info", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
    ).strip()


def run_script(output: Path, cwd: Path, extra_args=None) -> str:
    args = [sys.executable, str(SCRIPT)]
    if extra_args:
        args.extend(extra_args)
    args.append(str(output))
    subprocess.check_call(
        args, cwd=cwd
    )
    return output.read_text()


class GitUrlSanitizationTest(TestCase):
    """Test that git remote URLs are sanitized before embedding."""

    def setUp(self):
        self.module = load_embed_git_info()

    def test_sanitizes_https_url_with_token(self):
        """Token in HTTPS URL must be stripped."""
        url = "https://ghp_secret123@github.com/org/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("https://github.com/org/repo.git", result)

    def test_sanitizes_https_url_with_user_pass(self):
        """User:pass in HTTPS URL must be stripped."""
        url = "https://user:pass@gitlab.com/org/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("https://gitlab.com/org/repo.git", result)

    def test_sanitizes_ssh_url_with_user(self):
        """SSH URLs with explicit user (git@) are kept as-is (no secret)."""
        url = "git@github.com:org/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("git@github.com:org/repo.git", result)

    def test_sanitizes_ssh_scheme_url(self):
        """SSH scheme URLs keep scheme, strip userinfo."""
        url = "ssh://git@github.com:22/org/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("ssh://github.com:22/org/repo.git", result)

    def test_sanitizes_git_scheme_url(self):
        """Git protocol URLs pass through (no userinfo possible)."""
        url = "git://github.com/org/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("git://github.com/org/repo.git", result)

    def test_rejects_file_protocol(self):
        """file:// URLs leak local paths and are rejected."""
        url = "file:///home/user/repo"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("unknown", result)

    def test_rejects_ftp_protocol(self):
        """FTP URLs are not in allowlist and rejected."""
        url = "ftp://user@host/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("unknown", result)

    def test_rejects_malformed_url_with_multiple_ats(self):
        """Malformed URLs with @ in netloc after stripping are rejected."""
        url = "https://token@host@evil.com/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("unknown", result)

    def test_sanitizes_url_with_port(self):
        """URLs with ports are preserved."""
        url = "https://token@github.com:8443/org/repo.git"
        result = self.module._sanitize_remote_url(url)
        self.assertEqual("https://github.com:8443/org/repo.git", result)

    def test_rejects_empty_url(self):
        """Empty URLs are rejected."""
        result = self.module._sanitize_remote_url("")
        self.assertEqual("unknown", result)

    def test_rejects_none(self):
        """None is rejected."""
        result = self.module._sanitize_remote_url(None)
        self.assertEqual("unknown", result)

    def test_rejects_absolute_local_path(self):
        """Local filesystem paths leak usernames and are rejected."""
        result = self.module._sanitize_remote_url("/home/user/repo")
        self.assertEqual("unknown", result)

    def test_rejects_relative_local_path(self):
        """Relative local paths are rejected."""
        result = self.module._sanitize_remote_url("../repo")
        self.assertEqual("unknown", result)

    def test_rejects_windows_path(self):
        """Windows paths are rejected."""
        result = self.module._sanitize_remote_url(r"C:\Users\marco\repo")
        self.assertEqual("unknown", result)

    def test_rejects_plain_string(self):
        """Arbitrary non-URL strings are rejected."""
        result = self.module._sanitize_remote_url("just-a-random-string")
        self.assertEqual("unknown", result)

    def test_rejects_scp_like_without_user(self):
        """host:path without user@ is not scp syntax; reject it."""
        result = self.module._sanitize_remote_url("github.com:org/repo.git")
        self.assertEqual("unknown", result)


class GitInfoReproducibilityTest(TestCase):
    def test_developer_build_embeds_local_checkout_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            clone_a = root / "clone-a"
            clone_b = root / "clone-b"
            source.mkdir()

            run_git(source, "init")
            run_git(source, "config", "user.name", "Specter Test")
            run_git(source, "config", "user.email", "specter@example.invalid")
            (source / "payload.txt").write_text("same source\n")
            run_git(source, "add", "payload.txt")
            run_git(source, "commit", "-m", "fixture")
            commit = run_git(source, "rev-parse", "HEAD")

            run_git(root, "clone", str(source), str(clone_a))
            run_git(root, "clone", str(source), str(clone_b))

            run_git(clone_a, "checkout", "-b", "release-test")
            run_git(
                clone_a,
                "remote",
                "set-url",
                "origin",
                "git@example.invalid:fork/specter-diy.git",
            )

            run_git(clone_b, "checkout", "--detach", commit)
            run_git(
                clone_b,
                "remote",
                "set-url",
                "origin",
                "https://example.invalid/other/specter-diy.git",
            )

            content_a = run_script(root / "git-info-a.py", clone_a)
            content_b = run_script(root / "git-info-b.py", clone_b)

            self.assertNotEqual(content_a, content_b)
            self.assertIn(
                "REPOSITORY = 'git@example.invalid:fork/specter-diy.git'",
                content_a,
            )
            self.assertIn("BRANCH = 'release-test'", content_a)
            self.assertIn("COMMIT = %r" % commit, content_a)
            self.assertIn(
                "REPOSITORY = 'https://example.invalid/other/specter-diy.git'",
                content_b,
            )
            self.assertIn("COMMIT = %r" % commit, content_b)

    def test_without_git_metadata_uses_stable_unknown_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "git-info.py"

            content = run_script(output, root)

            self.assertIn("REPOSITORY = 'unknown'", content)
            self.assertIn("BRANCH = 'unknown'", content)
            self.assertIn("COMMIT = 'unknown'", content)

    def test_without_origin_uses_unknown_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_git(root, "init")

            content = run_script(root / "git-info.py", root)

            self.assertIn("REPOSITORY = 'unknown'", content)
            self.assertNotIn(str(root), content)

    def test_reproducible_build_output_is_source_acquisition_independent(self):
        """Reproducible builds must produce identical
        output from a git checkout and from a .git-less source archive."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            archive = root / "archive"
            checkout.mkdir()

            run_git(checkout, "init")
            run_git(checkout, "config", "user.name", "Specter Test")
            run_git(checkout, "config", "user.email", "specter@example.invalid")
            (checkout / "payload.txt").write_text("same source\n")
            run_git(checkout, "add", "payload.txt")
            run_git(checkout, "commit", "-m", "fixture")
            commit = run_git(checkout, "rev-parse", "HEAD")

            # A source archive: same files, no .git metadata.
            archive.mkdir()
            (archive / "payload.txt").write_text("same source\n")

            reproducible_args = ["--reproducible"]
            from_checkout = run_script(
                root / "a.py", checkout, reproducible_args
            )
            from_archive = run_script(root / "b.py", archive, reproducible_args)

            self.assertEqual(from_checkout, from_archive)
            self.assertIn("REPOSITORY = 'unknown'", from_checkout)
            self.assertIn("BRANCH = 'unknown'", from_checkout)
            self.assertIn("COMMIT = 'unknown'", from_checkout)
            self.assertNotIn(commit, from_checkout)

    def test_make_forwards_reproducible_mode(self):
        environment_command = subprocess.check_output(
            ["make", "-n", "git-info"],
            cwd=REPO_ROOT,
            env={**os.environ, "REPRODUCIBLE": "1"},
            text=True,
        )
        developer_command = subprocess.check_output(
            ["make", "-n", "git-info", "REPRODUCIBLE=0"], cwd=REPO_ROOT, text=True
        )
        reproducible_command = subprocess.check_output(
            ["make", "-n", "git-info", "REPRODUCIBLE=1"],
            cwd=REPO_ROOT,
            text=True,
        )

        self.assertIn("--reproducible", environment_command)
        self.assertNotIn("--reproducible", developer_command)
        self.assertIn("--reproducible", reproducible_command)
