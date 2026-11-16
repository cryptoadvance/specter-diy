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


# GitHub author_association reflects prior contributions to this repository.
# A first-time contributor requires a PR-specific maintainer approval comment.
TRUSTED_ASSOCIATIONS = frozenset(("OWNER", "MEMBER", "COLLABORATOR", "CONTRIBUTOR"))
APPROVAL_COMMAND = "/build preview"
LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}\Z")


def has_write_access(repository, username, token):
    """Use actual repository access, not user-controlled comment text or labels."""
    if not isinstance(username, str) or not LOGIN_RE.fullmatch(username):
        return False
    result = gh("GET", f"/repos/{repository}/collaborators/{username}/permission", token)
    # GitHub maps the maintain role to the legacy 'write' permission.
    return isinstance(result, dict) and result.get("permission") in ("write", "admin")


def is_maintainer_approval(repository, number, comment, token):
    if not isinstance(comment, dict):
        return False
    expected_issue_url = f"{API}/repos/{repository}/issues/{number}"
    if comment.get("issue_url") != expected_issue_url:
        return False
    if (comment.get("body") or "").strip() != APPROVAL_COMMAND:
        return False
    login = (comment.get("user") or {}).get("login")
    return has_write_access(repository, login, token)


def previously_approved(repository, number, token):
    """An approval applies to the entire PR, including future head commits.

    The comment remains the source of truth. Editing/deleting it or revoking the
    maintainer's write access prevents further automatic builds.
    """
    for page in range(1, 21):
        comments = gh("GET", f"/repos/{repository}/issues/{number}/comments?per_page=100&page={page}", token)
        if not isinstance(comments, list):
            return False
        for comment in comments:
            if is_maintainer_approval(repository, number, comment, token):
                return True
        if len(comments) < 100:
            return False
    # Fail closed if a PR has more than 2,000 comments.
    return False


def request_environment_for_comment(env, pr):
    """Supply the exact live PR fields absent from issue_comment events."""
    base = pr.get("base") or {}
    head = pr.get("head") or {}
    result = dict(env)
    result.update({
        "BASE_SHA": base.get("sha", ""),
        "BASE_REF": base.get("ref", ""),
        "HEAD_SHA": head.get("sha", ""),
        "HEAD_REF": head.get("ref", ""),
        "HEAD_REPOSITORY": (head.get("repo") or {}).get("full_name", ""),
        "SOURCE_UPDATED_AT": pr.get("updated_at", ""),
    })
    return result


def approval_event_valid(env, token):
    """Only a live, exact maintainer command on this PR may initiate a build."""
    repository = env["BASE_REPOSITORY"]
    if not REPOSITORY_RE.fullmatch(repository) or repository.rsplit("/", 1)[1].lower() != "specter-diy":
        raise ValueError("invalid Specter base repository")
    number = int(env["PR_NUMBER"])
    comment_id = int(env["COMMENT_ID"])
    if not 1 <= number <= 9999999 or comment_id <= 0:
        raise ValueError("invalid PR or comment identity")
    if env["ACTION"] != "build":
        return False
    comment = gh("GET", f"/repos/{repository}/issues/comments/{comment_id}", token)
    return is_maintainer_approval(repository, number, comment, token)


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
    env = dict(os.environ)
    token = env["GITHUB_TOKEN"]
    event_name = env.get("EVENT_NAME", "pull_request_target")
    if event_name not in ("pull_request_target", "issue_comment"):
        return

    if event_name == "issue_comment":
        if not approval_event_valid(env, token):
            return
        repository = env["BASE_REPOSITORY"]
        pr = gh("GET", f"/repos/{repository}/pulls/{int(env['PR_NUMBER'])}", token)
        env = request_environment_for_comment(env, pr)
    else:
        # Reject malformed event metadata before constructing API paths.
        request = request_from_environment(env)
        pr = gh("GET", f"/repos/{request['base_repository']}/pulls/{request['pr_number']}", token)

    request = request_from_environment(env)
    if not current(request, token, lambda *_: pr):
        return

    if request["action"] == "build" and event_name != "issue_comment":
        author_association = pr.get("author_association")
        trusted_author = author_association in TRUSTED_ASSOCIATIONS
        if not trusted_author and not previously_approved(
                request["base_repository"], request["pr_number"], token):
            return

    simulator = env.get("WEB_SIMULATOR_REPOSITORY", "").strip()
    if not simulator:
        simulator = f"{request['base_repository'].split('/', 1)[0]}/specter-diy-web-simulator"
    dispatch(request, simulator, env["WEB_SIMULATOR_DISPATCH_TOKEN"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Browser preview dispatcher failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
