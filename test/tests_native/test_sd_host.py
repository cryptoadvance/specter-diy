import asyncio
import os
import sys
import types
from types import SimpleNamespace
from unittest import TestCase

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

microur = sys.modules.setdefault("microur", types.ModuleType("microur"))
microur_decoder = sys.modules.setdefault("microur.decoder", types.ModuleType("microur.decoder"))
microur_util = sys.modules.setdefault("microur.util", types.ModuleType("microur.util"))
microur_decoder.FileURDecoder = type("FileURDecoder", (), {})
microur_util.cbor = types.SimpleNamespace()
microur.decoder = microur_decoder
microur.util = microur_util

import platform
from hosts.core import HostError
from hosts.sd import SDHost
from tests.util import TEST_DIR, clear_testdir


class FakeGUI:
    def __init__(self, menu_results=None, prompt_results=None):
        self.menu_results = list(menu_results or [])
        self.prompt_results = list(prompt_results or [])
        self.menus = []
        self.prompts = []
        self.alerts = []

    async def menu(self, buttons, **kwargs):
        self.menus.append((buttons, kwargs))
        if self.menu_results:
            return self.menu_results.pop(0)
        return None

    async def prompt(self, title, msg, popup=False):
        self.prompts.append((title, msg, popup))
        if self.prompt_results:
            return self.prompt_results.pop(0)
        return False

    async def alert(self, title, msg, button_text="OK", note=None):
        self.alerts.append((title, msg, button_text, note))


class SDHostFileSelectionTest(TestCase):
    def setUp(self):
        clear_testdir()
        platform.maybe_mkdir(TEST_DIR)
        platform.maybe_mkdir(TEST_DIR + "/sd")
        platform.maybe_mkdir(TEST_DIR + "/host")
        self.sdpath = TEST_DIR + "/sd"
        self.host = SDHost(TEST_DIR + "/host", sdpath=self.sdpath)

    def tearDown(self):
        clear_testdir()

    def write_sd_file(self, name, data=b"test"):
        path = self.sdpath + "/" + name
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_select_file_includes_delete_actions_for_matching_files(self):
        psbt = self.write_sd_file("unsigned.psbt")
        self.write_sd_file("notes.md")
        gui = FakeGUI(menu_results=[psbt])
        self.host.manager = SimpleNamespace(gui=gui)

        result = asyncio.run(self.host.select_file([".psbt", ".txt", ".json"]))

        self.assertEqual(result, psbt)
        buttons = gui.menus[0][0]
        self.assertIn((psbt, "unsigned.psbt"), buttons)
        self.assertIn(((SDHost.DELETE_ACTION, psbt), "Delete unsigned.psbt"), buttons)
        self.assertFalse(any("notes.md" in str(button) for button in buttons))

    def test_delete_action_cancels_without_removing_file(self):
        psbt = self.write_sd_file("unsigned.psbt")
        gui = FakeGUI(
            menu_results=[(SDHost.DELETE_ACTION, psbt), psbt],
            prompt_results=[False],
        )
        self.host.manager = SimpleNamespace(gui=gui)

        result = asyncio.run(self.host.select_file([".psbt"]))

        self.assertEqual(result, psbt)
        self.assertTrue(os.path.exists(psbt))
        self.assertEqual(len(gui.prompts), 1)
        self.assertEqual(gui.alerts, [])

    def test_delete_action_removes_file_and_refreshes_menu(self):
        old_psbt = self.write_sd_file("old.psbt")
        keep_txt = self.write_sd_file("keep.txt")
        gui = FakeGUI(
            menu_results=[(SDHost.DELETE_ACTION, old_psbt), keep_txt],
            prompt_results=[True],
        )
        self.host.manager = SimpleNamespace(gui=gui)

        result = asyncio.run(self.host.select_file([".psbt", ".txt"]))

        self.assertEqual(result, keep_txt)
        self.assertFalse(os.path.exists(old_psbt))
        self.assertTrue(os.path.exists(keep_txt))
        self.assertEqual(len(gui.menus), 2)
        self.assertEqual(len(gui.alerts), 1)
        refreshed_buttons = gui.menus[1][0]
        self.assertFalse(any("old.psbt" in str(button) for button in refreshed_buttons))
        self.assertIn((keep_txt, "keep.txt"), refreshed_buttons)

    def test_deleting_last_matching_file_raises_no_files_error(self):
        psbt = self.write_sd_file("unsigned.psbt")
        gui = FakeGUI(
            menu_results=[(SDHost.DELETE_ACTION, psbt)],
            prompt_results=[True],
        )
        self.host.manager = SimpleNamespace(gui=gui)

        with self.assertRaises(HostError):
            asyncio.run(self.host.select_file([".psbt"]))

        self.assertFalse(os.path.exists(psbt))
