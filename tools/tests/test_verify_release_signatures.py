"""
Offline end-to-end tests for tools/verify_release_signatures.py and the
signature flow used by .github/workflows/release-finalize.yml.

No merge, no GitHub Actions, no real vendor signers: uses the committed test
key set (bootloader/keys/test/*.pem + pubkeys.c) and in-memory upgrade files.

    pip install cryptography intelhex bitstring click pytest
    pytest tools/tests -v
"""

import io
import os
import sys
import importlib.util

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOOTLOADER_TOOLS = os.path.join(REPO_ROOT, "bootloader", "tools")
TEST_KEYS = os.path.join(REPO_ROOT, "bootloader", "keys", "test")
TEST_PUBKEYS_C = os.path.join(TEST_KEYS, "pubkeys.c")

for p in (os.path.join(REPO_ROOT, "tools"), BOOTLOADER_TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.blsection import PayloadSection, SignatureSection, make_signature_message
from core.signature import seckey_from_pem, parse_recoverable_sig
from core.recovery import sign_recoverable

import verify_release_signatures as vrs

_spec = importlib.util.spec_from_file_location(
    "upgrade_generator", os.path.join(BOOTLOADER_TOOLS, "upgrade-generator.py")
)
_ug = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ug)

# Test key set: bootloader_sig_threshold = 2, main_fw_sig_threshold = 3
BOOT_THRESHOLD = 2
MAIN_THRESHOLD = 3


def _ver(major, minor, patch, rc=99):
    # rc == 99 means "final release"
    return f"{major * 10**8 + minor * 10**5 + patch * 100 + rc:010d}"


def build_unsigned(with_boot=True, main_ver=(1, 10, 5), boot_ver=(1, 2, 0)):
    sections = []
    if with_boot:
        sections.append(PayloadSection(
            "boot", b"BOOTLOADER<version:tag10>%s</version:tag10>"
                    % _ver(*boot_ver).encode()))
    sections.append(PayloadSection(
        "main", b"MAINFW<version:tag10>%s</version:tag10>"
                % _ver(*main_ver).encode()))
    sections.append(SignatureSection())
    buf = io.BytesIO()
    _ug.write_sections(buf, sections)
    return buf.getvalue()


def signing_message(upgrade_bytes):
    sections = _ug.load_sections(io.BytesIO(upgrade_bytes))
    payload_sections, _ = _ug.parse_sections(sections)
    return make_signature_message(payload_sections)


def seckey(name):
    return seckey_from_pem(open(os.path.join(TEST_KEYS, name + ".pem"), "rb").read())


def import_sig(upgrade_bytes, b64sig):
    """Mirror `upgrade-generator.py import-sig` including its at-import dedup."""
    sections = _ug.load_sections(io.BytesIO(upgrade_bytes))
    pl_sections, _ = _ug.parse_sections(sections)
    msg = make_signature_message(pl_sections)
    sig, pub = parse_recoverable_sig(b64sig, msg)
    _ug.add_signature(sections, sig, pub)  # ClickException on duplicate fingerprint
    out = io.BytesIO()
    _ug.write_sections(out, sections)
    return out.getvalue()


def sign_with(upgrade_bytes, *pem_names, message=None):
    u = upgrade_bytes
    msg = message if message is not None else signing_message(upgrade_bytes)
    for name in pem_names:
        u = import_sig(u, sign_recoverable(msg, seckey(name)))
    return u


def check(upgrade_bytes, provided_count):
    return vrs.check_signatures(
        upgrade_bytes, TEST_PUBKEYS_C, BOOT_THRESHOLD, MAIN_THRESHOLD,
        provided_count=provided_count,
    )


# --- bootloader upgrade: vendor-only, threshold 2 ---------------------------
def test_two_distinct_vendor_signatures_accepted():
    u = sign_with(build_unsigned(with_boot=True), "vend1", "vend2")
    assert check(u, 2).ok


def test_one_vendor_signature_rejected():
    u = sign_with(build_unsigned(with_boot=True), "vend1")
    res = check(u, 1)
    assert not res.ok and "need 2" in res.reason


def test_three_vendor_signatures_accepted():
    u = sign_with(build_unsigned(with_boot=True), "vend1", "vend2", "vend3")
    assert check(u, 3).ok


def test_same_vendor_twice_rejected_at_import():
    base = build_unsigned(with_boot=True)
    u = sign_with(base, "vend1")
    with pytest.raises(Exception):
        import_sig(u, sign_recoverable(signing_message(base), seckey("vend1")))


def test_vendor_plus_maintainer_only_below_vendor_threshold_rejected():
    u = sign_with(build_unsigned(with_boot=True), "vend1", "maint1")
    res = check(u, 2)
    assert not res.ok and "need 2" in res.reason


def test_two_vendor_plus_maintainer_only_accepted():
    u = sign_with(build_unsigned(with_boot=True), "vend1", "vend2", "maint1")
    assert check(u, 3).ok


def test_tampered_signature_byte_rejected():
    base = build_unsigned(with_boot=True)
    u = sign_with(base, "vend1", "vend2")
    sections = _ug.load_sections(io.BytesIO(u))
    _, sig_section = _ug.parse_sections(sections)
    fp = next(iter(sig_section.signatures))
    blob = bytearray(sig_section.signatures[fp])
    blob[10] ^= 0xFF
    sig_section.signatures[fp] = bytes(blob)
    out = io.BytesIO()
    _ug.write_sections(out, sections)
    res = check(out.getvalue(), 2)
    assert not res.ok and "invalid signature" in res.reason


def test_signatures_over_wrong_message_rejected():
    base = build_unsigned(with_boot=True)
    wrong_msg = signing_message(build_unsigned(with_boot=True, main_ver=(9, 9, 9)))
    u = sign_with(base, "vend1", "vend2", message=wrong_msg)
    assert not check(u, 2).ok


def test_valid_signature_from_foreign_key_rejected():
    base = build_unsigned(with_boot=True)
    foreign = (42).to_bytes(32, "big")
    u = import_sig(base, sign_recoverable(signing_message(base), foreign))
    u = import_sig(u, sign_recoverable(signing_message(base), seckey("vend1")))
    res = check(u, 2)
    assert not res.ok and "not an accepted production key" in res.reason


def test_duplicate_signer_backstop_in_verifier():
    # If import-sig's own dedup were bypassed, the verifier still rejects on the
    # provided-count mismatch.
    u = sign_with(build_unsigned(with_boot=True), "vend1", "vend2")
    res = check(u, 3)  # claim 3 provided but file has 2 distinct signers
    assert not res.ok and "duplicate signer" in res.reason


# --- main-firmware-only upgrade: vendor OR maintainer, threshold 3 ----------
def test_main_only_maintainers_count_toward_threshold():
    u = sign_with(build_unsigned(with_boot=False), "maint1", "maint2", "vend1")
    res = check(u, 3)
    assert res.ok and not res.is_bootloader


def test_main_only_below_threshold_rejected():
    u = sign_with(build_unsigned(with_boot=False), "maint1", "vend1")
    assert not check(u, 2).ok


# --- key set / threshold invariants (mirror validate_pubkey_set) -----------
def test_zero_bootloader_threshold_rejected():
    u = sign_with(build_unsigned(with_boot=True), "vend1", "vend2")
    res = vrs.check_signatures(u, TEST_PUBKEYS_C, 0, MAIN_THRESHOLD, provided_count=2)
    assert not res.ok and "invalid key set" in res.reason


def test_bootloader_threshold_above_vendor_key_count_rejected():
    u = sign_with(build_unsigned(with_boot=True), "vend1", "vend2")
    res = vrs.check_signatures(u, TEST_PUBKEYS_C, 999, MAIN_THRESHOLD, provided_count=2)
    assert not res.ok and "invalid key set" in res.reason


def test_zero_main_threshold_rejected():
    u = sign_with(build_unsigned(with_boot=False), "maint1", "maint2", "vend1")
    res = vrs.check_signatures(u, TEST_PUBKEYS_C, BOOT_THRESHOLD, 0, provided_count=3)
    assert not res.ok and "invalid key set" in res.reason


def test_production_thresholds_are_valid():
    prod = os.path.join(REPO_ROOT, "bootloader", "keys", "production", "pubkeys.c")
    u = sign_with(build_unsigned(with_boot=True), "vend1", "vend2")
    # production is 2-of-4 vendor / 2-of-8 vendor+maintainer -> key set is valid,
    # so this must fail on the signatures (test keys), not on "invalid key set".
    res = vrs.check_signatures(u, prod, 2, 2, provided_count=2)
    assert "invalid key set" not in res.reason
