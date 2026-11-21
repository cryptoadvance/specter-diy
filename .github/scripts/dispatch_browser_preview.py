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


# Only an authenticated repository writer can manually run a build. Approving
# the native CI run uses GitHub's own workflow permission gate instead.
COMMAND = "/build"
LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}\Z")
CI_WORKFLOW = ".github/workflows/test.yml"
SIMULATOR_WORKFLOW = "preview.yml"
APPROVAL_WORKFLOW = "approval.yml"


def has_write_access(repository, username, token):
    """Never trust comment text, author_association, or an unchecked username."""
    if not isinstance(username, str) or not LOGIN_RE.fullmatch(username):
        return False
    permission = gh("GET", f"/repos/{repository}/collaborators/{username}/permission", token)
    return isinstance(permission, dict) and permission.get("permission") in (
        "write", "maintain", "admin"
    )


def is_maintainer_command(repository, number, comment, token):
    if not isinstance(comment, dict):
        return False
    if comment.get("issue_url") != f"{API}/repos/{repository}/issues/{number}":
        return False
    if (comment.get("body") or "").strip().lower() != COMMAND:
        return False
    return has_write_access(repository, (comment.get("user") or {}).get("login"), token)


def request_environment_for_pr(env, pr):
    """Reconstruct all PR fields from GitHub rather than an untrusted event."""
    base, head = pr.get("base") or {}, pr.get("head") or {}
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


def comment_command_valid(env, token):
    repository = env["BASE_REPOSITORY"]
    if not REPOSITORY_RE.fullmatch(repository) or repository.rsplit("/", 1)[1].lower() != "specter-diy":
        raise ValueError("invalid Specter repository")
    number, comment_id = int(env["PR_NUMBER"]), int(env["COMMENT_ID"])
    if not 1 <= number <= 9999999 or comment_id <= 0:
        raise ValueError("invalid PR/comment ID")
    comment = gh("GET", f"/repos/{repository}/issues/comments/{comment_id}", token)
    return is_maintainer_command(repository, number, comment, token)


def dispatch_to_service(request, simulator, token, workflow=SIMULATOR_WORKFLOW):
    service = gh("GET", f"/repos/{simulator}", token)
    branch = service.get("default_branch") if isinstance(service, dict) else None
    if not isinstance(branch, str) or not valid_ref(branch):
        raise RuntimeError("Web Simulator has no valid default branch")
    if workflow == SIMULATOR_WORKFLOW:
        inputs = {key: str(value) for key, value in request.items()}
    elif workflow == APPROVAL_WORKFLOW:
        inputs = {
            "pr_number": str(request["pr_number"]),
            "head_sha": request["head_sha"],
            "source_updated_at": request["source_updated_at"],
        }
    else:
        raise ValueError("unsupported service workflow")
    gh("POST", f"/repos/{simulator}/actions/workflows/{workflow}/dispatches", token,
       {"ref": branch, "inputs": inputs})


def find_pr_for_ci(repository, run, token):
    """Look up live open PRs; fork workflow_run.pull_requests can be empty."""
    sha = run.get("head_sha")
    head_repository = (run.get("head_repository") or {}).get("full_name", "")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        return None
    for page in range(1, 6):
        pulls = gh("GET", f"/repos/{repository}/pulls?state=open&per_page=100&page={page}", token)
        if not isinstance(pulls, list):
            raise ValueError("invalid pull request search result")
        for pr in pulls:
            head = pr.get("head") or {}
            if (head.get("sha") == sha and
                    (head.get("repo") or {}).get("full_name", "").lower() == head_repository.lower()):
                return pr
        if len(pulls) < 100:
            break
    return None


def approved_ci_pr(env, token):
    """Only a started native PR CI run authorizes automatic preview dispatch."""
    repository = env["BASE_REPOSITORY"]
    run_id = int(env["CI_RUN_ID"])
    if run_id <= 0:
        raise ValueError("invalid CI workflow ID")
    run = gh("GET", f"/repos/{repository}/actions/runs/{run_id}", token)
    if (not isinstance(run, dict) or run.get("id") != run_id or
            (run.get("repository") or {}).get("full_name", "").lower() != repository.lower() or
            run.get("name") != "CI" or run.get("event") != "pull_request" or
            not str(run.get("path", "")).startswith(CI_WORKFLOW + "@")):
        return None
    if run.get("status") != "in_progress" and not (
        run.get("status") == "completed" and
        run.get("conclusion") in ("success", "failure", "timed_out")
    ):
        return None
    pr = find_pr_for_ci(repository, run, token)
    if not pr or pr.get("state") != "open":
        return None
    number = pr.get("number")
    if type(number) is not int or number <= 0:
        return None
    return number, pr


def main():
    env = dict(os.environ)
    token = env["GITHUB_TOKEN"]
    event_name = env.get("EVENT_NAME", "")
    if event_name not in ("pull_request_target", "issue_comment", "workflow_run", "workflow_dispatch"):
        return
    repository = env["BASE_REPOSITORY"]
    if (not REPOSITORY_RE.fullmatch(repository) or
            repository.rsplit("/", 1)[1].lower() != "specter-diy"):
        raise ValueError("invalid Specter repository")

    action = "build"
    if event_name == "issue_comment":
        if not comment_command_valid(env, token):
            return
        number = int(env["PR_NUMBER"])
        pr = gh("GET", f"/repos/{repository}/pulls/{number}", token)
    elif event_name == "workflow_run":
        checked = approved_ci_pr(env, token)
        if checked is None:
            return
        number, pr = checked
    else:
        number = int(env["PR_NUMBER"])
        if event_name == "workflow_dispatch" and not has_write_access(
                repository, env.get("GITHUB_ACTOR", ""), token):
            return
        pr = gh("GET", f"/repos/{repository}/pulls/{number}", token)
        if event_name == "pull_request_target" and env.get("ACTION") == "delete":
            action = "delete"

    if not isinstance(pr, dict) or pr.get("number") != number:
        return
    env["PR_NUMBER"] = str(number)
    env["ACTION"] = action
    env = request_environment_for_pr(env, pr)
    request = request_from_environment(env)
    if not current(request, token, lambda *_: pr):
        return

    simulator = env.get("WEB_SIMULATOR_REPOSITORY", "").strip()
    if not simulator:
        simulator = f"{repository.split('/', 1)[0]}/specter-diy-web-simulator"
    # Reuse the existing same-owner guard from request_from_environment().
    dispatch_token = env["WEB_SIMULATOR_DISPATCH_TOKEN"]
    if event_name == "pull_request_target" and action == "build":
        # No untrusted PR code is run here. The simulator's trusted reporter
        # verifies a real action_required CI run before it writes the comment.
        dispatch_to_service(request, simulator, dispatch_token, APPROVAL_WORKFLOW)
    else:
        dispatch_to_service(request, simulator, dispatch_token)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Browser preview dispatcher failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
