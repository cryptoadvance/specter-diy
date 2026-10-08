#!/usr/bin/env python3
"""Validate a live Specter PR and dispatch its exact preview request."""
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os
import re
import sys


API = "https://api.github.com"
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SHA_RE = re.compile(r"[a-f0-9]{40}\Z")


def gh(method, path, token, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "specter-preview"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = json.dumps(data).encode() if data is not None else None
    if raw is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(API + path, data=raw, headers=headers, method=method), timeout=25) as response:
            result = response.read()
            return json.loads(result) if result else None
    except HTTPError as exc:
        raise RuntimeError(f"GitHub API {method} {path.split('?', 1)[0]} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub API request failed") from exc


def parse_time(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("source_updated_at must be an RFC3339 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("source_updated_at must be an RFC3339 timestamp") from exc
    if result.tzinfo is None:
        raise ValueError("source_updated_at must include a timezone")
    return result.astimezone(timezone.utc)


def valid_ref(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 255 or
            value.startswith(("/", ".")) or value.endswith(("/", ".", ".lock"))):
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    if any(part in value for part in ("..", "//", "@{", "\\", " ", "~", "^", ":", "?", "*", "[")):
        return False
    return all(part and not part.startswith(".") and not part.endswith(".lock")
               for part in value.split("/"))


def request_from_environment(env):
    base = env["BASE_REPOSITORY"]
    simulator = env.get("WEB_SIMULATOR_REPOSITORY", "").strip()
    if not simulator and REPOSITORY_RE.fullmatch(base):
        simulator = f"{base.split('/', 1)[0]}/specter-diy-web-simulator"
    action = env["ACTION"]
    try:
        number = int(env["PR_NUMBER"])
        run_id = int(env["GITHUB_RUN_ID"])
        run_attempt = int(env["GITHUB_RUN_ATTEMPT"])
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid PR or workflow run identity") from exc

    head_repository = env.get("HEAD_REPOSITORY", "")
    head_ref = env.get("HEAD_REF", "")
    head_sha = env["HEAD_SHA"]
    base_sha = env["BASE_SHA"]
    base_ref = env["BASE_REF"]
    source_updated_at = env["SOURCE_UPDATED_AT"]

    if not REPOSITORY_RE.fullmatch(base) or base.rsplit("/", 1)[1].lower() != "specter-diy":
        raise ValueError("invalid Specter base repository")
    if (not REPOSITORY_RE.fullmatch(simulator) or
            simulator.split("/", 1)[0].lower() != base.split("/", 1)[0].lower()):
        raise ValueError("invalid paired Web Simulator repository")
    if not 1 <= number <= 9999999 or run_id <= 0 or run_attempt <= 0:
        raise ValueError("invalid PR or workflow run identity")
    if action not in ("build", "delete"):
        raise ValueError("invalid preview action")
    if not SHA_RE.fullmatch(head_sha) or not SHA_RE.fullmatch(base_sha):
        raise ValueError("invalid full PR SHA")
    if not valid_ref(base_ref):
        raise ValueError("invalid PR base ref")
    if action == "build":
        if (not REPOSITORY_RE.fullmatch(head_repository) or
                not valid_ref(head_ref)):
            raise ValueError("invalid PR head repository or ref")
    elif head_repository and not REPOSITORY_RE.fullmatch(head_repository):
        raise ValueError("invalid PR head repository")

    parse_time(source_updated_at)
    request_id = f"specter-pr-{number}-{head_sha}-{run_id}-{run_attempt}"
    return {
        "request_id": request_id,
        "action": action,
        "base_repository": base,
        "base_sha": base_sha,
        "base_ref": base_ref,
        "pr_number": number,
        "head_repository": head_repository,
        "head_sha": head_sha,
        "head_ref": head_ref,
        "source_updated_at": source_updated_at,
    }


def current(request, token, pull_fetcher=None):
    fetch = pull_fetcher or (lambda repo, number: gh(
        "GET", f"/repos/{repo}/pulls/{number}", token))
    pr = fetch(request["base_repository"], request["pr_number"])
    if int(pr.get("number", -1)) != request["pr_number"]:
        return False
    base, head = pr.get("base") or {}, pr.get("head") or {}
    base_repo = (base.get("repo") or {}).get("full_name", "")
    if base_repo.lower() != request["base_repository"].lower():
        return False
    if head.get("sha") != request["head_sha"]:
        return False
    if request["action"] == "build":
        if (pr.get("state") != "open" or base.get("sha") != request["base_sha"] or
                base.get("ref") != request["base_ref"]):
            return False
        if ((head.get("repo") or {}).get("full_name", "").lower() !=
                request["head_repository"].lower() or head.get("ref") != request["head_ref"]):
            return False
    else:
        if pr.get("state") != "closed":
            return False
        live_repository = (head.get("repo") or {}).get("full_name", "")
        if live_repository and request["head_repository"] and (
                live_repository.lower() != request["head_repository"].lower()):
            return False
    if parse_time(pr.get("updated_at", "")) < parse_time(request["source_updated_at"]):
        return False
    return True


def dispatch(request, simulator, token, github=None):
    github = github or gh
    service = github("GET", f"/repos/{simulator}", token)
    default_branch = service.get("default_branch") if isinstance(service, dict) else None
    if not isinstance(default_branch, str) or not valid_ref(default_branch):
        raise RuntimeError("Web Simulator repository has no valid default branch")
    inputs = {key: str(value) for key, value in request.items()}
    github("POST", f"/repos/{simulator}/actions/workflows/preview.yml/dispatches", token,
           {"ref": default_branch, "inputs": inputs})


def main():
    request = request_from_environment(os.environ)
    token = os.environ["GITHUB_TOKEN"]
    if not current(request, token):
        return
    simulator = os.environ.get("WEB_SIMULATOR_REPOSITORY", "").strip()
    if not simulator:
        simulator = f"{request['base_repository'].split('/', 1)[0]}/specter-diy-web-simulator"
    dispatch(request, simulator,
             os.environ["WEB_SIMULATOR_DISPATCH_TOKEN"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Browser preview dispatcher failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
