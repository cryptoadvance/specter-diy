#!/usr/bin/env python3
"""Select the official simulator-main revision for the trusted publisher."""
from pathlib import Path
from urllib.request import Request, urlopen
import json
import os
import re

SHA = re.compile(r"[a-f0-9]{40}")


def fetch_main(repository: str, token: str) -> str:
    request = Request(f"https://api.github.com/repos/{repository}/commits/main", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
    })
    with urlopen(request, timeout=30) as response:
        commit = json.load(response).get("sha")
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise ValueError("Simulator main did not resolve to a full commit SHA")
    return commit


def resolve(env, get_main=fetch_main) -> str:
    if env["BUILD_WORKFLOW_PATH"].split("@", 1)[0] != ".github/workflows/build.yml" or \
            env["BUILD_EVENT"] not in ("pull_request", "push", "workflow_dispatch"):
        raise ValueError("Unrecognized Build workflow run")
    current = get_main(env["SIMULATOR_REPOSITORY"], env["GH_TOKEN"])
    if env["BUILD_CONCLUSION"] == "success":
        path = Path(env["TARGET_FILE"])
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
            raise ValueError("Successful build is missing safe target metadata")
        try:
            target = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise ValueError("Build target metadata is malformed") from error
        if not isinstance(target, dict) or \
                target.get("simulator_repository", "").lower() != env["SIMULATOR_REPOSITORY"].lower() or \
                target.get("simulator_commit") != current:
            raise ValueError("Build did not use the current simulator main commit")
    return current


def main():
    commit = resolve(os.environ)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"simulator_commit={commit}\n")


if __name__ == "__main__":
    main()
