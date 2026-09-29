#!/usr/bin/env python3
"""Verify a self-contained browser build before preview publication."""
from hashlib import sha256
from pathlib import Path
import json
import os
import re


def verify(root: Path, expected_sha: str | None = None, expected_repo: str | None = None,
           expected_simulator_sha: str | None = None,
           expected_simulator_repo: str | None = None) -> dict:
    root = root.resolve()
    pointer = json.loads((root / "browser/current.json").read_text())
    build_path = pointer["build"]
    if not re.fullmatch(r"builds/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[a-f0-9]{40}/", build_path):
        raise ValueError("Invalid build pointer")
    build = (root / build_path).resolve()
    if not build.is_relative_to(root):
        raise ValueError("Build escaped staging directory")
    manifest = json.loads((build / "build-info.json").read_text())
    source = manifest["source"]
    simulator = manifest["simulator"]
    commit = source["commit"]
    repository = source["repository"]
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Invalid source commit")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid source repository")
    if not re.fullmatch(r"[a-f0-9]{40}", simulator["commit"]):
        raise ValueError("Invalid simulator commit")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", simulator["repository"]):
        raise ValueError("Invalid simulator repository")
    if build_path != f"builds/{repository}/{commit}/":
        raise ValueError("Manifest does not match build path")
    if expected_sha and commit != expected_sha:
        raise ValueError("Build does not match workflow commit")
    if expected_repo and repository.lower() != expected_repo.lower():
        raise ValueError("Build does not match workflow repository")
    if expected_simulator_sha and simulator["commit"] != expected_simulator_sha:
        raise ValueError("Build does not match simulator tooling commit")
    if expected_simulator_repo and simulator["repository"].lower() != expected_simulator_repo.lower():
        raise ValueError("Build does not match simulator tooling repository")
    artifacts = manifest["artifacts"]
    if set(artifacts) != {"micropython.js", "micropython.wasm", "micropython.data"}:
        raise ValueError("Unexpected artifact set")
    for name, record in artifacts.items():
        path = build / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != record["bytes"]:
            raise ValueError(f"Missing or invalid {name}")
        if sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Hash mismatch for {name}")
    artifact_set = sha256(''.join(artifacts[name]['sha256'] for name in sorted(artifacts)).encode()).hexdigest()
    if manifest['artifact_set_sha256'] != artifact_set or pointer['version'] != artifact_set[:16]:
        raise ValueError("Artifact set hash mismatch")
    return manifest


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent
    result = verify(base, os.getenv("EXPECTED_SHA"), os.getenv("SPECTER_SOURCE_REPOSITORY"),
                    os.getenv("SIMULATOR_COMMIT"), os.getenv("SIMULATOR_REPOSITORY"))
    print("Verified browser build", result["source"]["repository"], result["source"]["commit"])
