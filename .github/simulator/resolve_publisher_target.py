#!/usr/bin/env python3
"""Resolve the simulator tooling revision for the trusted publisher."""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote
import json
import os
import re

SHA_PATTERN = re.compile(r"[a-f0-9]{40}")


def fetch_default_branch_sha(repository: str, branch: str, token: str) -> str:
    request = Request(
        f"https://api.github.com/repos/{repository}/commits/{quote(branch, safe='')}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(request, timeout=30) as response:
        commit = json.load(response).get("sha")
    if not isinstance(commit, str) or not SHA_PATTERN.fullmatch(commit):
        raise ValueError(f"Repository {repository} returned no valid default-branch SHA")
    return commit


def read_target(path: Path, repository: str) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("Build target artifact is missing or invalid")
    target = json.loads(path.read_text())
    if not isinstance(target, dict):
        raise ValueError("Build target artifact is not a JSON object")
    target_repository = target.get("simulator_repository")
    commit = target.get("simulator_commit")
    if not isinstance(target_repository, str) or target_repository.lower() != repository.lower():
        raise ValueError("Build target names an unexpected simulator repository")
    if not isinstance(commit, str) or not SHA_PATTERN.fullmatch(commit):
        raise ValueError("Build target has no valid simulator commit SHA")
    return target_repository, commit


def resolve_simulator_commit(target_path: Path, conclusion: str,
                             repository: str, trusted_commit: str) -> str:
    if not isinstance(trusted_commit, str) or not SHA_PATTERN.fullmatch(trusted_commit):
        raise ValueError("Trusted simulator commit must be a full 40-character SHA")
    if conclusion != "success":
        # Failed runs may have no target artifact; the trusted pin is still
        # sufficient to remove a stale PR preview.
        return trusted_commit
    try:
        target_repository, target_commit = read_target(target_path, repository)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Successful build has no valid target artifact: {error}") from error
    if target_repository.lower() != repository.lower() or target_commit != trusted_commit:
        raise ValueError("Build target does not match trusted simulator repository and commit")
    return trusted_commit


def should_publish(event: str, branch: str, run_sha: str, default_branch: str,
                   repository: str, token: str, fetch_head=fetch_default_branch_sha) -> bool:
    if event != "push":
        return True
    if branch != default_branch:
        return False
    if not isinstance(run_sha, str) or not SHA_PATTERN.fullmatch(run_sha):
        raise ValueError("Default-branch workflow run has no valid full commit SHA")
    current_sha = fetch_head(repository, default_branch, token)
    if not isinstance(current_sha, str) or not SHA_PATTERN.fullmatch(current_sha):
        raise ValueError("Could not resolve the current default-branch SHA")
    return run_sha == current_sha


def main():
    commit = resolve_simulator_commit(
        Path(os.environ["TARGET_FILE"]),
        os.environ["BUILD_CONCLUSION"],
        os.environ["SIMULATOR_REPOSITORY"],
        os.environ["TRUSTED_SIMULATOR_COMMIT"],
    )
    publish = should_publish(
        os.environ["BUILD_EVENT"],
        os.environ["BUILD_BRANCH"],
        os.environ["BUILD_SHA"],
        os.environ["DEFAULT_BRANCH"],
        os.environ["GITHUB_REPOSITORY"],
        os.environ["GH_TOKEN"],
    )
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"simulator_commit={commit}\n")
        output.write(f"should_publish={'true' if publish else 'false'}\n")


if __name__ == "__main__":
    main()
