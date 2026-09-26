#!/usr/bin/env python3
"""Record the exact checkout and firmware hashes for one CI artifact."""
from hashlib import sha256
from pathlib import Path
import json
import os
import subprocess
import sys

kind = sys.argv[1]
repository = os.environ["SPECTER_SOURCE_REPOSITORY"]
expected = os.environ["EXPECTED_SHA"]
actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
if actual != expected:
    raise SystemExit(f"Checkout {actual} does not match expected {expected}")
if kind == "firmware":
    files = [Path("bin/specter-diy.bin"), Path("bin/specter-diy.hex")]
elif kind == "browser":
    files = []
else:
    raise SystemExit("Expected firmware or browser")
hashes = {}
for path in files:
    if not path.is_file() or not path.stat().st_size:
        raise SystemExit(f"Missing artifact {path}")
    hashes[str(path)] = sha256(path.read_bytes()).hexdigest()
Path("source.json").write_text(json.dumps({
    "kind": kind, "commit": actual, "repository": repository, "sha256": hashes,
}, indent=2) + "\n")
