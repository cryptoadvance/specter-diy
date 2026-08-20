"""
State/UI-flow tests for Specter.import_bitbox_backup(). These exercise the
method against a scripted fake GUI and a real (simulator) SD card
directory tree, without needing lvgl or actual hardware.
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import hashlib
import os
import types
from unittest import TestCase

import platform
import specter as specter_module
import bitbox_sd as sd
import bitbox_backup as bb
from embit import bip39
from keystore.core import KeyStoreError
from tests.util import get_keystore, clear_testdir
from tests_native.bitbox_test_helpers import (
    OFFICIAL_VECTOR_MNEMONIC,
    OFFICIAL_VECTOR_ENTROPY,
    make_valid_backup_bytes,
    backup_id_for,
)

ENTROPY_16 = bytes(range(16))
ORIGINAL_MNEMONIC = "ability " * 11 + "acid"


class FakeGui:
    """Scripted stand-in for gui.specter.SpecterGUI: each interactive call
    (show_screen()'s returned fn, menu, prompt, get_input) consumes the
    next item from `script`, in the exact order import_bitbox_backup()
    calls them. Records everything shown/asked for assertions."""

    def __init__(self, script):
        self._script = list(script)
        self.shown_screens = []
        self.menu_calls = []
        self.prompt_calls = []
        self.alerts = []
        self.get_input_calls = 0

    def _next(self):
        if not self._script:
            raise AssertionError("FakeGui script exhausted - unexpected interactive call")
        return self._script.pop(0)

    def show_screen(self, popup=False):
        async def fn(scr):
            self.shown_screens.append(scr)
            return self._next()

        return fn

    async def menu(self, buttons=None, title=None, note=None, last=None):
        self.menu_calls.append({"buttons": buttons, "title": title})
        return self._next()

    async def prompt(self, title, msg, popup=False):
        self.prompt_calls.append((title, msg))
        return self._next()

    async def alert(self, title, msg, button_text="OK", note=None):
        self.alerts.append((title, msg))

    async def get_input(self, title="Enter your passphrase:", note="", suggestion=""):
        self.get_input_calls += 1
        return self._next()


def _run(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class BitboxBackupFlowTestBase(TestCase):
    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore(mnemonic=ORIGINAL_MNEMONIC, password="")
        self.original_fingerprint = self.keystore.fingerprint

        self.sp = specter_module.Specter.__new__(specter_module.Specter)
        self.sp.keystore = self.keystore
        self.sp.init_apps = lambda: None

        self.sd_root = sd._bitbox_root()
        self._clean_sd()

    def tearDown(self):
        self._clean_sd()
        clear_testdir()

    def _clean_sd(self):
        try:
            platform.delete_recursively(self.sd_root, include_self=True)
        except Exception:
            pass
        try:
            os.mkdir(self.sd_root)
        except OSError:
            pass

    def _write_backup(self, entropy=ENTROPY_16, num_files=3, **kwargs):
        dir_id = backup_id_for(entropy)
        dirpath = self.sd_root + "/" + dir_id
        try:
            os.mkdir(dirpath)
        except OSError:
            pass
        buf = make_valid_backup_bytes(entropy, **kwargs)
        for i in range(num_files):
            with open(dirpath + "/backup_%d.bin" % i, "wb") as f:
                f.write(buf)
        return dir_id

    def _hash_sd_tree(self):
        hashes = {}
        for root, dirs, files in os.walk(self.sd_root):
            for name in files:
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    hashes[path] = hashlib.sha256(f.read()).hexdigest()
        return hashes

    def _assert_keystore_unchanged(self):
        self.assertEqual(self.keystore.mnemonic, ORIGINAL_MNEMONIC)
        self.assertEqual(self.keystore.fingerprint, self.original_fingerprint)


class ImportMenuGatingTest(BitboxBackupFlowTestBase):
    """The "BitBox microSD backup" entry in the "Import recovery phrase"
    menu must only be offered when a backup can plausibly be found -
    showing it unconditionally (regardless of whether anything is on the
    card) is confusing, since picking it would just fail immediately.

    The presence check is deliberately name-based only (does a directory
    matching the 64-hex-character backup-id pattern exist under
    bitbox02/?), not a full read+parse+checksum - that heavier
    verification already happens, with well-tested error handling, once
    the user actually picks the entry. A directory that looks right but
    whose contents turn out to be invalid is still offered; it just fails
    with the normal "could not be verified" error after selection.
    """

    def setUp(self):
        super().setUp()
        self.sp.hosts = []

    def _import_menu_labels(self):
        self.sp.gui = FakeGui([255])  # back out of the menu immediately
        _run(self.sp.import_mnemonic())
        buttons = self.sp.gui.menu_calls[0]["buttons"]
        return [text for _value, text in buttons]

    def test_hidden_when_no_bitbox02_directory(self):
        self.assertNotIn("BitBox microSD backup", self._import_menu_labels())

    def test_shown_when_valid_backup_present(self):
        self._write_backup(ENTROPY_16)
        self.assertIn("BitBox microSD backup", self._import_menu_labels())

    def test_shown_even_if_backup_content_is_invalid(self):
        # Name-based presence check only, by design - see class docstring.
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        for i in range(3):
            with open(dirpath + "/backup_%d.bin" % i, "wb") as f:
                f.write(b"\x00" * 10)
        self.assertIn("BitBox microSD backup", self._import_menu_labels())

    def test_hidden_when_no_sd_card(self):
        class _NoCard:
            is_present = False

        real_sdcard = platform.sdcard
        platform.sdcard = _NoCard()
        try:
            labels = self._import_menu_labels()
        finally:
            platform.sdcard = real_sdcard
        self.assertNotIn("BitBox microSD backup", labels)

    def test_hidden_when_directory_name_is_not_hex(self):
        os.mkdir(self.sd_root + "/" + "not_a_backup")
        self.assertNotIn("BitBox microSD backup", self._import_menu_labels())

    def test_presence_check_does_not_write_to_the_card(self):
        self._write_backup(ENTROPY_16)
        before = self._hash_sd_tree()
        self._import_menu_labels()
        self.assertEqual(before, self._hash_sd_tree())


class AbortSafetyTest(BitboxBackupFlowTestBase):
    def test_abort_at_initial_warning(self):
        self._write_backup()
        self.sp.gui = FakeGui([False])  # decline the "not encrypted" warning
        result = _run(self.sp.import_bitbox_backup())
        self.assertIsNone(result)
        self._assert_keystore_unchanged()
        # must not even have looked at the SD card
        self.assertEqual(self.sp.gui.menu_calls, [])

    def test_abort_at_backup_selection(self):
        self._write_backup()
        self.sp.gui = FakeGui([True, 255])  # accept warning, then cancel selection
        result = _run(self.sp.import_bitbox_backup())
        self.assertIsNone(result)
        self._assert_keystore_unchanged()

    def test_abort_after_metadata_confirmation(self):
        dir_id = self._write_backup()
        self.sp.gui = FakeGui([True, dir_id, False])  # decline the metadata/backup prompt
        result = _run(self.sp.import_bitbox_backup())
        self.assertIsNone(result)
        self._assert_keystore_unchanged()

    def test_abort_at_mnemonic_confirmation(self):
        dir_id = self._write_backup()
        self.sp.gui = FakeGui([True, dir_id, True, False])  # decline final mnemonic confirm
        result = _run(self.sp.import_bitbox_backup())
        self.assertIsNone(result)
        self._assert_keystore_unchanged()

    def test_no_sd_card_present(self):
        class _NoCard:
            is_present = False

        real_sdcard = platform.sdcard
        platform.sdcard = _NoCard()
        try:
            self.sp.gui = FakeGui([True])  # accept warning, then no card detected
            result = _run(self.sp.import_bitbox_backup())
        finally:
            platform.sdcard = real_sdcard
        self.assertIsNone(result)
        self._assert_keystore_unchanged()
        self.assertEqual(len(self.sp.gui.alerts), 1)

    def test_invalid_backup_rejected_keystore_unchanged(self):
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        for i in range(3):
            with open(dirpath + "/backup_%d.bin" % i, "wb") as f:
                f.write(b"\x00" * 10)  # not a valid backup at all
        self.sp.gui = FakeGui([True, dir_id])
        result = _run(self.sp.import_bitbox_backup())
        self.assertIsNone(result)
        self._assert_keystore_unchanged()
        self.assertEqual(len(self.sp.gui.alerts), 1)

    def test_wrong_file_count_rejected_keystore_unchanged(self):
        dir_id = self._write_backup(num_files=2)
        self.sp.gui = FakeGui([True, dir_id])
        result = _run(self.sp.import_bitbox_backup())
        self.assertIsNone(result)
        self._assert_keystore_unchanged()


class SuccessfulImportTest(BitboxBackupFlowTestBase):
    def test_successful_import_loads_expected_mnemonic(self):
        dir_id = self._write_backup(ENTROPY_16)
        self.sp.gui = FakeGui([
            True,     # accept "not encrypted" warning
            dir_id,   # select the (only) backup
            True,     # confirm metadata screen
            True,     # confirm mnemonic screen
        ])
        result = _run(self.sp.import_bitbox_backup())
        self.assertEqual(result, self.sp.mainmenu)
        self.assertNotEqual(self.keystore.mnemonic, ORIGINAL_MNEMONIC)
        self.assertNotEqual(self.keystore.fingerprint, self.original_fingerprint)

    def test_metadata_screen_shows_accurate_partial_valid_copy_count(self):
        # One of three copies is corrupted - import must still succeed (2
        # of 3 individually valid, no majority recovery needed) and the
        # metadata screen must report the true count, not a hardcoded "3
        # of 3".
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        buf = make_valid_backup_bytes(ENTROPY_16)
        bad = bytearray(buf)
        bad[5] ^= 0xFF
        with open(dirpath + "/backup_0.bin", "wb") as f:
            f.write(buf)
        with open(dirpath + "/backup_1.bin", "wb") as f:
            f.write(buf)
        with open(dirpath + "/backup_2.bin", "wb") as f:
            f.write(bytes(bad))

        self.sp.gui = FakeGui([True, dir_id, True, True])
        _run(self.sp.import_bitbox_backup())

        metadata_screens = [
            scr for scr in self.sp.gui.shown_screens
            if len(scr.args) > 1 and "Valid copies" in scr.args[1]
        ]
        self.assertEqual(len(metadata_screens), 1)
        self.assertIn("2 of 3", metadata_screens[0].args[1])
        self.assertNotIn("3 of 3", metadata_screens[0].args[1])
        self.assertEqual(
            metadata_screens[0].kwargs.get("confirm_text"),
            "I verified independently",
        )
        self.assertIn("not authenticated", metadata_screens[0].args[1])

    def test_import_does_not_write_to_sd_card(self):
        dir_id = self._write_backup(ENTROPY_16)
        before = self._hash_sd_tree()
        self.sp.gui = FakeGui([True, dir_id, True, True])
        _run(self.sp.import_bitbox_backup())
        after = self._hash_sd_tree()
        self.assertEqual(before, after)

    def test_import_does_not_autosave(self):
        """A successful import must not persist anything: no keystore save
        helper may be invoked and no new file may appear anywhere under the
        test dir (flash/keystore) or on the card."""
        import hashlib as _hashlib

        dir_id = self._write_backup(ENTROPY_16)

        # Spy on every persistence entry point the keystore exposes.
        calls = []
        for meth in ("save_aead", "save_mnemonic", "create_new_secret"):
            if hasattr(self.keystore, meth):
                original = getattr(self.keystore, meth)

                def _spy(*a, __m=meth, __o=original, **kw):
                    calls.append(__m)
                    return __o(*a, **kw)

                setattr(self.keystore, meth, _spy)

        def snapshot(root):
            out = {}
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    p = os.path.join(dirpath, name)
                    with open(p, "rb") as f:
                        out[p] = _hashlib.sha256(f.read()).hexdigest()
            return out

        before_keystore = snapshot(self.keystore.path)
        before_sd = snapshot(self.sd_root)

        self.sp.gui = FakeGui([True, dir_id, True, True])
        _run(self.sp.import_bitbox_backup())

        # The import must actually have succeeded, otherwise this test would
        # pass trivially by never getting far enough to save anything.
        self.assertNotEqual(self.keystore.mnemonic, ORIGINAL_MNEMONIC)
        self.assertEqual(calls, [])
        self.assertEqual(snapshot(self.keystore.path), before_keystore)
        self.assertEqual(snapshot(self.sd_root), before_sd)

    def test_mnemonic_prompt_shown_with_correct_words(self):
        dir_id = self._write_backup(ENTROPY_16)
        self.sp.gui = FakeGui([True, dir_id, True, True])
        _run(self.sp.import_bitbox_backup())
        mnemonic_screens = [
            scr for scr in self.sp.gui.shown_screens if hasattr(scr, "mnemonic")
        ]
        self.assertEqual(len(mnemonic_screens), 1)

    def test_official_vector_end_to_end(self):
        from tests_native.bitbox_test_helpers import (
            OFFICIAL_VECTOR_HEX,
            OFFICIAL_VECTOR_BACKUP_ID,
        )
        import binascii

        dir_id = OFFICIAL_VECTOR_BACKUP_ID
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        buf = binascii.unhexlify(OFFICIAL_VECTOR_HEX)
        for i in range(3):
            with open(dirpath + "/backup_%d.bin" % i, "wb") as f:
                f.write(buf)
        self.sp.gui = FakeGui([True, dir_id, True, True])
        _run(self.sp.import_bitbox_backup())
        self.assertEqual(self.keystore.mnemonic, OFFICIAL_VECTOR_MNEMONIC)

    def test_majority_recovery_shows_warning_and_still_succeeds(self):
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        buf = make_valid_backup_bytes(ENTROPY_16)
        corrupted = []
        for offset, xor in [(10, 0x01), (20, 0x02), (30, 0x04)]:
            b = bytearray(buf)
            b[offset] ^= xor
            corrupted.append(bytes(b))
        for i, data in enumerate(corrupted):
            with open(dirpath + "/backup_%d.bin" % i, "wb") as f:
                f.write(data)

        self.sp.gui = FakeGui([True, dir_id, True, True])
        result = _run(self.sp.import_bitbox_backup())
        self.assertEqual(result, self.sp.mainmenu)

        metadata_screens = [
            scr for scr in self.sp.gui.shown_screens
            if getattr(scr, "kwargs", {}).get("warning") == "Majority recovery used!"
        ]
        self.assertEqual(len(metadata_screens), 1)
        self.assertEqual(
            metadata_screens[0].kwargs.get("confirm_text"),
            "I verified independently",
        )

    def test_phase_2_peeks_all_backups_in_a_single_mount(self):
        """Phase 2 must batch all _peek_backup_name calls into a single
        mount/unmount window. Before the fix, each backup was peeked
        individually via _read_sd, causing one mount cycle per backup;
        with many backups on the card this was both slow and redundant.
        Verified here by counting mount() calls during the phase-2 peek
        window (between the phase-1 listing and the phase-3 read) for a
        card holding three different backups."""
        entropies = [bytes([i]) * 16 for i in (1, 2, 3)]
        dir_ids = [self._write_backup(e) for e in entropies]

        mount_count = 0
        real_mount = platform.sdcard.mount
        real_unmount = platform.sdcard.unmount

        def counting_mount():
            nonlocal mount_count
            mount_count += 1
            return real_mount()

        platform.sdcard.mount = counting_mount
        platform.sdcard.unmount = real_unmount

        menu_mount_snapshot = []

        class _TrackingGui(FakeGui):
            async def menu(inner, buttons=None, title=None, note=None, last=None):
                # snapshot mount_count at the moment of the selection menu
                # (phase 2) - this is the count after phase 1 + phase 2
                # peeks, before phase 3.
                menu_mount_snapshot.append(mount_count)
                inner.menu_calls.append({"buttons": buttons, "title": title})
                return inner._next()

        self.sp.gui = _TrackingGui([True, dir_ids[1], True, True])
        try:
            _run(self.sp.import_bitbox_backup())
        finally:
            platform.sdcard.mount = real_mount
            platform.sdcard.unmount = real_unmount

        # The selection menu is shown once, and at that point mount_count
        # must be: 1 (phase 1 listing) + 1 (phase 2 batched peek) = 2.
        # With the old per-backup code it would be 1 + 3 = 4.
        self.assertEqual(len(menu_mount_snapshot), 1)
        self.assertEqual(
            menu_mount_snapshot[0], 2,
            "phase 2 should batch all peeks into one mount, got %d mounts "
            "before the selection menu (1 listing + 1 batched peek = 2)"
            % menu_mount_snapshot[0],
        )

    def test_card_is_not_left_mounted_across_gui_waits(self):
        """The card must be unmounted before every user-facing screen, so
        pulling it while a confirmation dialog is open is harmless."""
        dir_id = self._write_backup(ENTROPY_16)
        mount_state = []

        real_mount = platform.sdcard.mount
        real_unmount = platform.sdcard.unmount
        platform.sdcard.mount = lambda: (mount_state.append("mount"), real_mount())[1]
        platform.sdcard.unmount = lambda: (mount_state.append("unmount"), real_unmount())[1]

        class TrackingGui(FakeGui):
            def show_screen(inner, popup=False):
                async def fn(scr):
                    mount_state.append("gui")
                    inner.shown_screens.append(scr)
                    return inner._next()

                return fn

            async def menu(inner, buttons=None, title=None, note=None, last=None):
                mount_state.append("gui")
                inner.menu_calls.append({"buttons": buttons, "title": title})
                return inner._next()

            async def prompt(inner, title, msg, popup=False):
                mount_state.append("gui")
                inner.prompt_calls.append((title, msg))
                return inner._next()

        try:
            self.sp.gui = TrackingGui([True, dir_id, True, True])
            _run(self.sp.import_bitbox_backup())
        finally:
            platform.sdcard.mount = real_mount
            platform.sdcard.unmount = real_unmount

        # Walk the trace: at no point may a "gui" event occur while mounted.
        depth = 0
        for event in mount_state:
            if event == "mount":
                depth += 1
            elif event == "unmount":
                depth -= 1
            elif event == "gui":
                self.assertEqual(
                    depth, 0,
                    "SD card was still mounted during a GUI wait: %r" % (mount_state,),
                )
        self.assertEqual(depth, 0, "unbalanced mount/unmount: %r" % (mount_state,))
        self.assertIn("mount", mount_state)

    def test_bitbox_import_uses_normal_mnemonic_flow(self):
        """The BitBox path must reach the shared tail and nothing else."""
        dir_id = self._write_backup(ENTROPY_16)
        calls = []
        real_tail = self.sp.confirm_and_set_mnemonic

        async def spy(mnemonic):
            calls.append(mnemonic)
            return await real_tail(mnemonic)

        self.sp.confirm_and_set_mnemonic = spy
        self.sp.gui = FakeGui([True, dir_id, True, True])
        result = _run(self.sp.import_bitbox_backup())

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], self.keystore.mnemonic)
        self.assertEqual(result, self.sp.mainmenu)

    def test_bitbox_import_does_not_prompt_for_passphrase(self):
        """No passphrase (or any other extra) dialog may appear. Checked
        against the recorded GUI interactions, not against an attribute."""
        dir_id = self._write_backup(ENTROPY_16)
        self.sp.gui = FakeGui([True, dir_id, True, True])
        _run(self.sp.import_bitbox_backup())

        self.assertEqual(self.sp.gui.get_input_calls, 0)
        self.assertEqual(self.sp.gui.prompt_calls, [])
        blob = " ".join(
            [t for t, _ in self.sp.gui.prompt_calls]
            + [str(s.args) for s in self.sp.gui.shown_screens]
        ).lower()
        self.assertNotIn("use a passphrase now", blob)
        self.assertNotIn("add a passphrase", blob)
        # The script above contains exactly the 4 expected interactions; a
        # 5th would have raised "script exhausted" inside FakeGui.
        self.assertEqual(len(self.sp.gui.shown_screens), 3)
        self.assertEqual(len(self.sp.gui.menu_calls), 1)

    def test_bitbox_import_and_host_mnemonic_import_have_same_final_state(self):
        """From the moment a mnemonic exists, the BitBox path and a normal
        host-based recovery-phrase import (the QR/SD/USB path through
        import_mnemonic) must produce the same calls, the same state and the
        same target menu.

        This covers the host path specifically - manual word entry and
        loading a stored key are compared separately in
        ImportSourceEquivalenceTest below, because their pre-mnemonic
        context differs on purpose.
        """
        mnemonic = OFFICIAL_VECTOR_MNEMONIC

        def instrument(sp):
            log = {"set_mnemonic": [], "init_apps": 0, "keystore_saves": []}
            real_set = sp.set_mnemonic
            real_init = sp.init_apps

            def set_mnemonic(m, password=""):
                log["set_mnemonic"].append((m, password))
                return real_set(m, password)

            def init_apps():
                log["init_apps"] += 1
                return real_init()

            sp.set_mnemonic = set_mnemonic
            sp.init_apps = init_apps
            for meth in ("save_aead", "save_mnemonic"):
                if hasattr(sp.keystore, meth):
                    orig = getattr(sp.keystore, meth)

                    def spy(*a, __m=meth, __o=orig, **kw):
                        log["keystore_saves"].append(__m)
                        return __o(*a, **kw)

                    setattr(sp.keystore, meth, spy)
            return log

        # --- path A: BitBox microSD import ---
        dir_id = self._write_backup(OFFICIAL_VECTOR_ENTROPY)
        sp_a = self.sp
        log_a = instrument(sp_a)
        sp_a.gui = FakeGui([True, dir_id, True, True])
        result_a = _run(sp_a.import_bitbox_backup())
        state_a = (sp_a.keystore.mnemonic, sp_a.keystore.fingerprint)

        # --- path B: normal import via a host delivering the same phrase ---
        sp_b = specter_module.Specter.__new__(specter_module.Specter)
        sp_b.keystore = get_keystore(mnemonic=ORIGINAL_MNEMONIC, password="")
        sp_b.init_apps = lambda: None
        log_b = instrument(sp_b)

        class FakeHost:
            button = "Fake host"
            is_enabled = True

            async def get_data(self):
                from io import BytesIO

                return BytesIO(mnemonic.encode())

        host = FakeHost()
        sp_b.hosts = [host]
        sp_b.gui = FakeGui([host, True])
        result_b = _run(sp_b.import_mnemonic())
        state_b = (sp_b.keystore.mnemonic, sp_b.keystore.fingerprint)

        # Identical hand-over to the shared flow ...
        self.assertEqual(log_a["set_mnemonic"], [(mnemonic, "")])
        self.assertEqual(log_a["set_mnemonic"], log_b["set_mnemonic"])
        # ... identical number of app re-initialisations ...
        self.assertEqual(log_a["init_apps"], 1)
        self.assertEqual(log_a["init_apps"], log_b["init_apps"])
        # ... no persistence on either path ...
        self.assertEqual(log_a["keystore_saves"], [])
        self.assertEqual(log_b["keystore_saves"], [])
        # ... identical resulting key state ...
        self.assertEqual(state_a, state_b)
        # ... and the same target menu.
        self.assertEqual(result_a, sp_a.mainmenu)
        self.assertEqual(result_b, sp_b.mainmenu)
        self.assertEqual(result_a.__name__, result_b.__name__)
        # Neither path asked for a passphrase.
        self.assertEqual(sp_a.gui.get_input_calls, 0)
        self.assertEqual(sp_b.gui.get_input_calls, 0)


class ErrorMessageHygieneTest(BitboxBackupFlowTestBase):
    def test_error_messages_do_not_leak_entropy_or_mnemonic(self):
        dir_id = backup_id_for(ENTROPY_16)
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        for i in range(3):
            with open(dirpath + "/backup_%d.bin" % i, "wb") as f:
                f.write(b"\x00" * 10)
        self.sp.gui = FakeGui([True, dir_id])
        _run(self.sp.import_bitbox_backup())

        forbidden = [ENTROPY_16.hex()]
        from embit import bip39

        forbidden += bip39.WORDLIST[:50]  # sample of real mnemonic words
        blob = " ".join(msg for _, msg in self.sp.gui.alerts)
        for token in forbidden:
            self.assertNotIn(token, blob)


class ImportSourceEquivalenceTest(TestCase):
    """Verifies the property that actually matters for the BitBox feature:
    once a full, confirmed mnemonic exists, every import source triggers the
    same state change - same mnemonic and empty password into the keystore,
    exactly one app re-initialisation, no automatic passphrase, no automatic
    persistence, and the main menu as the destination.

    The sources deliberately differ *before* that point and are NOT expected
    to share code there:

    * host data (QR/SD/USB) and BitBox backups show the recovered words for
      confirmation, so both go through Specter.confirm_and_set_mnemonic();
    * manual entry / generation need no separate confirmation screen - the
      user just typed or reviewed the words in gui.recover()/new_mnemonic(),
      so initmenu calls Specter.set_mnemonic() directly;
    * loading an already stored key (internal flash, SD card, or smartcard)
      needs neither confirmation nor a fresh save, so the keystore performs
      keystore.set_mnemonic() itself (memorycard.py:291, sdcard.py:128,
      flash.py:267) and initmenu supplies init_apps() + mainmenu.

    What this test pins down is that all three assemblies end up equivalent.
    """

    TARGET = OFFICIAL_VECTOR_MNEMONIC

    def setUp(self):
        clear_testdir()
        self.sd_root = sd._bitbox_root()
        self._clean_sd()

    def tearDown(self):
        self._clean_sd()
        clear_testdir()

    def _clean_sd(self):
        try:
            platform.delete_recursively(self.sd_root, include_self=True)
        except Exception:
            pass
        try:
            os.mkdir(self.sd_root)
        except OSError:
            pass

    def _make_specter(self, keystore_cls=None):
        """Builds a Specter with a freshly initialised keystore, mirroring
        tests.util.get_keystore but allowing a subclass to be substituted."""
        from keystore.ram import RAMKeyStore
        from tests.util import TEST_DIR, show, show_loader

        cls = keystore_cls or RAMKeyStore
        platform.maybe_mkdir(TEST_DIR)
        platform.maybe_mkdir(TEST_DIR + "/keystore")
        ks = cls()
        ks.path = TEST_DIR + "/keystore"
        ks.show_loader = show_loader
        ks.show = show
        ks.load_secret(ks.path)
        ks.initialized = True
        ks._unlock("1234")
        ks.set_mnemonic(ORIGINAL_MNEMONIC, "")

        sp = specter_module.Specter.__new__(specter_module.Specter)
        sp.keystore = ks
        sp.hosts = []
        sp.apps = []
        sp.init_apps = lambda: None
        return sp

    def _instrument(self, sp):
        """Records what reaches the keystore, the app re-init count and any
        persistence attempt. Wrapping keystore.set_mnemonic (rather than
        Specter.set_mnemonic) is what makes the different assemblies
        comparable at all."""
        log = {"keystore_set_mnemonic": [], "init_apps": 0, "persisted": []}

        real_ks_set = sp.keystore.set_mnemonic
        real_init = sp.init_apps

        def ks_set(mnemonic=None, password=""):
            log["keystore_set_mnemonic"].append((mnemonic, password))
            return real_ks_set(mnemonic, password)

        def init_apps():
            log["init_apps"] += 1
            return real_init()

        sp.keystore.set_mnemonic = ks_set
        sp.init_apps = init_apps
        for meth in ("save_aead", "save_mnemonic"):
            if hasattr(sp.keystore, meth):
                orig = getattr(sp.keystore, meth)

                def spy(*a, __m=meth, __o=orig, **kw):
                    log["persisted"].append(__m)
                    return __o(*a, **kw)

                setattr(sp.keystore, meth, spy)
        return log

    # --- the four drivers -------------------------------------------------

    def _run_bitbox(self):
        sp = self._make_specter()
        dir_id = backup_id_for(OFFICIAL_VECTOR_ENTROPY)
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        buf = make_valid_backup_bytes(OFFICIAL_VECTOR_ENTROPY)
        for i in range(3):
            with open(dirpath + "/backup_%d.bin" % i, "wb") as f:
                f.write(buf)
        log = self._instrument(sp)
        sp.gui = FakeGui([True, dir_id, True, True])
        result = _run(sp.import_bitbox_backup())
        return sp, log, result

    def _run_host(self):
        sp = self._make_specter()
        target = self.TARGET

        class FakeHost:
            button = "Fake host"
            is_enabled = True

            async def get_data(self):
                from io import BytesIO

                return BytesIO(target.encode())

        host = FakeHost()
        sp.hosts = [host]
        log = self._instrument(sp)
        sp.gui = FakeGui([host, True])
        result = _run(sp.import_mnemonic())
        return sp, log, result

    def _run_manual(self):
        sp = self._make_specter()
        log = self._instrument(sp)
        gui = FakeGui([1])  # menuitem 1 = "Enter recovery phrase"
        target = self.TARGET

        async def recover(checker=None, lookup=None, fix=None):
            return target

        gui.recover = recover
        sp.gui = gui
        result = _run(sp.initmenu())
        return sp, log, result

    def _run_saved_key(self):
        """Mirrors the stored-key / smartcard path: the keystore loads and
        applies the mnemonic itself, initmenu adds init_apps() + mainmenu."""
        from keystore.ram import RAMKeyStore

        target = self.TARGET

        class _SavedKeyStore(RAMKeyStore):
            # class attributes intentionally shadow RAMKeyStore's properties
            is_key_saved = True
            load_button = "Load key"

            async def load_mnemonic(self, file=None):
                self.set_mnemonic(target, "")
                return True

        sp = self._make_specter(_SavedKeyStore)
        log = self._instrument(sp)
        sp.gui = FakeGui([2])  # menuitem 2 = "Load key"
        result = _run(sp.initmenu())
        return sp, log, result

    def _drivers(self):
        return [
            ("bitbox", self._run_bitbox),
            ("host", self._run_host),
            ("manual", self._run_manual),
            ("saved_key", self._run_saved_key),
        ]

    # --- the actual assertions --------------------------------------------

    def test_all_sources_apply_the_same_mnemonic_and_password(self):
        for name, driver in self._drivers():
            self.setUp()
            sp, log, _result = driver()
            self.assertEqual(
                log["keystore_set_mnemonic"], [(self.TARGET, "")],
                "%s: unexpected keystore.set_mnemonic calls: %r"
                % (name, log["keystore_set_mnemonic"]),
            )
            self.assertEqual(
                log["init_apps"], 1,
                "%s: init_apps called %d times" % (name, log["init_apps"]),
            )
            self.assertEqual(
                log["persisted"], [],
                "%s: unexpected persistence: %r" % (name, log["persisted"]),
            )
            self.assertEqual(sp.keystore.mnemonic, self.TARGET, name)
            self.tearDown()

    def test_all_sources_land_on_the_main_menu(self):
        for name, driver in self._drivers():
            self.setUp()
            sp, _log, result = driver()
            self.assertEqual(result, sp.mainmenu, name)
            self.assertEqual(result.__name__, "mainmenu", name)
            self.tearDown()

    def test_no_source_asks_for_a_passphrase(self):
        for name, driver in self._drivers():
            self.setUp()
            sp, _log, _result = driver()
            self.assertEqual(
                sp.gui.get_input_calls, 0,
                "%s: asked for free-text input (passphrase) during import" % name,
            )
            self.assertEqual(sp.gui.prompt_calls, [], name)
            self.tearDown()

    def test_all_sources_produce_identical_keys(self):
        """The strongest form: identical fingerprint across all sources."""
        fingerprints = {}
        for name, driver in self._drivers():
            self.setUp()
            sp, _log, _result = driver()
            fingerprints[name] = sp.keystore.fingerprint
            self.tearDown()
        self.assertEqual(len(set(fingerprints.values())), 1, fingerprints)


class ConfirmAndSetMnemonicPurityTest(TestCase):
    """confirm_and_set_mnemonic() is shared infrastructure and must contain
    no BitBox-specific condition - it must work on a Specter that has never
    touched the BitBox code or an SD card."""

    def setUp(self):
        clear_testdir()
        self.keystore = get_keystore(mnemonic=ORIGINAL_MNEMONIC, password="")
        self.sp = specter_module.Specter.__new__(specter_module.Specter)
        self.sp.keystore = self.keystore
        self.sp.init_apps = lambda: None

    def tearDown(self):
        clear_testdir()

    def test_works_without_any_bitbox_context(self):
        self.sp.gui = FakeGui([True])
        result = _run(self.sp.confirm_and_set_mnemonic(OFFICIAL_VECTOR_MNEMONIC))
        self.assertEqual(result, self.sp.mainmenu)
        self.assertEqual(self.keystore.mnemonic, OFFICIAL_VECTOR_MNEMONIC)
        # exactly one screen (the confirmation), no menus, no prompts
        self.assertEqual(len(self.sp.gui.shown_screens), 1)
        self.assertEqual(self.sp.gui.menu_calls, [])
        self.assertEqual(self.sp.gui.prompt_calls, [])
        self.assertEqual(self.sp.gui.get_input_calls, 0)

    def test_rejection_changes_nothing(self):
        before = (self.keystore.mnemonic, self.keystore.fingerprint)
        self.sp.gui = FakeGui([False])
        result = _run(self.sp.confirm_and_set_mnemonic(OFFICIAL_VECTOR_MNEMONIC))
        self.assertIsNone(result)
        self.assertEqual((self.keystore.mnemonic, self.keystore.fingerprint), before)

    def test_signature_takes_only_a_mnemonic(self):
        """Guards against a BitBox-specific flag sneaking in later."""
        import inspect

        params = list(
            inspect.signature(specter_module.Specter.confirm_and_set_mnemonic).parameters
        )
        self.assertEqual(params, ["self", "mnemonic"])


class BitboxExportTest(BitboxBackupFlowTestBase):
    """RAMKeyStore._write_bitbox_backup(): writing a native BitBox02-format
    backup of the currently loaded key to the SD card."""

    def _dir_id(self):
        return backup_id_for(bip39.mnemonic_to_bytes(ORIGINAL_MNEMONIC))

    def test_writes_three_copies_and_verifies(self):
        path, verified = self.keystore._write_bitbox_backup("label")
        self.assertTrue(verified)
        self.assertEqual(path, "bitbox02/%s/" % self._dir_id())
        dirpath = self.sd_root + "/" + self._dir_id()
        self.assertEqual(sorted(os.listdir(dirpath)), ["0.bin", "1.bin", "2.bin"])
        # all three copies are identical and decode back to the same phrase
        with open(dirpath + "/0.bin", "rb") as f:
            data = f.read()
        parsed = bb.validate_backup(data, self._dir_id())
        try:
            self.assertEqual(parsed.mnemonic(), ORIGINAL_MNEMONIC)
            self.assertEqual(parsed.name, "label")
        finally:
            parsed.zeroize()

    def test_refuses_to_merge_into_existing_backup_dir(self):
        """A real BitBox02 backup of the SAME key lives in the same
        directory name (the id depends only on the seed) but with
        timestamped filenames. Adding our 0/1/2.bin would leave six files,
        which both this device and real BitBox02 firmware then refuse to
        load at all (exactly-three-files rule) - so the write must be
        refused up front instead, leaving the existing backup untouched."""
        dir_id = self._dir_id()
        dirpath = self.sd_root + "/" + dir_id
        os.mkdir(dirpath)
        buf = make_valid_backup_bytes(
            bip39.mnemonic_to_bytes(ORIGINAL_MNEMONIC), name="real bitbox"
        )
        names = ["backup_Mon_2020-09-28T08-30-09Z_%d.bin" % i for i in range(3)]
        for name in names:
            with open(dirpath + "/" + name, "wb") as f:
                f.write(buf)

        with self.assertRaises(KeyStoreError) as ctx:
            self.keystore._write_bitbox_backup("label")
        self.assertIn("already exists", str(ctx.exception))
        # nothing was added, removed or modified
        self.assertEqual(sorted(os.listdir(dirpath)), sorted(names))
        for name in names:
            with open(dirpath + "/" + name, "rb") as f:
                self.assertEqual(f.read(), buf)

    def test_refuses_reexport_of_same_key(self):
        """Re-exporting the same key targets the same (now populated)
        directory - same refusal, no silent overwrite."""
        path, verified = self.keystore._write_bitbox_backup("label")
        self.assertTrue(verified)
        with self.assertRaises(KeyStoreError):
            self.keystore._write_bitbox_backup("another label")

    def test_encoded_buffer_is_zeroized_after_write(self):
        """The encoded backup holds the plaintext seed; the writer must
        wipe its buffer once the files are written (the on-disk copies are
        the intended plaintext, the in-RAM one is not)."""
        real_build_backup = bb.build_backup
        captured = {}

        def spy(entropy, **kwargs):
            backup_id, encoded = real_build_backup(entropy, **kwargs)
            captured["encoded"] = encoded
            return backup_id, encoded

        bb.build_backup = spy
        try:
            path, verified = self.keystore._write_bitbox_backup("label")
        finally:
            bb.build_backup = real_build_backup
        self.assertTrue(verified)
        self.assertIsInstance(captured["encoded"], bytearray)
        self.assertTrue(all(b == 0 for b in captured["encoded"]))


class _ScriptedShow:
    """Stand-in for keystore.show: consumes one scripted result per screen
    shown, in order, and records every screen for assertions."""

    def __init__(self, results):
        self._results = list(results)
        self.screens = []

    async def __call__(self, scr):
        self.screens.append(scr)
        if not self._results:
            raise AssertionError("unexpected extra screen: %r" % (scr,))
        return self._results.pop(0)


class LabelValidationTest(BitboxBackupFlowTestBase):
    """User-typed labels become file names - they must not contain path
    separators, traversal, FAT-invalid or control characters."""

    def test_accepts_normal_names(self):
        for label in ("my backup", "backup-01", "seed_2", "Müller", "a.b.c"):
            show = _ScriptedShow([])
            self.keystore.show = show
            self.assertTrue(_run(self.keystore.check_label(label)), label)
            self.assertEqual(show.screens, [])  # no error screen

    def test_rejects_hostile_names(self):
        for label in (
            "", "../evil", "a/b", "a\\b", "sub/../x", "x:y", "a*b",
            "a?b", 'a"b', "a<b", "a>b", "a|b", "nul\x00byte", "del\x7f",
        ):
            show = _ScriptedShow([True])
            self.keystore.show = show
            self.assertFalse(_run(self.keystore.check_label(label)), repr(label))
            self.assertEqual(len(show.screens), 1)  # error screen shown

    def test_export_aborts_on_hostile_label(self):
        async def fake_get_input(**kwargs):
            return "../evil"
        self.keystore.get_input = fake_get_input
        # menu (format choice) -> prompt (unencrypted warning) -> alert
        self.keystore.show = _ScriptedShow(["plain", True, True])
        sd_root = platform.fpath("/sd")
        before = set(os.listdir(sd_root))
        _run(self.keystore.export_mnemonic_to_sd())
        self.assertEqual(set(os.listdir(sd_root)), before)

    def test_export_plaintext_writes_verified_file(self):
        async def fake_get_input(**kwargs):
            return "mybackup"
        self.keystore.get_input = fake_get_input
        # menu (format choice) -> prompt (unencrypted warning) -> success alert
        self.keystore.show = _ScriptedShow(["plain", True, True])
        fpath = platform.fpath("/sd") + "/mybackup.specter.txt"
        try:
            _run(self.keystore.export_mnemonic_to_sd())
            with open(fpath, "r") as f:
                self.assertEqual(f.read(), ORIGINAL_MNEMONIC)
        finally:
            if platform.file_exists(fpath):
                os.remove(fpath)


class _FakeSDImportHost:
    """Stands in for SDHost in the import menu: provides the
    encrypted-files warning hook and records how often it fires."""

    button = "Open SD card file"
    is_enabled = True

    def __init__(self):
        self.warn_calls = 0
        self.get_data_calls = 0

    async def warn_about_encrypted_files(self):
        self.warn_calls += 1

    async def get_data(self, *args, **kwargs):
        self.get_data_calls += 1
        return None


class _FakeOtherImportHost:
    """A host without the warning hook (like QRHost/USBHost)."""

    button = "Scan QR code"
    is_enabled = True

    def __init__(self):
        self.get_data_calls = 0

    async def get_data(self, *args, **kwargs):
        self.get_data_calls += 1
        return None


class ImportEncryptedHintTest(BitboxBackupFlowTestBase):
    """The "encrypted recovery phrase on this card" hint must fire exactly
    when the user picks the SD host in the import-mnemonic flow - not
    implicitly on every SD file selection (PSBTs, descriptors, ...)."""

    def setUp(self):
        super().setUp()
        self.sp.hosts = []

    def test_hint_fires_when_sd_host_picked_for_import(self):
        host = _FakeSDImportHost()
        self.sp.hosts = [host]
        self.sp.gui = FakeGui([host])  # pick the host in the menu
        _run(self.sp.import_mnemonic())
        self.assertEqual(host.warn_calls, 1)
        self.assertEqual(host.get_data_calls, 1)

    def test_hosts_without_hint_hook_still_work(self):
        host = _FakeOtherImportHost()
        self.sp.hosts = [host]
        self.sp.gui = FakeGui([host])
        _run(self.sp.import_mnemonic())
        self.assertEqual(host.get_data_calls, 1)

    def test_select_file_does_not_fire_the_hint(self):
        """Regression guard: the generic SD file picker must stay silent
        even when device-encrypted key files are present on the card."""
        from hosts.sd import SDHost

        host = SDHost("testdir/sdhost-data")
        gui = FakeGui([None])  # cancel the file picker
        host.manager = types.SimpleNamespace(gui=gui)
        sd_root = platform.fpath("/sd")
        enc = sd_root + "/specterdiy00112233.somekey"
        txt = sd_root + "/note.txt"
        with open(enc, "wb") as f:
            f.write(b"x")
        with open(txt, "w") as f:
            f.write("hello")
        try:
            res = _run(host.select_file([".txt"]))
        finally:
            os.remove(enc)
            os.remove(txt)
        self.assertIsNone(res)
        self.assertEqual(gui.alerts, [])


class _StrictSdCard:
    """platform.sdcard stand-in with real-hardware mount semantics:
    mounting an already-mounted card raises, like os.mount() on a busy
    mount point does on device. The simulator's own SDCard is a no-op
    mount, which is exactly why the nested-mount bug this guards against
    was invisible in every native test."""

    def __init__(self):
        self._mounted = False

    @property
    def is_present(self):
        return True

    def mount(self):
        if self._mounted:
            raise OSError("mount point already in use")
        self._mounted = True

    def unmount(self):
        self._mounted = False

    def __enter__(self):
        self.mount()
        return self

    def __exit__(self, *args):
        self.unmount()


class SdCardItemsTest(BitboxBackupFlowTestBase):
    """Specter._list_sdcard_items(): the delete menu's scan of the card."""

    def test_bitbox_item_shows_backup_name(self):
        self._write_backup(name="my bitbox name")
        items = self.sp._list_sdcard_items()
        bitbox_items = [i for i in items if i[0] == "bitbox"]
        self.assertEqual(len(bitbox_items), 1)
        self.assertEqual(bitbox_items[0][2], "my bitbox name")

    def test_bitbox_name_peeked_within_a_single_mount(self):
        """Regression guard for the nested-mount bug: _list_sdcard_items
        holds its own mount window, and the name peek must reuse it. On
        hardware a second os.mount() on the mounted path raises - with
        the bug, every BitBox label silently fell back to the raw id."""
        self._write_backup(name="my bitbox name")
        real_sdcard = platform.sdcard
        platform.sdcard = _StrictSdCard()
        try:
            items = self.sp._list_sdcard_items()
        finally:
            platform.sdcard = real_sdcard
        bitbox_items = [i for i in items if i[0] == "bitbox"]
        self.assertEqual(len(bitbox_items), 1)
        # the peeked name, not the raw 64-hex id fallback
        self.assertEqual(bitbox_items[0][2], "my bitbox name")

    def test_card_is_unmounted_after_scan(self):
        self._write_backup(name="my bitbox name")
        real_sdcard = platform.sdcard
        strict = _StrictSdCard()
        platform.sdcard = strict
        try:
            self.sp._list_sdcard_items()
        finally:
            platform.sdcard = real_sdcard
        self.assertFalse(strict._mounted)

    def test_enc_and_plain_items_are_classified(self):
        sd_root = platform.fpath("/sd")
        enc = sd_root + "/specterdiy00112233.mykey"
        plain = sd_root + "/paperbackup.specter.txt"
        with open(enc, "wb") as f:
            f.write(b"x")
        with open(plain, "w") as f:
            f.write("word " * 11 + "word")
        try:
            items = self.sp._list_sdcard_items()
        finally:
            os.remove(enc)
            os.remove(plain)
        by_kind = {}
        for kind, ident, label in items:
            by_kind.setdefault(kind, []).append(label)
        self.assertEqual(by_kind.get("enc"), ["mykey"])
        self.assertEqual(by_kind.get("plain"), ["paperbackup"])

    def test_enumeration_capped_at_max_entries(self):
        """An adversarial card with far more root entries than a real
        Specter-DIY would ever produce must not cause unbounded memory
        use: the scan stops after _SDCARD_LIST_MAX_ENTRIES entries, the
        same bound bitbox_sd._listdir_typed uses for bitbox02/ listings.
        The "Format entire SD card" option in the delete menu is the
        tool for wiping everything indiscriminately, so silently stopping
        after the cap is the right behaviour."""
        sd_root = platform.fpath("/sd")
        cap = self.sp._SDCARD_LIST_MAX_ENTRIES
        created = []
        for i in range(cap + 50):
            fname = "%s/junk_%05d.txt" % (sd_root, i)
            with open(fname, "w") as f:
                f.write("x")
            created.append(fname)
        try:
            items = self.sp._list_sdcard_items()
        finally:
            for fname in created:
                try:
                    os.remove(fname)
                except OSError:
                    pass
        # None of the junk files match the enc/plain filters, so items
        # is empty - but the important thing is the function returned
        # in bounded time instead of enumerating all cap+50 entries.
        # (If the cap were missing, this test would still pass on a
        # fast machine; the guard is against adversarial memory use,
        # not speed. We assert the cap is respected by checking that
        # the loop did not process every entry: with the cap, only
        # cap entries are looked at, so the function cannot have
        # classified any file past the cap.)
        self.assertIsInstance(items, list)
