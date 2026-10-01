#!/usr/bin/env python3
"""Trusted, data-only publisher for the browser simulator workflow.

This file runs from the protected Specter default branch. It never imports or
executes code from the PR artifact or the Web Simulator checkout.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import argparse
import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile

SIMULATOR_REPOSITORY = "cryptoadvance/specter-diy-web-simulator"
SIMULATOR_PIN = os.environ.get("WEB_SIMULATOR_SHA", "")
WORKFLOW_PATH = ".github/workflows/browser-simulator.yml"
COMMENT_MARKER = "<!-- specter-browser-preview -->"
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")
HEX256 = re.compile(r"[a-f0-9]{64}\Z")
TARGET_KEYS = {
    "event", "number", "branch", "repository", "commit", "base_repository",
    "base_branch", "simulator_repository", "simulator_commit",
    "workflow_run_id", "workflow_run_attempt",
}
BUILD_FILES = ("build-info.json", "micropython.js", "micropython.wasm", "micropython.data")
PAYLOAD_FILES = ("micropython.js", "micropython.wasm", "micropython.data")
MAX_ARCHIVE_BYTES = 300_000_000
MAX_EXTRACTED_BYTES = 350_000_000
MAX_FILE_BYTES = 300_000_000
MAX_ARCHIVE_ENTRIES = 32


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def valid_repository(value: object) -> bool:
    return isinstance(value, str) and bool(REPOSITORY.fullmatch(value)) and \
        all(part not in (".", "..") for part in value.split("/"))


def safe_relative(value: str) -> PurePosixPath:
    require(isinstance(value, str) and value and "\\" not in value, "Unsafe artifact path")
    require(not value.startswith("/") and not PureWindowsPath(value).drive, "Absolute artifact path")
    raw = value[:-1] if value.endswith("/") else value
    pieces = raw.split("/")
    require(all(piece not in ("", ".", "..") for piece in pieces), "Artifact path traversal")
    path = PurePosixPath(raw)
    require(not path.is_absolute() and path.parts, "Unsafe artifact path")
    return path


def contained_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = root
    for part in safe_relative(relative).parts:
        path = path / part
        require(not path.is_symlink(), "Symlink in artifact or publication tree")
    require(path.resolve().is_relative_to(root), "Path escaped expected root")
    return path


def read_json(path: Path, limit: int = 1_000_000) -> dict:
    require(not path.is_symlink() and path.is_file(), f"Missing metadata: {path.name}")
    require(path.stat().st_size <= limit, f"Metadata too large: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"Invalid metadata: {path.name}")
    return value


def api_request(method: str, path: str, body: dict | None = None):
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    require(valid_repository(repository), "Invalid caller repository")
    url = f"https://api.github.com/repos/{repository}/{path.lstrip('/')}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "specter-diy-browser-preview-publisher",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method, headers=headers)
    with urlopen(request, timeout=45) as response:
        content = response.read(50_000_001)
    require(len(content) <= 50_000_000, "GitHub API response too large")
    if not content:
        return None
    return json.loads(content)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_artifact_zip(artifact_id: int) -> bytes:
    """Fetch an artifact without forwarding the API token to the blob host."""
    request = Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/artifacts/{artifact_id}/zip",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "specter-diy-browser-preview-publisher",
        },
    )
    opener = build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=60)
    except HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        location = error.headers.get("Location", "")
        parsed = urlparse(location)
        host = parsed.hostname or ""
        require(parsed.scheme == "https" and not parsed.username and
                (host.endswith(".blob.core.windows.net") or host.endswith(".githubusercontent.com")),
                "Unexpected GitHub artifact redirect")
        response = urlopen(Request(location, headers={"User-Agent": "specter-diy-browser-preview-publisher"}), timeout=60)
    with response:
        data = response.read(MAX_ARCHIVE_BYTES + 1)
    require(len(data) <= MAX_ARCHIVE_BYTES, "Artifact archive exceeds size limit")
    return data


def artifact_candidates(run_id: int, name: str) -> list[dict]:
    result = api_request("GET", f"actions/runs/{run_id}/artifacts?per_page=100")
    artifacts = result.get("artifacts", []) if isinstance(result, dict) else []
    found = [item for item in artifacts if item.get("name") == name and not item.get("expired")]
    return sorted(found, key=lambda item: (item.get("created_at", ""), item.get("id", 0)), reverse=True)


def extract_archive(data: bytes, destination: Path) -> set[str]:
    """Safely extract regular ZIP data to a new private directory."""
    require(not destination.exists() and not destination.is_symlink(), "Artifact destination already exists")
    destination.mkdir(parents=True)
    extracted: set[str] = set()
    directories: set[str] = set()
    folded: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            require(0 < len(infos) <= MAX_ARCHIVE_ENTRIES, "Unexpected artifact entry count")
            for info in infos:
                name = info.filename
                rel = safe_relative(name)
                normalized = rel.as_posix()
                require(normalized.casefold() not in folded, "Duplicate artifact path")
                folded.add(normalized.casefold())
                mode = (info.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                require(kind in (0, stat.S_IFREG, stat.S_IFDIR), "Special artifact file type")
                is_directory = info.is_dir()
                require((kind != stat.S_IFDIR) if not is_directory else (kind in (0, stat.S_IFDIR)),
                        "Artifact file type mismatch")
                require(not (info.flag_bits & 0x1), "Encrypted artifacts are not supported")
                require(info.file_size <= MAX_FILE_BYTES, "Artifact file exceeds size limit")
                if info.compress_size:
                    require(info.file_size <= max(info.compress_size * 250, 1_000_000),
                            "Suspicious artifact compression ratio")
                target = contained_path(destination, normalized)
                if is_directory:
                    target.mkdir(parents=True, exist_ok=True)
                    directories.add(normalized)
                    continue
                require(normalized not in extracted, "Duplicate artifact file")
                target.parent.mkdir(parents=True, exist_ok=True)
                count = 0
                with archive.open(info, "r") as source, target.open("xb") as sink:
                    while True:
                        block = source.read(64 * 1024)
                        if not block:
                            break
                        count += len(block)
                        total += len(block)
                        require(count <= MAX_FILE_BYTES and total <= MAX_EXTRACTED_BYTES,
                                "Artifact extraction exceeds size limit")
                        sink.write(block)
                require(count == info.file_size, "Artifact size metadata mismatch")
                extracted.add(normalized)
        expected_directories = {
            parent.as_posix()
            for filename in extracted
            for parent in PurePosixPath(filename).parents
            if parent.as_posix() != "."
        }
        require(directories <= expected_directories, "Unexpected empty artifact directory")
    except Exception as error:
        shutil.rmtree(destination, ignore_errors=True)
        if isinstance(error, ValueError):
            raise
        raise ValueError("Malformed or unsafe artifact archive") from error
    return extracted


def download_matching_artifact(run_id: int, attempt: int, name: str, parent: Path,
                               identity_file: str) -> tuple[Path, set[str]] | None:
    """Select the newest artifact carrying this exact GitHub run attempt."""
    candidates = artifact_candidates(run_id, name)
    for candidate in candidates:
        size = candidate.get("size_in_bytes")
        artifact_id = candidate.get("id")
        if type(size) is not int or size > MAX_ARCHIVE_BYTES or type(artifact_id) is not int:
            continue
        directory = parent / f"{name}-{artifact_id}"
        try:
            names = extract_archive(download_artifact_zip(artifact_id), directory)
            metadata = read_json(contained_path(directory, identity_file))
            if metadata.get("workflow_run_id") == run_id and metadata.get("workflow_run_attempt") == attempt:
                return directory, names
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            continue
        shutil.rmtree(directory, ignore_errors=True)
    return None


def validate_target(root: Path, names: set[str], run: dict, repository: str, default_branch: str,
                    simulator_sha: str) -> dict:
    require(names == {"target.json"}, "Unexpected browser target artifact structure")
    target = read_json(contained_path(root, "target.json"))
    require(set(target) == TARGET_KEYS, "Unexpected browser target schema")
    require(target.get("event") == run.get("event") and target.get("event") in ("pull_request", "push"),
            "Browser target event mismatch")
    require(type(target.get("workflow_run_id")) is int and target["workflow_run_id"] == run["id"] and
            type(target.get("workflow_run_attempt")) is int and target["workflow_run_attempt"] == run["run_attempt"],
            "Browser target belongs to another workflow run")
    require(valid_repository(target.get("repository")) and SHA.fullmatch(str(target.get("commit", ""))),
            "Invalid browser target source")
    require(target.get("base_repository", "").lower() == repository.lower() and
            target.get("base_branch") == default_branch, "Browser target is for another repository or branch")
    require(target.get("simulator_repository") == SIMULATOR_REPOSITORY and
            target.get("simulator_commit") == simulator_sha and SHA.fullmatch(simulator_sha),
            "Browser target has the wrong simulator pin")
    number = target.get("number")
    require(type(number) is int and 0 <= number <= 999999, "Invalid browser target PR number")
    branch = target.get("branch")
    require(isinstance(branch, str) and branch and len(branch) <= 250 and "\n" not in branch,
            "Invalid browser target branch")
    if target["event"] == "pull_request":
        require(number > 0 and target["branch"] == run.get("head_branch"), "Browser target PR mismatch")
    else:
        require(number == 0 and target["repository"].lower() == repository.lower() and
                branch == default_branch and run.get("head_branch") == default_branch,
                "Browser target is not a default-branch push")
    return target


def expected_browser_files(repository: str, commit: str) -> set[str]:
    owner, name = repository.split("/", 1)
    build = f"builds/{owner}/{name}/{commit}/"
    return {"browser/current.json", *(build + filename for filename in BUILD_FILES)}


def validate_browser_bundle(root: Path, names: set[str], target: dict, simulator_sha: str) -> dict:
    provenance = read_json(contained_path(root, "provenance.json"))
    require(provenance.get("schema_version") == 1, "Unsupported browser provenance schema")
    require(provenance.get("source_repository", "").lower() == target["repository"].lower() and
            provenance.get("source_sha") == target["commit"] and provenance.get("pr_number") == target["number"],
            "Browser provenance does not match caller source")
    require(provenance.get("web_simulator_repository") == SIMULATOR_REPOSITORY and
            provenance.get("web_simulator_sha") == simulator_sha, "Browser provenance has the wrong simulator pin")
    require(provenance.get("workflow_run_id") == target["workflow_run_id"] and
            provenance.get("workflow_run_attempt") == target["workflow_run_attempt"],
            "Browser artifact belongs to another workflow attempt")
    files = provenance.get("files")
    expected = expected_browser_files(target["repository"], target["commit"])
    require(isinstance(files, dict) and set(files) == expected, "Unexpected browser artifact file contract")
    require(names == expected | {"provenance.json"}, "Unexpected browser artifact structure")
    expected_directories = {
        parent.as_posix()
        for filename in names
        for parent in PurePosixPath(filename).parents
        if parent.as_posix() != "."
    }
    actual_directories = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()}
    require(actual_directories == expected_directories, "Unexpected browser artifact directories")
    for relative, record in files.items():
        require(isinstance(record, dict) and set(record) == {"bytes", "sha256"},
                f"Invalid hash record: {relative}")
        require(type(record["bytes"]) is int and 0 <= record["bytes"] <= MAX_FILE_BYTES and
                isinstance(record["sha256"], str) and HEX256.fullmatch(record["sha256"]),
                f"Invalid file hash metadata: {relative}")
        path = contained_path(root, relative)
        require(path.is_file() and path.stat().st_size == record["bytes"], f"Missing or wrong-size payload: {relative}")
        require(sha256(path.read_bytes()).hexdigest() == record["sha256"], f"Payload hash mismatch: {relative}")

    pointer = read_json(contained_path(root, "browser/current.json"), limit=4096)
    build = f"builds/{target['repository']}/{target['commit']}/"
    require(set(pointer) == {"build", "version"} and pointer.get("build") == build,
            "Browser build pointer does not match source")
    manifest_path = contained_path(root, build + "build-info.json")
    manifest = read_json(manifest_path)
    source = manifest.get("source", {})
    simulator = manifest.get("simulator", {})
    require(source.get("repository", "").lower() == target["repository"].lower() and
            source.get("commit") == target["commit"], "Build manifest has the wrong Specter source")
    require(simulator.get("repository") == SIMULATOR_REPOSITORY and simulator.get("commit") == simulator_sha,
            "Build manifest has the wrong Web Simulator source")
    require(manifest.get("experimental") is True and "NEVER ENTER A REAL SEED PHRASE" in
            (Path(os.environ["TRUSTED_WEB"]) / "index.html").read_text(encoding="utf-8"),
            "Development-build warning is missing")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, dict) and set(artifacts) == set(PAYLOAD_FILES),
            "Unexpected WebAssembly artifact set")
    artifact_set = sha256("".join(artifacts[name].get("sha256", "") for name in sorted(artifacts)).encode()).hexdigest()
    require(manifest.get("artifact_set_sha256") == artifact_set and pointer.get("version") == artifact_set[:16],
            "Browser artifact-set hash mismatch")
    for name in PAYLOAD_FILES:
        record = artifacts[name]
        require(isinstance(record, dict) and type(record.get("bytes")) is int and
                record.get("bytes") == files[build + name]["bytes"] and
                record.get("sha256") == files[build + name]["sha256"],
                f"Build manifest hash mismatch: {name}")
    return {"repository": SIMULATOR_REPOSITORY, "commit": simulator_sha}


def validate_tree_no_symlinks(root: Path) -> None:
    require(not root.is_symlink(), "Symlink in publication input")
    root = root.resolve()
    require(root.is_dir(), "Expected a publication directory")
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Symlink in publication input")
        require(path.resolve().is_relative_to(root), "Publication input escaped its root")
        require(path.is_file() or path.is_dir(), "Special file in publication input")


def walk_files_no_symlinks(root: Path):
    validate_tree_no_symlinks(root)
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def artifact_id_for_comment(run_id: int, name: str) -> int | None:
    candidates = artifact_candidates(run_id, name)
    return candidates[0].get("id") if len(candidates) == 1 and type(candidates[0].get("id")) is int else None


def find_pr_for_run(run: dict, repository: str, default_branch: str) -> dict | None:
    associated = run.get("pull_requests") or []
    candidates = []
    numbers = set()
    for item in associated:
        number = item.get("number")
        if type(number) is int and 0 < number < 1_000_000:
            numbers.add(number)
    for number in sorted(numbers):
        candidates.append(api_request("GET", f"pulls/{number}"))
    if not candidates:
        head_repo = (run.get("head_repository") or {}).get("full_name", "")
        branch = run.get("head_branch")
        if not valid_repository(head_repo) or not isinstance(branch, str) or not branch:
            return None
        head = quote(f"{head_repo.split('/')[0]}:{branch}", safe="")
        base = quote(default_branch, safe="")
        for page in range(1, 11):
            batch = api_request("GET", f"pulls?state=all&head={head}&base={base}&per_page=100&page={page}")
            candidates.extend(batch)
            if len(batch) < 100:
                break
    matches = []
    for pr in candidates:
        base = pr.get("base") or {}
        base_repo = (base.get("repo") or {}).get("full_name", "")
        if base_repo.lower() == repository.lower() and base.get("ref") == default_branch:
            matches.append(pr)
    return matches[0] if len(matches) == 1 else None


def current_default_sha(branch: str) -> str:
    return api_request("GET", f"commits/{quote(branch, safe='')}")["sha"]


def preview_path(pages: Path, number: int) -> Path:
    require(type(number) is int and 0 < number < 1_000_000, "Invalid preview number")
    result = pages / "pr" / str(number)
    require(result.resolve().is_relative_to(pages.resolve()), "Preview destination escaped Pages root")
    require(not result.is_symlink(), "Preview destination is a symlink")
    return result


def read_marker(target: Path) -> dict | None:
    marker = target / ".specter-build.json"
    if not marker.exists() and not marker.is_symlink():
        return None
    data = read_json(marker, 4096)
    require(type(data.get("run_id")) is int and data["run_id"] > 0 and
            SHA.fullmatch(str(data.get("sha", ""))) and valid_repository(data.get("repository")) and
            SHA.fullmatch(str(data.get("simulator_sha", ""))), "Invalid existing preview state")
    return data


def is_newer_preview(pages: Path, number: int, run_id: int) -> bool:
    target = preview_path(pages, number)
    marker = read_marker(target) if target.exists() else None
    return marker is not None and marker["run_id"] > run_id


def remove_preview(pages: Path, number: int, run_id: int) -> bool:
    target = preview_path(pages, number)
    if is_newer_preview(pages, number, run_id):
        return False
    if target.exists():
        validate_tree_no_symlinks(target)
        shutil.rmtree(target)
        return True
    return False


def copy_file_checked(source: Path, destination: Path, source_root: Path, destination_root: Path) -> None:
    require(not source.is_symlink() and source.is_file(), "Unsafe publication source file")
    require(source.resolve().is_relative_to(source_root.resolve()), "Trusted shell file escaped checkout")
    destination = contained_path(destination_root, destination.relative_to(destination_root).as_posix())
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def copy_trusted_shell(trusted_web: Path, destination: Path, destination_root: Path,
                       source_repository: str) -> None:
    validate_tree_no_symlinks(trusted_web)
    require("NEVER ENTER A REAL SEED PHRASE" in
            (trusted_web / "index.html").read_text(encoding="utf-8"), "Safety warning is missing from Web Simulator shell")
    static = [trusted_web / "index.html"]
    static.extend(sorted((trusted_web / "assets").rglob("*")))
    static.extend(trusted_web / "browser" / name for name in ("site.js", "runtime-worker.js", "demo-data.js"))
    for source in static:
        if source.is_dir():
            continue
        relative = source.relative_to(trusted_web)
        target = destination / relative
        require(target.resolve().is_relative_to(destination_root.resolve()), "Trusted shell destination escaped Pages")
        target.parent.mkdir(parents=True, exist_ok=True)
        contents = source.read_bytes()
        if relative.as_posix() in ("index.html", "browser/site.js"):
            canonical = b"https://github.com/cryptoadvance/specter-diy"
            replacement = ("https://github.com/" + source_repository).encode("ascii")
            contents = contents.replace(canonical, replacement)
        target.write_bytes(contents)


def publish_payload(bundle: Path, pages: Path, trusted_web: Path, target: dict,
                    simulator_sha: str, run: dict) -> None:
    validate_tree_no_symlinks(bundle)
    bundle_names = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
    validate_browser_bundle(bundle, bundle_names, target, simulator_sha)
    validate_tree_no_symlinks(pages)
    number = target["number"]
    output = preview_path(pages, number) if number else pages
    if number:
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
    else:
        for item in ("index.html", "assets", "browser", "builds", "provenance.json"):
            path = pages / item
            require(not path.is_symlink(), "Symlink in existing Pages output")
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        output = pages
    copy_trusted_shell(trusted_web, output, pages, target["repository"])
    for relative in sorted(expected_browser_files(target["repository"], target["commit"])):
        source = contained_path(bundle, relative)
        destination = output / relative
        require(destination.resolve().is_relative_to(pages.resolve()), "Browser payload destination escaped Pages")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(contained_path(bundle, "provenance.json"), output / "provenance.json")
    (pages / ".nojekyll").touch()
    if number:
        marker = output / ".specter-build.json"
        marker.write_text(json.dumps({
            "run_id": run["id"], "run_attempt": run["run_attempt"], "sha": target["commit"],
            "repository": target["repository"], "simulator_sha": simulator_sha,
        }, indent=2) + "\n", encoding="utf-8")


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"publish={'true' if state.get('action') == 'publish' else 'false'}\n")
            handle.write(f"deploy={'true' if state.get('deploy') else 'false'}\n")


def read_run_context(event_path: Path, simulator_sha: str) -> tuple[dict, dict, str, str]:
    event = read_json(event_path, limit=5_000_000)
    caller_repository = os.environ["GITHUB_REPOSITORY"]
    require(valid_repository(caller_repository) and
            (event.get("repository") or {}).get("full_name", "").lower() == caller_repository.lower(),
            "Publisher event belongs to another repository")
    default_branch = (event["repository"].get("default_branch") or "")
    require(isinstance(default_branch, str) and default_branch, "Missing repository default branch")
    event_run = event.get("workflow_run")
    require(isinstance(event_run, dict), "Missing workflow run")
    run_id = event_run.get("id")
    require(type(run_id) is int and run_id > 0, "Invalid workflow run id")
    run = api_request("GET", f"actions/runs/{run_id}")
    workflow_path = str(run.get("path", "")).split("@", 1)[0]
    require(workflow_path == WORKFLOW_PATH and run.get("id") == run_id,
            "Run did not come from the local browser workflow")
    require(run.get("event") in ("pull_request", "push"), "Unsupported browser workflow event")
    require(type(run.get("run_attempt")) is int and run["run_attempt"] > 0, "Invalid workflow run attempt")
    require(SHA.fullmatch(str(run.get("head_sha", ""))), "Invalid workflow run SHA")
    require(SHA.fullmatch(simulator_sha), "Invalid configured Web Simulator pin")
    return event, run, caller_repository, default_branch


def run_head_identity(run: dict, target: dict | None) -> tuple[str | None, str | None]:
    if target:
        return target.get("commit"), target.get("repository")
    # The run's associated PR metadata preserves the source SHA even when the
    # Actions run itself uses a synthetic pull/merge ref.
    for item in run.get("pull_requests") or []:
        head = item.get("head") or {}
        repo = head.get("repo") or {}
        if SHA.fullmatch(str(head.get("sha", ""))) and valid_repository(repo.get("full_name")):
            return head["sha"], repo["full_name"]
    return None, None


def prepare(args) -> dict:
    pin = args.simulator_sha
    event, run, repository, default_branch = read_run_context(args.event, pin)
    pages = Path(args.pages)
    trusted_web = Path(args.trusted_web)
    validate_tree_no_symlinks(pages)
    validate_tree_no_symlinks(trusted_web)
    artifacts_root = Path(args.artifacts_root)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    run_attempt = run["run_attempt"]
    downloaded_target = download_matching_artifact(run["id"], run_attempt, "browser-target", artifacts_root,
                                                   "target.json")
    target = None
    target_root = None
    if downloaded_target:
        target_root, target_names = downloaded_target
        try:
            target = validate_target(target_root, target_names, run, repository, default_branch, pin)
        except Exception:
            target = None

    state = {
        "action": "skip", "mode": "skip", "run_id": run["id"], "run_attempt": run_attempt,
        "run_sha": run["head_sha"], "run_url": run.get("html_url", ""),
        "repository": repository, "default_branch": default_branch, "simulator_sha": pin,
        "deploy": False, "comment": False,
    }

    if run["event"] == "push":
        candidate_sha = target.get("commit") if target else run["head_sha"]
        if run.get("head_branch") != default_branch or current_default_sha(default_branch) != candidate_sha:
            save_state(Path(args.state), state)
            return state
        state.update({"source_sha": candidate_sha, "source_repository": repository, "mode": "default"})
        if run.get("conclusion") != "success" or not target or not downloaded_target:
            save_state(Path(args.state), state)
            return state
        bundle_result = download_matching_artifact(run["id"], run_attempt, "browser-preview", artifacts_root,
                                                   "provenance.json")
        if not bundle_result:
            save_state(Path(args.state), state)
            return state
        bundle_root, bundle_names = bundle_result
        try:
            simulator = validate_browser_bundle(bundle_root, bundle_names, target, pin)
            publish_payload(bundle_root, pages, trusted_web, target, pin, run)
        except Exception:
            save_state(Path(args.state), state)
            return state
        state.update({"action": "publish", "published": True, "bundle_root": str(bundle_root),
                      "target_root": str(target_root), "target": target, "simulator": simulator,
                      "deploy": True})
        save_state(Path(args.state), state)
        return state

    pr = find_pr_for_run(run, repository, default_branch)
    if not pr:
        save_state(Path(args.state), state)
        return state
    number = pr.get("number")
    require(type(number) is int and 0 < number < 1_000_000, "Invalid associated pull request")
    base = pr.get("base") or {}
    head = pr.get("head") or {}
    head_repository = (head.get("repo") or {}).get("full_name")
    head_sha = head.get("sha")
    require(base.get("ref") == default_branch and
            (base.get("repo") or {}).get("full_name", "").lower() == repository.lower(),
            "Pull request targets another repository or branch")
    state.update({"number": number, "current_head_sha": head_sha, "current_head_repository": head_repository,
                  "mode": "pr"})
    preview = preview_path(pages, number)
    if pr.get("state") == "closed":
        if not is_newer_preview(pages, number, run["id"]):
            remove_preview(pages, number, run["id"])
            state.update({"action": "publish", "mode": "closed_cleanup", "deploy": has_site(pages)})
        save_state(Path(args.state), state)
        return state

    candidate_sha, candidate_repository = run_head_identity(run, target)
    if not candidate_sha or not candidate_repository:
        save_state(Path(args.state), state)
        return state
    if candidate_sha != head_sha:
        marker = read_marker(preview) if preview.exists() else None
        if not (marker and marker["run_id"] > run["id"]):
            if not marker or marker.get("sha") != head_sha:
                remove_preview(pages, number, run["id"])
                state.update({"action": "publish", "mode": "stale_cleanup", "deploy": has_site(pages)})
        save_state(Path(args.state), state)
        return state

    # The live PR API, rather than artifact metadata, supplies the identity for
    # a current failed build. A malformed target with the current SHA is a
    # failed current build, not a reason to retain the previous preview.
    source_repository = head_repository or candidate_repository
    state.update({"source_sha": head_sha, "source_repository": source_repository})
    state["comment"] = True
    if is_newer_preview(pages, number, run["id"]):
        state["action"] = "skip"
        save_state(Path(args.state), state)
        return state

    error_reason = "The current build did not produce a valid browser preview."
    bundle_result = None
    target_matches_pr = bool(target and head_repository and target["commit"] == head_sha and
                             target["repository"].lower() == head_repository.lower() and
                             target["number"] == number and target["branch"] == head.get("ref"))
    if run.get("conclusion") == "success" and target_matches_pr and downloaded_target:
        bundle_result = download_matching_artifact(run["id"], run_attempt, "browser-preview", artifacts_root,
                                                   "provenance.json")
        if bundle_result:
            try:
                bundle_root, bundle_names = bundle_result
                simulator = validate_browser_bundle(bundle_root, bundle_names, target, pin)
                publish_payload(bundle_root, pages, trusted_web, target, pin, run)
                state.update({"action": "publish", "published": True, "target": target,
                              "target_root": str(target_root), "bundle_root": str(bundle_root),
                              "simulator": simulator, "mode": "pr_success", "deploy": True})
            except Exception:
                remove_preview(pages, number, run["id"])
                state.update({"action": "publish", "published": False, "error": error_reason,
                              "mode": "pr_failure"})
        else:
            remove_preview(pages, number, run["id"])
            state.update({"action": "publish", "published": False, "error": error_reason,
                          "mode": "pr_failure"})
    else:
        remove_preview(pages, number, run["id"])
        state.update({"action": "publish", "published": False, "error": error_reason,
                      "mode": "pr_failure"})
    state["deploy"] = has_site(pages)
    save_state(Path(args.state), state)
    return state


def has_site(pages: Path) -> bool:
    return (pages / "index.html").is_file() or (pages / "pr").is_dir()


def recheck(args) -> dict:
    state = read_json(Path(args.state))
    publish = state.get("action") == "publish"
    pages = Path(args.pages)
    validate_tree_no_symlinks(pages)
    if not publish:
        state["action"] = "skip"
        save_state(Path(args.state), state)
        return state
    repository = state["repository"]
    branch = state["default_branch"]
    if state.get("mode") in ("pr_success", "pr_failure", "stale_cleanup", "closed_cleanup"):
        number = state["number"]
        pr = api_request("GET", f"pulls/{number}")
        base = pr.get("base") or {}
        if (base.get("ref") != branch or (base.get("repo") or {}).get("full_name", "").lower() != repository.lower()):
            state["action"] = "skip"
            state["comment"] = False
        elif state["mode"] in ("pr_success", "pr_failure"):
            head = pr.get("head") or {}
            head_repo = (head.get("repo") or {}).get("full_name")
            expected_repo = state.get("current_head_repository")
            repo_matches = (head_repo.lower() == expected_repo.lower()) if head_repo and expected_repo else \
                (head_repo is None and expected_repo is None and not state.get("published"))
            if pr.get("state") != "open" or head.get("sha") != state.get("source_sha") or not repo_matches:
                state["action"] = "skip"
                state["comment"] = False
        elif state["mode"] == "stale_cleanup":
            head = pr.get("head") or {}
            if pr.get("state") != "open" or head.get("sha") != state.get("current_head_sha") or \
                    (head.get("repo") or {}).get("full_name", "").lower() != \
                    str(state.get("current_head_repository") or "").lower():
                state["action"] = "skip"
                state["comment"] = False
        elif pr.get("state") != "closed":
            state["action"] = "skip"
            state["comment"] = False
        if state.get("action") == "publish" and is_newer_preview(pages, number, state["run_id"]):
            state["action"] = "skip"
            state["comment"] = False
        if state.get("action") == "publish" and state.get("published"):
            target = state["target"]
            target_root = Path(state["target_root"])
            bundle_root = Path(state["bundle_root"])
            target_run = read_json(contained_path(target_root, "target.json"))
            validate_target(target_root, {"target.json"}, {
                "id": state["run_id"], "run_attempt": state["run_attempt"], "event": "pull_request",
                "head_branch": target["branch"],
            }, repository, branch, state["simulator_sha"])
            names = {path.relative_to(bundle_root).as_posix() for path in bundle_root.rglob("*") if path.is_file()}
            validate_browser_bundle(bundle_root, names, target_run, state["simulator_sha"])
    elif state.get("mode") == "default":
        if current_default_sha(branch) != state.get("source_sha"):
            state["action"] = "skip"
        elif state.get("published"):
            target_root = Path(state["target_root"])
            bundle_root = Path(state["bundle_root"])
            target = read_json(contained_path(target_root, "target.json"))
            run_stub = {"id": state["run_id"], "run_attempt": state["run_attempt"],
                        "event": "push", "head_branch": branch}
            validate_target(target_root, {"target.json"}, run_stub, repository, branch, state["simulator_sha"])
            names = {path.relative_to(bundle_root).as_posix() for path in bundle_root.rglob("*") if path.is_file()}
            validate_browser_bundle(bundle_root, names, target, state["simulator_sha"])
    if state.get("action") == "publish":
        state["deploy"] = has_site(pages)
    save_state(Path(args.state), state)
    return state


def stage(args) -> bool:
    state = read_json(Path(args.state))
    if state.get("action") != "publish" or not state.get("deploy"):
        return False
    pages = Path(args.pages)
    validate_tree_no_symlinks(pages)
    output = Path(args.output)
    require(not output.exists() and not output.is_symlink(), "Pages staging directory already exists")
    output.mkdir(parents=True)
    for source in walk_files_no_symlinks(pages):
        relative = source.relative_to(pages)
        if relative.parts and relative.parts[0] == ".git":
            continue
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as handle:
            handle.write("deploy=true\n")
    return True


def comment_body(state: dict, deployed: bool) -> str:
    number = state["number"]
    sha = state["source_sha"]
    run_url = state["run_url"]
    if deployed and state.get("published"):
        repo = state["repository"]
        owner, name = repo.split("/", 1)
        preview_url = f"https://{owner.lower()}.github.io/{name}/pr/{number}/"
        simulator = state["simulator"]
        return (
            f"{COMMENT_MARKER}\n🧪 **Specter browser preview** · `{sha[:7]}` ✅\n\n"
            f"🖥️ [Open preview]({preview_url})\n\n"
            f"**Specter source:** `{state['source_repository']}@{sha[:12]}`  \n"
            f"**Web Simulator:** `{simulator['repository']}@{simulator['commit'][:12]}`  \n"
            f"[Build logs]({run_url})\n\n"
            "⚠️ Experimental development build. Never use real funds or enter a real seed phrase."
        )
    return (
        f"{COMMENT_MARKER}\n🧪 **Specter browser preview** · `{sha[:7]}` ❌\n\n"
        "No current browser preview is available for this PR commit. Any earlier preview has been removed. "
        f"[Inspect the build and publishing logs]({run_url})."
    )


def update_comment(args) -> None:
    state = read_json(Path(args.state))
    if not state.get("comment") or type(state.get("number")) is not int:
        return
    pr = api_request("GET", f"pulls/{state['number']}")
    head = pr.get("head") or {}
    head_repo = (head.get("repo") or {}).get("full_name") or ""
    expected_repo = state.get("current_head_repository") or state.get("source_repository", "")
    repo_matches = head_repo.lower() == expected_repo.lower() if head_repo else \
        state.get("current_head_repository") is None and not state.get("published")
    if pr.get("state") != "open" or head.get("sha") != state.get("source_sha") or not repo_matches:
        return
    deployed = os.environ.get("PAGES_DEPLOYED", "false").lower() == "true"
    body = comment_body(state, deployed)
    existing = []
    for page in range(1, 11):
        batch = api_request("GET", f"issues/{state['number']}/comments?per_page=100&page={page}")
        existing.extend(batch)
        if len(batch) < 100:
            break
    bot_comments = [entry for entry in existing if COMMENT_MARKER in entry.get("body", "") and
                    (entry.get("user") or {}).get("login") == "github-actions[bot]"]
    if bot_comments:
        primary = min(bot_comments, key=lambda item: item["id"])
        api_request("PATCH", f"issues/comments/{primary['id']}", {"body": body})
        for duplicate in bot_comments:
            if duplicate["id"] != primary["id"]:
                api_request("DELETE", f"issues/comments/{duplicate['id']}")
    else:
        api_request("POST", f"issues/{state['number']}/comments", {"body": body})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "recheck", "stage", "comment"))
    parser.add_argument("--event", type=Path)
    parser.add_argument("--pages", type=Path, default=Path("pages"))
    parser.add_argument("--trusted-web", type=Path, default=Path("simulator-tools/web"))
    parser.add_argument("--artifacts-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--simulator-sha", default=SIMULATOR_PIN)
    parser.add_argument("--output", type=Path, default=Path("site-dist"))
    args = parser.parse_args()
    if args.phase == "prepare":
        require(args.event is not None, "--event is required")
        prepare(args)
    elif args.phase == "recheck":
        recheck(args)
    elif args.phase == "stage":
        args.result = stage(args)
    elif args.phase == "comment":
        update_comment(args)


if __name__ == "__main__":
    main()
