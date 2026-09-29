#!/usr/bin/env python3
"""Record the exact source from the direct Build event."""
import json
import os
import re
from urllib.request import Request, urlopen

SHA = re.compile(r"[a-f0-9]{40}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def fetch_pull(repository: str, number: int, token: str) -> dict:
    request = Request(f"https://api.github.com/repos/{repository}/pulls/{number}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
    })
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def resolve(env, fetch=fetch_pull) -> dict:
    event = env["TARGET_EVENT"]
    base_repository = env["GITHUB_REPOSITORY"]
    base_branch = env["TARGET_DEFAULT_BRANCH"]
    repository = env["TARGET_REPOSITORY"]
    commit = env["TARGET_SHA"]
    branch = env["TARGET_BRANCH"]
    number = int(env["TARGET_PR"])
    if event == "pull_request":
        if number <= 0 or env["TARGET_BASE_REPOSITORY"] != base_repository or \
                env["TARGET_BASE_BRANCH"] != base_branch:
            raise ValueError("PR does not target the default branch")
    elif event == "workflow_dispatch":
        if env["GITHUB_REF"] != f"refs/heads/{base_branch}" or number <= 0 or \
                not re.fullmatch(r"[a-f0-9]{7,40}", commit):
            raise ValueError("Invalid manual PR build request")
        pr = fetch(base_repository, number, env["GH_TOKEN"])
        head, base = pr["head"], pr["base"]
        if pr["state"] != "open" or not head["sha"].startswith(commit) or \
                base["repo"]["full_name"] != base_repository or base["ref"] != base_branch:
            raise ValueError("Manual PR request is stale or targets another branch")
        repository, commit, branch = head["repo"]["full_name"], head["sha"], head["ref"]
    elif event == "push":
        if env["GITHUB_REF"] != f"refs/heads/{base_branch}" or repository != base_repository:
            raise ValueError("Push did not target the default branch")
        number = 0
    else:
        raise ValueError("Unsupported Build event")
    if not SHA.fullmatch(commit) or not REPOSITORY.fullmatch(repository) or not branch:
        raise ValueError("Invalid source identity")
    simulator_repository = env["TARGET_SIMULATOR_REPOSITORY"]
    simulator_commit = env["TARGET_SIMULATOR_COMMIT"]
    if simulator_repository != "cryptoadvance/specter-diy-web-simulator" or \
            not SHA.fullmatch(simulator_commit):
        raise ValueError("Invalid approved simulator identity")
    return {"event": event, "number": number, "branch": branch,
            "repository": repository, "commit": commit,
            "base_repository": base_repository, "base_branch": base_branch,
            "simulator_repository": simulator_repository,
            "simulator_commit": simulator_commit}


def main():
    target = resolve(os.environ)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key in ("repository", "commit", "number", "simulator_repository", "simulator_commit"):
            output.write(f"{key}={target[key]}\n")
    with open("target.json", "w") as output:
        json.dump(target, output)


if __name__ == "__main__":
    main()
