"""
Static portability guards for the BitBox modules.

The native test suite runs on CPython, where several constructs work that
MicroPython does not support. Two such bugs actually shipped into this
feature and were only caught by building and running the unix port:

  * hmac.new(key, msg, hashlib.sha256) - MicroPython's hmac only accepts
    the digest *name*, i.e. digestmod="sha256". This one was fatal: it
    crashed the backup-id check, so the import could never have worked on
    real hardware.
  * bytes.hex() - not implemented in MicroPython; use
    binascii.hexlify(...).decode().

These checks are deliberately source-level greps rather than behavioural
tests, because CPython cannot reproduce the failure at runtime. They are
cheap insurance against a reintroduction, not a substitute for actually
building the firmware.
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import os
import re
from unittest import TestCase

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
GUARDED_FILES = ["bitbox_backup.py", "bitbox_sd.py"]


def _read(name):
    with open(os.path.join(SRC, name), "r", encoding="utf-8") as f:
        return f.read()


def _code_lines(source):
    """Yields (lineno, text) for lines that are not comments. Crude but
    good enough to stop the guards tripping over their own explanations."""
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        yield i, line


class MicroPythonPortabilityTest(TestCase):
    def _assert_absent(self, pattern, message):
        rx = re.compile(pattern)
        hits = []
        for name in GUARDED_FILES:
            for lineno, line in _code_lines(_read(name)):
                if rx.search(line):
                    hits.append("%s:%d: %s" % (name, lineno, line.strip()))
        self.assertEqual(hits, [], "%s\n%s" % (message, "\n".join(hits)))

    def test_no_bytes_hex_calls(self):
        self._assert_absent(
            r"\.hex\(\)",
            "bytes.hex() does not exist in MicroPython - "
            "use binascii.hexlify(x).decode() instead.",
        )

    def test_hmac_uses_digest_name(self):
        """hmac.new() must pass digestmod as the string "sha256"."""
        rx = re.compile(r"hmac\.new\(")
        for name in GUARDED_FILES:
            source = _read(name)
            for lineno, line in _code_lines(source):
                if rx.search(line):
                    self.assertIn(
                        'digestmod="', line,
                        "%s:%d: hmac.new() must pass digestmod as a name, e.g. "
                        'digestmod="sha256" - MicroPython rejects the hashlib '
                        "type object.\n%s" % (name, lineno, line.strip()),
                    )

    def test_no_fstrings(self):
        self._assert_absent(
            r"""(?<![\w'"])f["']""",
            "f-strings are not supported by this MicroPython build - "
            "use %-formatting.",
        )

    def test_no_cpython_only_stdlib(self):
        self._assert_absent(
            r"^\s*(import|from)\s+(typing|dataclasses|enum|abc|functools|itertools)\b",
            "This module is not available in MicroPython.",
        )

    def test_guarded_files_exist(self):
        """Fails loudly if a guarded file is renamed, so the guards can
        never silently stop covering anything."""
        for name in GUARDED_FILES:
            self.assertTrue(
                os.path.isfile(os.path.join(SRC, name)), "missing: %s" % name
            )
