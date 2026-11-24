#!/usr/bin/env python3
"""Check the dispatcher contract against the paired Web Simulator workflows."""
from pathlib import Path
import re
import sys

import dispatch_browser_preview as dispatcher


def workflow_dispatch_inputs(path):
    """Read workflow_dispatch input keys without adding a YAML dependency."""
    lines = path.read_text(encoding="utf-8").splitlines()
    dispatch = next(
        (index for index, line in enumerate(lines)
         if re.fullmatch(r"  workflow_dispatch:\s*(?:#.*)?", line)),
        None,
    )
    if dispatch is None:
        raise AssertionError(f"{path.name} has no top-level workflow_dispatch trigger")

    inputs_block = next(
        (index for index in range(dispatch + 1, len(lines))
         if re.fullmatch(r"    inputs:\s*(?:#.*)?", lines[index])),
        None,
    )
    if inputs_block is None:
        raise AssertionError(f"{path.name} has no workflow_dispatch.inputs block")

    names = []
    for line in lines[inputs_block + 1:]:
        if line.strip() and not line.lstrip().startswith("#"):
            indentation = len(line) - len(line.lstrip(" "))
            if indentation <= 4:
                break
            match = re.fullmatch(r"      ([A-Za-z_][A-Za-z0-9_-]*):\s*(?:#.*)?", line)
            if match:
                names.append(match.group(1))

    if len(names) != len(set(names)):
        raise AssertionError(f"{path.name} declares duplicate dispatch inputs")
    return tuple(names)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_dispatch_browser_preview_integration.py WORKFLOW_DIR")
    workflow_dir = Path(sys.argv[1])
    contracts = (
        (dispatcher.SIMULATOR_WORKFLOW, dispatcher.SIMULATOR_WORKFLOW_INPUTS),
        (dispatcher.APPROVAL_WORKFLOW, dispatcher.APPROVAL_WORKFLOW_INPUTS),
        (dispatcher.AUTO_MODE_WORKFLOW, ("pr_number", "comment_id", "action")),
    )
    for workflow_name, expected_inputs in contracts:
        path = workflow_dir / workflow_name
        if not path.is_file():
            raise AssertionError(f"paired Web Simulator workflow is missing: {path}")
        actual_inputs = workflow_dispatch_inputs(path)
        if actual_inputs != expected_inputs:
            raise AssertionError(
                f"{workflow_name} inputs mismatch: dispatcher={expected_inputs}, "
                f"workflow={actual_inputs}"
            )
        print(f"PASS {workflow_name}: {', '.join(actual_inputs)}")


if __name__ == "__main__":
    main()
