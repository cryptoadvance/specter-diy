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
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("GitHub API request failed")


def comment(repo, number, token, text):
    path = f"/repos/{repo}/issues/{number}/comments"
    comments = gh("GET", path + "?per_page=100", token)
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


def current(repo, number, action, sha, token):
    try:
        pr = gh("GET", f"/repos/{repo}/pulls/{number}", token)
    except RuntimeError:
        return None
    return (pr.get("state") == "closed" if action == "delete" else pr.get("state") == "open") and \
        pr.get("head", {}).get("sha") == sha


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


def main():
    base = os.environ["BASE_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", base):
        raise ValueError("invalid base repository")
    number, sha, action = int(os.environ["PR_NUMBER"]), os.environ["HEAD_SHA"], os.environ["ACTION"]
    if not re.fullmatch(r"[a-f0-9]{40}", sha) or action not in ("build", "delete"):
        raise ValueError("invalid PR metadata")
    owner = base.split("/", 1)[0]
    simulator = os.environ.get("WEB_SIMULATOR_REPOSITORY", "").strip() or f"{owner}/specter-diy-web-simulator"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", simulator):
        raise ValueError("invalid paired repository")
    token = os.environ["GITHUB_TOKEN"]
    short = sha[:7]
    request_id = f"specter-pr-{number}-{sha}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    root = pages_root(simulator)
    preview, status_url = root + f"pr/{number}/", root + f"status/pr/{number}.json"
    if not os.environ.get("WEB_SIMULATOR_DISPATCH_TOKEN"):
        comment(base, number, token, f"🧪 Specter PR Build · {short} ⚠️\n\nConfigure the paired Web Simulator and `WEB_SIMULATOR_DISPATCH_TOKEN` secret.")
        return
    try:
        service = gh("GET", f"/repos/{simulator}")
        inputs = {"request_id": request_id, "action": action, "base_repository": base,
                  "pr_number": str(number), "head_repository": os.environ.get("HEAD_REPOSITORY", ""),
                  "head_sha": sha, "head_ref": os.environ.get("HEAD_REF", ""),
                  "source_updated_at": os.environ["SOURCE_UPDATED_AT"]}
        gh("POST", f"/repos/{simulator}/actions/workflows/preview.yml/dispatches",
           os.environ["WEB_SIMULATOR_DISPATCH_TOKEN"], {"ref": service["default_branch"], "inputs": inputs})
    except (RuntimeError, KeyError) as exc:
        comment(base, number, token, f"🧪 Specter PR Build · {short} ⚠️\n\nThe paired Web Simulator could not start ({type(exc).__name__}). Check Actions settings and the secret's Actions: write permission.")
        return

    note = "Removing the preview for this closed PR." if action == "delete" else "Browser simulator and firmware are being built."
    comment(base, number, token, f"🧪 Specter PR Build · {short} ⏳\n\n{note}\n\nSource commit: `{short}`")
    deadline, delay = monotonic() + 55 * 60, 10
    while monotonic() < deadline:
        if current(base, number, action, sha, token) is False:
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
            if current(base, number, action, sha, token) is not False:
                comment(base, number, token, text)
            return
        sleep(min(delay, max(0, deadline - monotonic())))
        delay = min(60, int(delay * 1.5))
    if current(base, number, action, sha, token) is not False:
        comment(base, number, token, f"🧪 Specter PR Build · {short} ⚠️\n\nThe remote Web Simulator did not return a matching result in time. Check its Actions page or rerun the preview.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Browser preview dispatcher failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
