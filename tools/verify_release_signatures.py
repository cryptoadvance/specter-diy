#!/usr/bin/env python3
"""
Verify that a signed Specter DIY upgrade file satisfies the production signing
policy - the same policy the on-device bootloader enforces in verify_multisig():

  * upgrade that contains a bootloader ("boot") section:
        >= bootloader_sig_threshold valid signatures from VENDOR keys
  * main-firmware-only upgrade:
        >= main_fw_sig_threshold valid signatures from VENDOR or MAINTAINER keys

This is deliberately independent of bootloader/tools/introspect-binary.py, which
puts vendor and maintainer keys into one combined lookup and does not restrict a
bootloader payload to vendor keys.

Used by .github/workflows/release-finalize.yml as the authoritative signature
gate, and covered by tools/tests/test_verify_release_signatures.py.

Usage:

    python3 tools/verify_release_signatures.py \
        --upgrade release/specter_upgrade.bin \
        --pubkeys bootloader/keys/production/pubkeys.c \
        --boot-threshold 2 \
        --main-threshold 2 \
        --provided-count 2

Exit code 0 = policy satisfied, non-zero = rejected (reason on stdout).
"""

import argparse
import io
import importlib.util
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BOOTLOADER_TOOLS = os.path.join(_REPO_ROOT, "bootloader", "tools")
if _BOOTLOADER_TOOLS not in sys.path:
    sys.path.insert(0, _BOOTLOADER_TOOLS)

from core.blsection import make_signature_message  # noqa: E402
from core.signature import verify  # noqa: E402
from parse_pubkeys import get_pubkey_info  # noqa: E402

# load_sections / parse_sections live in upgrade-generator.py, whose hyphenated
# name blocks a normal import (same trick as introspect-binary.py).
_spec = importlib.util.spec_from_file_location(
    "upgrade_generator", os.path.join(_BOOTLOADER_TOOLS, "upgrade-generator.py")
)
_ug = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ug)
load_sections = _ug.load_sections
parse_sections = _ug.parse_sections


class PolicyResult:
    def __init__(self, ok, reason, valid_signers, is_bootloader, threshold):
        self.ok = ok
        self.reason = reason
        self.valid_signers = list(valid_signers)
        self.is_bootloader = is_bootloader
        self.threshold = threshold

    def __bool__(self):
        return self.ok


def check_signatures(upgrade_bytes, pubkeys_c_path, boot_threshold,
                     main_threshold, provided_count=None):
    """Return a PolicyResult for an already-signed upgrade file (bytes)."""
    info = get_pubkey_info(pubkeys_c_path)
    vendor = {bytes.fromhex(fp): (owner, pk) for owner, fp, pk in info["vendor"]}
    maint = {bytes.fromhex(fp): (owner, pk) for owner, fp, pk in info["maintainer"]}

    # Mirror the on-device validate_pubkey_set(): a threshold must be >= 1 and
    # must not exceed the number of keys that can ever satisfy it. Otherwise the
    # key set itself is invalid and the bootloader would refuse to boot with it,
    # so "policy satisfied" would be a false statement.
    n_vendor = len(vendor)
    n_maint = len(maint)
    if not 1 <= boot_threshold <= n_vendor:
        return PolicyResult(
            False,
            f"invalid key set: bootloader_sig_threshold {boot_threshold} is not "
            f"in [1, {n_vendor}] (number of vendor keys)",
            [], True, boot_threshold,
        )
    if not 1 <= main_threshold <= n_vendor + n_maint:
        return PolicyResult(
            False,
            f"invalid key set: main_fw_sig_threshold {main_threshold} is not in "
            f"[1, {n_vendor + n_maint}] (vendor + maintainer keys)",
            [], False, main_threshold,
        )

    sections = load_sections(io.BytesIO(upgrade_bytes))
    payload_sections, sig_section = parse_sections(sections)
    if sig_section is None:
        return PolicyResult(False, "upgrade file has no signature section",
                            [], False, 0)

    message = make_signature_message(payload_sections)
    is_bootloader = any(s.name == "boot" for s in payload_sections)

    if is_bootloader:
        accepted = vendor
        threshold = boot_threshold
        role = "vendor"
    else:
        accepted = {**maint, **vendor}
        threshold = main_threshold
        role = "vendor/maintainer"

    sigs = sig_section.signatures

    if provided_count is not None and len(sigs) != provided_count:
        return PolicyResult(
            False,
            f"{provided_count} signatures provided but the upgrade file holds "
            f"{len(sigs)} distinct signers (duplicate signer?)",
            [], is_bootloader, threshold,
        )

    valid_signers = []
    for fp, sig in sigs.items():
        if fp in accepted:
            owner, pubkey = accepted[fp]
            if not verify(sig, message, pubkey):
                return PolicyResult(
                    False, f"invalid signature for {owner} ({fp.hex()})",
                    valid_signers, is_bootloader, threshold,
                )
            valid_signers.append(owner)
        elif fp in maint and is_bootloader:
            # A maintainer-only key on a bootloader upgrade is not an error,
            # it simply does not count toward the vendor threshold.
            continue
        else:
            return PolicyResult(
                False, f"signer {fp.hex()} is not an accepted production key "
                       f"for this upgrade type",
                valid_signers, is_bootloader, threshold,
            )

    if len(valid_signers) < threshold:
        return PolicyResult(
            False,
            f"{len(valid_signers)} valid {role} signature(s), need {threshold}",
            valid_signers, is_bootloader, threshold,
        )

    return PolicyResult(True, "signature policy satisfied", valid_signers,
                        is_bootloader, threshold)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upgrade", required=True,
                    help="path to the signed upgrade file")
    ap.add_argument("--pubkeys", required=True,
                    help="path to the production pubkeys.c")
    ap.add_argument("--boot-threshold", type=int, required=True)
    ap.add_argument("--main-threshold", type=int, required=True)
    ap.add_argument("--provided-count", type=int, default=None,
                    help="number of signatures that were imported; if given, "
                         "must equal the number of distinct signers in the file")
    args = ap.parse_args(argv)

    with open(args.upgrade, "rb") as fh:
        upgrade_bytes = fh.read()

    res = check_signatures(upgrade_bytes, args.pubkeys, args.boot_threshold,
                           args.main_threshold, args.provided_count)

    kind = "bootloader" if res.is_bootloader else "main-firmware"
    print(f"upgrade type       : {kind}")
    print(f"required threshold : {res.threshold}")
    print(f"valid signers      : {', '.join(res.valid_signers) or '(none)'}")
    print(f"result             : {res.reason}")

    if not res.ok:
        print("REJECTED: the on-device bootloader would not accept this upgrade.")
        return 1
    print("ACCEPTED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
