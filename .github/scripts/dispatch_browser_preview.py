#!/usr/bin/env python3
"""Dispatch exact PR metadata and maintain its single preview comment."""
from time import monotonic, sleep, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import os
import re
import sys

API = "https://api.github.com"
MARKER = "<!-- specter-web-simulator-preview -->"

# Keep these values in sync with the paired Web Simulator workflow. Its
# critical path is validate + max(build, trusted_runtime) + verify + finalize.
# Current limits total 315m; polling adds 15m, and the caller has 30m more.
REMOTE_VALIDATE_TIMEOUT_MINUTES = 5
REMOTE_BUILD_TIMEOUT_MINUTES = 180
REMOTE_RUNTIME_TIMEOUT_MINUTES = 180
REMOTE_VERIFY_TIMEOUT_MINUTES = 120
REMOTE_FINALIZE_TIMEOUT_MINUTES = 10
REMOTE_SCHEDULING_ALLOWANCE_MINUTES = 15
REMOTE_CHAIN_TIMEOUT_MINUTES = (
    REMOTE_VALIDATE_TIMEOUT_MINUTES
    + max(REMOTE_BUILD_TIMEOUT_MINUTES, REMOTE_RUNTIME_TIMEOUT_MINUTES)
    + REMOTE_VERIFY_TIMEOUT_MINUTES
    + REMOTE_FINALIZE_TIMEOUT_MINUTES
)
POLL_TIMEOUT_MINUTES = REMOTE_CHAIN_TIMEOUT_MINUTES + REMOTE_SCHEDULING_ALLOWANCE_MINUTES
CALLER_WORKFLOW_TIMEOUT_MINUTES = 360


def gh(method, path, token="", data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "specter-preview"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = json.dumps(data).encode() if data is not None else None
    if raw:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(API + path, data=raw, headers=headers, method=method), timeout=25) as response:
            result = response.read()
            return json.loads(result) if result else None
    except HTTPError as exc:
        endpoint = path.split("?", 1)[0]
        message = ""
        try:
            payload = json.loads(exc.read(4096))
            if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                message = re.sub(r"[^A-Za-z0-9 .,:'/_-]", "", payload["message"])[:180]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        detail = f": {message}" if message else ""
        raise RuntimeError(
            f"GitHub API {method} {endpoint} returned HTTP {exc.code}{detail}"
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("GitHub API request failed")


def list_comments(repo, number, token):
    """Fetch every issue-comment page so the bot comment stays unique."""
    path = f"/repos/{repo}/issues/{number}/comments"
    comments = []
    page = 1
    while True:
        batch = gh("GET", path + "?" + urlencode({"per_page": 100, "page": page}), token)
        if not isinstance(batch, list):
            raise RuntimeError("GitHub returned an invalid issue-comment page")
        comments.extend(batch)
        if len(batch) < 100:
            return comments
        page += 1


def comment(repo, number, token, text):
    path = f"/repos/{repo}/issues/{number}/comments"
    comments = list_comments(repo, number, token)
    found = [c for c in comments if MARKER in c.get("body", "") and
             c.get("user", {}).get("login") == "github-actions[bot]"]
    body = {"body": f"{text}\n\n{MARKER}"}
    if found:
        gh("PATCH", f"/repos/{repo}/issues/comments/{found[0]['id']}", token, body)
        for duplicate in found[1:]:
            gh("DELETE", f"/repos/{repo}/issues/comments/{duplicate['id']}", token)
    else:
        gh("POST", path, token, body)


def pages_root(repo):
    owner, name = repo.split("/", 1)
    host = owner.lower() + ".github.io"
    return f"https://{host}/" + ("" if name.lower() == host else f"{name}/")


def comment_auth_token(workflow_token):
    """Use a fork-specific comment token when configured; otherwise GITHUB_TOKEN."""
    return os.environ.get("SPECTER_PREVIEW_COMMENT_TOKEN", "").strip() or workflow_token


def current(repo, number, action, sha, token, base_sha=None, base_ref=None):
    try:
        pr = gh("GET", f"/repos/{repo}/pulls/{number}", token)
    except RuntimeError:
        return None
    return ((pr.get("state") == "closed" if action == "delete" else pr.get("state") == "open") and
            pr.get("head", {}).get("sha") == sha and
            (action == "delete" or base_sha is None or pr.get("base", {}).get("sha") == base_sha) and
            (action == "delete" or base_ref is None or pr.get("base", {}).get("ref") == base_ref))


def result_text(status, short_sha, preview, simulator):
    repo = re.escape(simulator)
    run = status.get("run_url", "")
    if not re.fullmatch(rf"https://github\.com/{repo}/actions/runs/[1-9][0-9]*", run):
        raise ValueError("invalid run URL")
    if status["status"] == "success":
        page, firmware = status.get("preview_url", ""), status.get("firmware_url", "")
        if page != preview or not re.fullmatch(
                rf"https://github\.com/{repo}/actions/runs/[1-9][0-9]*/artifacts/[1-9][0-9]*", firmware):
            raise ValueError("invalid result URL")
        return (f"🧪 Specter PR Build · {short_sha} ✅\n\n🖥️ [Open browser simulator]({page})\n\n"
                f"⬇️ [Download firmware artifact]({firmware})\n\nSource commit: `{short_sha}`\n\n"
                f"🔧 [Build logs]({run})\n\n⚠️ Experimental development build. Never enter a real seed phrase or use real funds.")
    if status["status"] in ("failure", "cancelled"):
        return (f"🧪 Specter PR Build · {short_sha} ❌\n\nNo browser preview is available for the current commit.\n\n"
                f"Source commit: `{short_sha}`\n\n🔧 [Build logs]({run})")
    if status["status"] == "deleted":
        return f"🧪 Specter PR Build · {short_sha} 🗑️\n\nPreview removed because this PR was closed."
    raise ValueError("unsupported status")


def _comment_if_current(repo, number, action, sha, token, text, base_sha=None, base_ref=None,
                        comment_token=None):
    if current(repo, number, action, sha, token, base_sha, base_ref) is True:
        comment(repo, number, comment_token or token, text)
        return True
    return False


def main():
    base = os.environ["BASE_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", base):
        raise ValueError("invalid base repository")
    number, sha, action = int(os.environ["PR_NUMBER"]), os.environ["HEAD_SHA"], os.environ["ACTION"]
    base_sha, base_ref = os.environ["BASE_SHA"], os.environ["BASE_REF"]
    if (not re.fullmatch(r"[a-f0-9]{40}", sha) or
            not re.fullmatch(r"[a-f0-9]{40}", base_sha) or
            not base_ref or len(base_ref) > 255 or
            action not in ("build", "delete")):
        raise ValueError("invalid PR metadata")
    owner = base.split("/", 1)[0]
    simulator = os.environ.get("WEB_SIMULATOR_REPOSITORY", "").strip() or f"{owner}/specter-diy-web-simulator"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", simulator):
        raise ValueError("invalid paired repository")
    token = os.environ["GITHUB_TOKEN"]
    comment_token = comment_auth_token(token)
    short = sha[:7]
    request_id = f"specter-pr-{number}-{sha}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    root = pages_root(simulator)
    preview, status_url = root + f"pr/{number}/", root + f"status/pr/{number}.json"

    # A failed metadata lookup (None) must never authorize a status comment or
    # a privileged remote dispatch. Fork and same-repository PRs follow the
    # same verified path; the build job remains isolated from repository writes.
    if current(base, number, action, sha, token, base_sha, base_ref) is not True:
        return

    if not os.environ.get("WEB_SIMULATOR_DISPATCH_TOKEN"):
        _comment_if_current(
            base, number, action, sha, token,
            f"🧪 Specter PR Build · {short} ⚠️\n\nConfigure the paired Web Simulator and `WEB_SIMULATOR_DISPATCH_TOKEN` secret.",
            base_sha, base_ref, comment_token=comment_token)
        return
    try:
        service = gh("GET", f"/repos/{simulator}")
        inputs = {"request_id": request_id, "action": action, "base_repository": base,
                  "base_sha": base_sha, "base_ref": base_ref,
                  "pr_number": str(number), "head_repository": os.environ.get("HEAD_REPOSITORY", ""),
                  "head_sha": sha, "head_ref": os.environ.get("HEAD_REF", ""),
                  "source_updated_at": os.environ["SOURCE_UPDATED_AT"]}
        gh("POST", f"/repos/{simulator}/actions/workflows/preview.yml/dispatches",
           os.environ["WEB_SIMULATOR_DISPATCH_TOKEN"], {"ref": service["default_branch"], "inputs": inputs})
    except (RuntimeError, KeyError) as exc:
        _comment_if_current(
            base, number, action, sha, token,
            f"🧪 Specter PR Build · {short} ⚠️\n\nThe paired Web Simulator could not start ({type(exc).__name__}). Check Actions settings and the secret's Actions: write permission.",
            base_sha, base_ref, comment_token=comment_token)
        return

    note = "Removing the preview for this closed PR." if action == "delete" else "Browser simulator and firmware are being built."
    _comment_if_current(base, number, action, sha, token,
                        f"🧪 Specter PR Build · {short} ⏳\n\n{note}\n\nSource commit: `{short}`",
                        base_sha, base_ref, comment_token=comment_token)
    deadline, delay = monotonic() + POLL_TIMEOUT_MINUTES * 60, 10
    while monotonic() < deadline:
        state = current(base, number, action, sha, token, base_sha, base_ref)
        if state is False:
            return
        url = status_url + "?" + urlencode({"request_id": request_id, "poll": int(time())})
        try:
            with urlopen(Request(url, headers={"Cache-Control": "no-cache"}), timeout=20) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            result = None
        if (isinstance(result, dict) and result.get("request_id") == request_id and
                result.get("source_sha") == sha and result.get("pr_number") == number):
            try:
                text = result_text(result, short, preview, simulator)
            except (ValueError, KeyError):
                text = f"🧪 Specter PR Build · {short} ⚠️\n\nThe Web Simulator returned an invalid result link."
            state = current(base, number, action, sha, token, base_sha, base_ref)
            if state is False:
                return
            if state is True:
                comment(base, number, comment_token, text)
                return
            # An API error is unknown, not proof that this result is current.
            # Keep polling and retry verification instead of writing a comment.
        sleep(min(delay, max(0, deadline - monotonic())))
        delay = min(60, int(delay * 1.5))
    _comment_if_current(
        base, number, action, sha, token,
        f"🧪 Specter PR Build · {short} ⚠️\n\nThe remote Web Simulator did not return a matching result in time. Check its Actions page or rerun the preview.",
        base_sha, base_ref, comment_token=comment_token)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Browser preview dispatcher failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
