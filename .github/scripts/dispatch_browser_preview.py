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
        if (pr.get("state") != "open" or pr.get("draft") is True or base.get("sha") != request["base_sha"] or
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
ONCE_COMMAND = "/build"
AUTO_COMMAND = "/build-auto"
LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}\Z")
CI_WORKFLOW = ".github/workflows/test.yml"
SIMULATOR_WORKFLOW = "preview.yml"
APPROVAL_WORKFLOW = "approval.yml"
AUTO_MODE_WORKFLOW = "auto-mode.yml"
SIMULATOR_WORKFLOW_INPUTS = (
    "request_id",
    "action",
    "base_repository",
    "base_sha",
    "base_ref",
    "pr_number",
    "head_repository",
    "head_sha",
    "head_ref",
    "source_updated_at",
)
APPROVAL_WORKFLOW_INPUTS = ("pr_number", "head_sha", "source_updated_at")


def has_write_access(repository, username, token):
    """Never trust comment text, author_association, or an unchecked username."""
    if not isinstance(username, str) or not LOGIN_RE.fullmatch(username):
        return False
    try:
        permission = gh("GET", f"/repos/{repository}/collaborators/{username}/permission", token)
    except RuntimeError as exc:
        # GitHub returns 404 when the commenter is not a collaborator.
        if "HTTP 404" in str(exc):
            return False
        raise
    return isinstance(permission, dict) and permission.get("permission") in (
        "write", "maintain", "admin"
    )


def is_maintainer_command(repository, number, comment, token):
    if not isinstance(comment, dict):
        return False
    if comment.get("issue_url") != f"{API}/repos/{repository}/issues/{number}":
        return False
    command = (comment.get("body") or "").strip().lower()
    if command not in (ONCE_COMMAND, AUTO_COMMAND):
        return False
    if command == AUTO_COMMAND:
        # Edited comments must not silently turn into durable approvals.
        created, updated = comment.get("created_at"), comment.get("updated_at")
        if not created or not updated or parse_time(created) != parse_time(updated):
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
    if not is_maintainer_command(repository, number, comment, token):
        return None
    return (comment.get("body") or "").strip().lower()


def _issue_open_epoch(repository, number, pr, token):
    """Read the latest reopen event directly rather than scanning the timeline."""
    owner, name = repository.split("/", 1)
    query = """query($owner:String!,$name:String!,$number:Int!) {
      repository(owner:$owner,name:$name) { pullRequest(number:$number) {
        state timelineItems(last:1,itemTypes:[REOPENED_EVENT]) {
          nodes { ... on ReopenedEvent { createdAt } } } } } }"""
    result = gh("POST", "/graphql", token, {"query": query, "variables": {
        "owner": owner, "name": name, "number": number}})
    if not isinstance(result, dict) or result.get("errors"):
        raise ValueError("cannot verify PR open period")
    try:
        live = result["data"]["repository"]["pullRequest"]
        if live["state"] != "OPEN":
            raise ValueError("PR no longer open")
        events = live["timelineItems"]["nodes"]
        if len(events) > 1:
            raise ValueError("invalid reopen history")
        epoch = parse_time(pr["created_at"])
        return max(epoch, parse_time(events[0]["createdAt"])) if events else epoch
    except (TypeError, KeyError) as exc:
        raise ValueError("invalid reopen history") from exc


def auto_build_status(repository, number, pr, token, bot_login="specter-preview-bot"):
    """Find the bot's card, then independently verify the original command."""
    if pr.get("state") != "open":
        return False, None
    if not isinstance(bot_login, str) or not LOGIN_RE.fullmatch(bot_login):
        raise ValueError("invalid configured preview bot login")
    query = """query($login:String!,$cursor:String) { user(login:$login) {
      issueComments(first:100,after:$cursor) { pageInfo { hasNextPage endCursor }
        nodes { body issue { number repository { nameWithOwner } } } } } }"""
    cursor = None
    for _ in range(100):
        result = gh("POST", "/graphql", token, {"query": query, "variables": {
            "login": bot_login, "cursor": cursor}})
        if not isinstance(result, dict) or result.get("errors"):
            raise ValueError("cannot inspect bot comments")
        try:
            page = result["data"]["user"]["issueComments"]
            for item in page["nodes"]:
                if not isinstance(item, dict) or not isinstance(item.get("issue"), dict):
                    continue
                issue = item["issue"]
                body = item.get("body")
                if not isinstance(body, str):
                    continue
                if (issue["number"] != number or issue["repository"]["nameWithOwner"].lower() != repository.lower()
                        or "<!-- specter-web-simulator-preview -->" not in body):
                    continue
                markers = re.findall(r"<!-- specter-auto-mode:([1-9][0-9]*) -->", body)
                if len(markers) != 1:
                    return False, None
                comment_id = int(markers[0])
                try:
                    comment = gh("GET", f"/repos/{repository}/issues/comments/{comment_id}", token)
                except RuntimeError as exc:
                    if "HTTP 404" in str(exc):
                        return False, comment_id
                    raise
                if (not isinstance(comment, dict) or (comment.get("body") or "").strip().lower() != AUTO_COMMAND
                        or not is_maintainer_command(repository, number, comment, token)):
                    return False, comment_id
                if parse_time(comment["created_at"]) <= _issue_open_epoch(repository, number, pr, token):
                    return False, comment_id
                return True, comment_id
            info = page["pageInfo"]
            if not info["hasNextPage"]:
                return False, None
            next_cursor = info["endCursor"]
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
                raise ValueError("invalid bot comment pagination")
            cursor = next_cursor
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid bot comments response") from exc
    raise ValueError("bot comment lookup exceeded its page limit")


def auto_build_approved(repository, number, pr, token):
    return auto_build_status(repository, number, pr, token)[0]


def dispatch_to_service(request, simulator, token, workflow=SIMULATOR_WORKFLOW):
    service = gh("GET", f"/repos/{simulator}", token)
    branch = service.get("default_branch") if isinstance(service, dict) else None
    if not isinstance(branch, str) or not valid_ref(branch):
        raise RuntimeError("Web Simulator has no valid default branch")
    if workflow == SIMULATOR_WORKFLOW:
        inputs = {key: str(request[key]) for key in SIMULATOR_WORKFLOW_INPUTS}
    elif workflow == APPROVAL_WORKFLOW:
        inputs = {key: str(request[key]) for key in APPROVAL_WORKFLOW_INPUTS}
    elif workflow == AUTO_MODE_WORKFLOW:
        inputs = {key: str(request[key]) for key in ("pr_number", "comment_id", "action")}
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
            not (run.get("path") == CI_WORKFLOW or
                 str(run.get("path", "")).startswith(CI_WORKFLOW + "@"))):
        return None
    if run.get("status") not in ("queued", "in_progress") and not (
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

    bot_login = env.get("SPECTER_PREVIEW_BOT_LOGIN", "").strip() or "specter-preview-bot"
    action = "build"
    invalid_auto_comment = None
    if event_name == "issue_comment":
        command = comment_command_valid(env, token)
        if command is None:
            return
        number = int(env["PR_NUMBER"])
        pr = gh("GET", f"/repos/{repository}/pulls/{number}", token)
    elif event_name == "workflow_run":
        checked = approved_ci_pr(env, token)
        if checked is None:
            return
        number, pr = checked
        # The pull_request_target synchronize event owns builds for auto-approved
        # PRs. Avoid dispatching the same SHA again when native CI also starts.
        approved, invalid_auto_comment = auto_build_status(repository, number, pr, token, bot_login)
        if approved:
            return
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
    if not current(request, token):
        return

    simulator = env.get("WEB_SIMULATOR_REPOSITORY", "").strip()
    if not simulator:
        simulator = f"{repository.split('/', 1)[0]}/specter-diy-web-simulator"
    # Reuse the existing same-owner guard from request_from_environment().
    dispatch_token = env["WEB_SIMULATOR_DISPATCH_TOKEN"]
    if event_name == "issue_comment" and command == AUTO_COMMAND:
        dispatch_to_service({"pr_number": number, "comment_id": env["COMMENT_ID"], "action": "set"},
                            simulator, dispatch_token, AUTO_MODE_WORKFLOW)
    if event_name == "workflow_run" and invalid_auto_comment:
        dispatch_to_service({"pr_number": number, "comment_id": invalid_auto_comment, "action": "clear"},
                            simulator, dispatch_token, AUTO_MODE_WORKFLOW)
    if event_name == "pull_request_target" and action == "build":
        approved, comment_id = (False, None)
        if env.get("GITHUB_EVENT_ACTION") == "synchronize":
            approved, comment_id = auto_build_status(repository, number, pr, token, bot_login)
        if comment_id and not approved:
            dispatch_to_service({"pr_number": number, "comment_id": comment_id, "action": "clear"},
                                simulator, dispatch_token, AUTO_MODE_WORKFLOW)
        if approved:
            # Subsequent commits are trusted only for the *current* open epoch.
            dispatch_to_service(request, simulator, dispatch_token)
        else:
            # The reporter checks for a genuine native GitHub approval request.
            dispatch_to_service(request, simulator, dispatch_token, APPROVAL_WORKFLOW)
    else:
        # /build and /build-auto both explicitly launch this SHA once.
        dispatch_to_service(request, simulator, dispatch_token)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Browser preview dispatcher failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
