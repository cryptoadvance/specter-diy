import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "embed_git_info.py"


def run_git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
    ).strip()


def run_script(output: Path, cwd: Path, extra_env=None) -> str:
    env = dict(os.environ)
    for key in ("SPECTER_REPRODUCIBLE_BUILD", "SPECTER_GIT_REPOSITORY",
                "SPECTER_GIT_BRANCH", "SPECTER_GIT_COMMIT"):
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    subprocess.check_call(
        [sys.executable, str(SCRIPT), str(output)], cwd=cwd, env=env
    )
    return output.read_text()


class GitInfoReproducibilityTest(TestCase):
    def test_same_commit_ignores_remote_and_checkout_ref(self):
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

            self.assertEqual(content_a, content_b)
            # Checkout metadata is not source identity. Keeping it neutral also
            # avoids attributing fork-only commits to the upstream repository.
            self.assertIn("REPOSITORY = 'unknown'", content_a)
            self.assertIn("BRANCH = 'unknown'", content_a)
            self.assertIn("COMMIT = %r" % commit, content_a)
            self.assertNotIn("release-test", content_a)
            self.assertNotIn("example.invalid", content_a)
            self.assertNotIn("cryptoadvance/specter-diy", content_a)

    def test_without_git_metadata_uses_stable_unknown_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "git-info.py"

            content = run_script(output, root)

            self.assertIn("REPOSITORY = 'unknown'", content)
            self.assertIn("BRANCH = 'unknown'", content)
            self.assertIn("COMMIT = 'unknown'", content)

    def test_reproducible_build_output_is_source_acquisition_independent(self):
        """Release builds (SPECTER_REPRODUCIBLE_BUILD=1) must produce identical
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

            env = {"SPECTER_REPRODUCIBLE_BUILD": "1"}
            from_checkout = run_script(root / "a.py", checkout, env)
            from_archive = run_script(root / "b.py", archive, env)

            self.assertEqual(from_checkout, from_archive)
            self.assertIn("REPOSITORY = 'unknown'", from_checkout)
            self.assertIn("BRANCH = 'unknown'", from_checkout)
            self.assertIn("COMMIT = 'unknown'", from_checkout)
            self.assertNotIn(commit, from_checkout)

    def test_explicit_overrides_are_embedded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = run_script(
                root / "git-info.py",
                root,
                {
                    "SPECTER_GIT_REPOSITORY": "https://example.org/specter-diy",
                    "SPECTER_GIT_BRANCH": "v9.9.9",
                    "SPECTER_GIT_COMMIT": "0" * 40,
                },
            )

            self.assertIn(
                "REPOSITORY = 'https://example.org/specter-diy'", content
            )
            self.assertIn("BRANCH = 'v9.9.9'", content)
            self.assertIn("COMMIT = '%s'" % ("0" * 40), content)
