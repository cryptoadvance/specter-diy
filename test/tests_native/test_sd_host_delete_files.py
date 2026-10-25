import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

import os
import unittest

import platform

from hosts.sd import SDHost, DELETE_FILE, WIPE_SD_CARD


TEST_DIR = "testdir_sd"
SD_DIR = TEST_DIR + "/sd"


def run_async(coro):
    """Runs a coroutine to completion on a fresh event loop."""
    try:
        import asyncio
    except ImportError:
        import uasyncio as asyncio
    if hasattr(asyncio, "run"):
        return asyncio.run(coro)
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class FakeGUI:
    """Minimal GUI stub that replays scripted answers."""

    def __init__(self, menu=None, prompt=None):
        self.menu_answers = list(menu or [])
        self.prompt_answers = list(prompt or [])
        # values of the buttons of every menu we were asked to show
        self.menus = []
        self.alerts = []

    async def menu(self, buttons=[], title="", note=None, last=None):
        self.menus.append([b[0] for b in buttons])
        if len(self.menu_answers) > 0:
            return self.menu_answers.pop(0)
        return None

    async def prompt(self, title, msg, popup=False):
        if len(self.prompt_answers) > 0:
            return self.prompt_answers.pop(0)
        return False

    async def alert(self, title, msg, button_text="OK", note=None):
        self.alerts.append((title, msg))

    @property
    def messages(self):
        return [msg for _, msg in self.alerts]


class FakeManager:
    def __init__(self, gui):
        self.gui = gui


class SDHostDeleteTest(unittest.TestCase):
    def setUp(self):
        self._rmtree(TEST_DIR)
        platform.maybe_mkdir(TEST_DIR)
        platform.maybe_mkdir(SD_DIR)
        self.gui = FakeGUI()
        self.host = SDHost(TEST_DIR + "/host", sdpath=SD_DIR)
        self.host.manager = FakeManager(self.gui)

    def tearDown(self):
        self._rmtree(TEST_DIR)

    def _rmtree(self, path):
        try:
            platform.delete_recursively(path, include_self=True)
        except Exception:
            pass

    def write(self, name, data=b"psbt-data"):
        with open(SD_DIR + "/" + name, "wb") as f:
            f.write(data)

    def names(self):
        return sorted([f[0] for f in os.ilistdir(SD_DIR) if f[1] == 0x8000])

    def test_picker_offers_delete_actions(self):
        self.write("tx.psbt")
        res = run_async(self.host.select_file(self.host.extensions))
        # no answer scripted -> user cancelled
        self.assertIsNone(res)
        values = self.gui.menus[0]
        self.assertIn(DELETE_FILE, values)
        self.assertIn(WIPE_SD_CARD, values)
        # file itself is still offered
        self.assertIn(SD_DIR + "/tx.psbt", values)

    def test_picker_without_delete_has_no_actions(self):
        self.write("tx.psbt")
        run_async(self.host.select_file(self.host.extensions, allow_delete=False))
        values = self.gui.menus[0]
        self.assertNotIn(DELETE_FILE, values)
        self.assertNotIn(WIPE_SD_CARD, values)

    def test_delete_single_file(self):
        self.write("tx.psbt", b"unsigned transaction")
        self.write("wallet.json", b"{}")
        self.gui.menu_answers = [SD_DIR + "/tx.psbt", None]
        self.gui.prompt_answers = [True]
        run_async(self.host.delete_files())
        self.assertEqual(self.names(), ["wallet.json"])
        self.assertTrue(any("deleted" in m for m in self.gui.messages))

    def test_delete_cancel_keeps_file(self):
        self.write("tx.psbt", b"unsigned transaction")
        self.gui.menu_answers = [SD_DIR + "/tx.psbt", None]
        self.gui.prompt_answers = [False]
        run_async(self.host.delete_files())
        self.assertEqual(self.names(), ["tx.psbt"])
        self.assertFalse(any("deleted" in m for m in self.gui.messages))

    def test_delete_last_file_stops_picker(self):
        self.write("tx.psbt", b"unsigned transaction")
        self.gui.menu_answers = [SD_DIR + "/tx.psbt"]
        self.gui.prompt_answers = [True]
        run_async(self.host.delete_files())
        self.assertEqual(self.names(), [])
        # after the last file there is nothing to pick,
        # the flow should end without asking for a file again
        self.assertEqual(len(self.gui.menus), 1)
        self.assertTrue(any("Nothing to delete" in t for t, _ in self.gui.alerts))

    def test_wipe_deletes_all_files(self):
        self.write("tx.psbt")
        self.write("wallet.json")
        self.write("notes.txt")
        self.gui.prompt_answers = [True]
        run_async(self.host.wipe_sd_card())
        self.assertEqual(self.names(), [])
        self.assertTrue(any("All 3 files are deleted" in m for m in self.gui.messages))

    def test_wipe_cancel_keeps_files(self):
        self.write("tx.psbt")
        self.write("wallet.json")
        self.gui.prompt_answers = [False]
        run_async(self.host.wipe_sd_card())
        self.assertEqual(self.names(), ["tx.psbt", "wallet.json"])

    def test_get_data_deletes_then_opens_file(self):
        self.write("a.psbt", b"first")
        self.write("b.psbt", b"second")
        # SDHost.copy() uses MicroPython's write(buf, len) signature which
        # doesn't exist in CPython where the native tests run.
        # The flow we test here doesn't depend on it.
        def copy(fin, fout):
            fout.write(fin.read())
        self.host.copy = copy
        self.gui.menu_answers = [DELETE_FILE, SD_DIR + "/a.psbt", None, SD_DIR + "/b.psbt"]
        self.gui.prompt_answers = [True]
        stream = run_async(self.host.get_data())
        self.assertEqual(self.names(), ["b.psbt"])
        data = stream.read()
        self.assertTrue(data.startswith(b"sign "))
        self.assertIn(b"second", data)
        stream.close()

    def test_get_data_stops_when_card_is_empty(self):
        self.write("only.psbt", b"only file")
        self.gui.menu_answers = [WIPE_SD_CARD]
        self.gui.prompt_answers = [True]
        stream = run_async(self.host.get_data())
        # nothing left to open - no exception and no empty picker
        self.assertIsNone(stream)
        self.assertEqual(self.names(), [])

    def test_secure_delete_overwrites_before_removing(self):
        fname = SD_DIR + "/secret.psbt"
        self.write("secret.psbt", b"\x00" * 64)
        captured = {}
        original_remove = os.remove

        def fake_remove(path):
            if path == fname:
                with open(path, "rb") as f:
                    captured["data"] = f.read()
            return original_remove(path)

        os.remove = fake_remove
        try:
            platform.secure_delete_file(fname)
        finally:
            os.remove = original_remove

        self.assertFalse(platform.file_exists(fname))
        self.assertEqual(len(captured["data"]), 64)
        self.assertNotEqual(captured["data"], b"\x00" * 64)

    def test_secure_delete_missing_file_is_noop(self):
        platform.secure_delete_file(SD_DIR + "/not-there.psbt")
        self.assertEqual(self.names(), [])
