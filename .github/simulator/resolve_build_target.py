#!/usr/bin/env python3
"""Resolve a Build run to one source commit before any build job starts."""
from urllib.request import Request, urlopen
from urllib.parse import quote
import json
import os
import re


def fetch_pull(repository: str, number: str, token: str) -> dict:
    request = Request(f"https://api.github.com/repos/{repository}/pulls/{number}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
    })
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_simulator_main(repository: str, token: str) -> str:
    request = Request(f"https://api.github.com/repos/{repository}/commits/main", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
    })
    with urlopen(request, timeout=30) as response:
        commit = json.load(response).get("sha")
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError(f"Simulator repository {repository} returned no valid main commit SHA")
    return commit


def fetch_open_pulls_for_head(repository: str, head_repository: str,
                              branch: str, token: str) -> list[dict]:
    owner = head_repository.split("/", 1)[0]
    head_filter = quote(f"{owner}:{branch}", safe="")
    pulls = []
    for page in range(1, 11):
        request = Request(
            f"https://api.github.com/repos/{repository}/pulls?state=open&head={head_filter}&per_page=100&page={page}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        with urlopen(request, timeout=30) as response:
            batch = json.load(response)
        pulls.extend(batch)
        if len(batch) < 100:
            break
    return pulls


def resolve(env, fetch=fetch_pull, fetch_main=fetch_simulator_main,
            fetch_head=fetch_open_pulls_for_head) -> dict:
    event = env["TARGET_EVENT"]
    number = str(env["TARGET_PR"]).strip(" \t")
    sha = env["TARGET_SHA"].strip(" \t")
    branch = env["TARGET_BRANCH"]
    repository = env["TARGET_REPOSITORY"]
    if event == "workflow_run":
        workflow_path = env["REQUEST_WORKFLOW_PATH"].split("@", 1)[0]
        head_repository = env["REQUEST_HEAD_REPOSITORY"]
        head_branch = env["REQUEST_HEAD_BRANCH"]
        request_sha = env["REQUEST_HEAD_SHA"]
        if workflow_path != ".github/workflows/pr-build-request.yml" or \
                env["REQUEST_EVENT"] != "pull_request" or \
                env["REQUEST_CONCLUSION"] != "success" or \
                not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", head_repository) or \
                not head_branch or not re.fullmatch(r"[a-f0-9]{40}", request_sha):
            raise ValueError("Unrecognized PR build request")
        candidates = fetch_head(env["GITHUB_REPOSITORY"], head_repository,
                                head_branch, env["GH_TOKEN"])
        matches = [pr for pr in candidates if pr.get("state") == "open" and
                   (pr.get("head", {}).get("repo") or {}).get("full_name", "").lower() == head_repository.lower() and
                   pr.get("head", {}).get("ref") == head_branch and
                   (pr.get("base", {}).get("repo") or {}).get("full_name", "").lower() == env["GITHUB_REPOSITORY"].lower() and
                   pr.get("base", {}).get("ref") == env["TARGET_DEFAULT_BRANCH"]]
        if len(matches) != 1:
            raise ValueError("PR request does not identify one open PR on the default branch")
        pr = matches[0]
        if pr["head"]["sha"] != request_sha:
            raise ValueError("PR request is stale")
        number = pr["number"]
        sha = pr["head"]["sha"]
        repository = pr["head"]["repo"]["full_name"]
        branch = pr["head"]["ref"]
    elif event == "workflow_dispatch":
        if not re.fullmatch(r"[a-f0-9]{7,40}", sha):
            raise ValueError("Expected a 7- to 40-character hexadecimal PR head SHA")
        if event == "workflow_dispatch" and env["GITHUB_REF"] != f"refs/heads/{env['TARGET_DEFAULT_BRANCH']}":
            raise ValueError("Manual PR builds must run from the default branch")
        if not re.fullmatch(r"[1-9][0-9]{0,6}", number):
            raise ValueError("Invalid PR number")
        pr = fetch(env["GITHUB_REPOSITORY"], number, env["GH_TOKEN"])
        current_sha = pr["head"]["sha"]
        if pr["state"] != "open":
            raise ValueError(f"PR #{number} is not open")
        if not isinstance(current_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", current_sha):
            raise ValueError(f"PR #{number} has no valid head SHA")
        if not current_sha.startswith(sha):
            raise ValueError(f"PR #{number} currently points to {current_sha[:12]}, not {sha}")
        if (pr["base"]["repo"]["full_name"].lower() != env["GITHUB_REPOSITORY"].lower() or
                pr["base"]["ref"] != env["TARGET_DEFAULT_BRANCH"]):
            raise ValueError("PR targets another repository or branch")
        sha = current_sha
        repository = pr["head"]["repo"]["full_name"]
        branch = pr["head"]["ref"]
    elif event == "push":
        number = 0
    else:
        raise ValueError("Unsupported Build event")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Expected a full source commit SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid source repository")
    simulator_repository = env["TARGET_SIMULATOR_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", simulator_repository):
        raise ValueError("Invalid simulator repository")
    simulator_commit = fetch_main(simulator_repository, env["GH_TOKEN"])
    if not isinstance(simulator_commit, str) or not re.fullmatch(r"[a-f0-9]{40}", simulator_commit):
        raise ValueError("Simulator main did not resolve to a full commit SHA")
    return {"event": event, "number": int(number), "branch": branch,
            "commit": sha, "repository": repository,
            "simulator_repository": simulator_repository,
            "simulator_commit": simulator_commit}


def main():
    target = resolve(os.environ)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"sha={target['commit']}\nrepository={target['repository']}\nnumber={target['number']}\n"
                     f"simulator_repository={target['simulator_repository']}\n"
                     f"simulator_commit={target['simulator_commit']}\n")
    with open("target.json", "w") as output:
        json.dump(target, output)


if __name__ == "__main__":
    main()
