import asyncio
import gc
import os
import sys
import types
from unittest import TestCase

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

import platform
from hosts.sd import SDHost
from tests.util import TEST_DIR, clear_testdir


class FakeGUI:
    def __init__(self, menu_results=None, prompt_results=None):
        self.menu_results = list(menu_results or [])
        self.prompt_results = list(prompt_results or [])
        self.menus = []
        self.prompts = []
        self.alerts = []

    async def menu(self, buttons, title="", note=None, last=None):
        self.menus.append({
            "title": title,
            "buttons": buttons,
            "last": last,
        })
        return self.menu_results.pop(0)

    async def prompt(self, title, msg, popup=False):
        self.prompts.append((title, msg))
        return self.prompt_results.pop(0)

    async def alert(self, title, msg, button_text="OK", note=None):
        self.alerts.append((title, msg, button_text))


class SDHostFileMenuTest(TestCase):
    def setUp(self):
        clear_testdir()
        platform.maybe_mkdir(TEST_DIR)
        platform.maybe_mkdir(TEST_DIR + "/host")
        platform.maybe_mkdir(TEST_DIR + "/sd")
        self.sdpath = TEST_DIR + "/sd"
        self.host = SDHost(TEST_DIR + "/host", sdpath=self.sdpath)

    def tearDown(self):
        clear_testdir()
        gc.collect()

    def write_file(self, name, content=b"data"):
        with open(self.sdpath + "/" + name, "wb") as f:
            f.write(content)

    def run_select_file(self, menu_results, prompt_results=None):
        gui = FakeGUI(menu_results, prompt_results)
        self.host.manager = types.SimpleNamespace(gui=gui)
        result = asyncio.run(self.host.select_file([".psbt", ".txt", ".json"]))
        return result, gui

    def test_select_file_menu_includes_delete_action(self):
        self.write_file("wallet.json")
        result, gui = self.run_select_file([self.sdpath + "/wallet.json"])

        self.assertEqual(result, self.sdpath + "/wallet.json")
        self.assertIn((self.host.DELETE_FILE, "Delete file"), gui.menus[0]["buttons"])

    def test_delete_file_removes_selected_file_after_confirmation(self):
        self.write_file("wallet.json")
        self.write_file("unsigned.psbt")

        result, gui = self.run_select_file(
            [
                self.host.DELETE_FILE,
                self.sdpath + "/wallet.json",
                self.sdpath + "/unsigned.psbt",
            ],
            [True],
        )

        self.assertEqual(result, self.sdpath + "/unsigned.psbt")
        self.assertFalse(os.path.exists(self.sdpath + "/wallet.json"))
        self.assertTrue(os.path.exists(self.sdpath + "/unsigned.psbt"))
        self.assertEqual(gui.prompts[0][0], "Delete file?")
        self.assertEqual(gui.alerts[0][0], "Success!")

    def test_delete_file_cancel_keeps_file(self):
        self.write_file("wallet.json")

        result, gui = self.run_select_file(
            [
                self.host.DELETE_FILE,
                self.sdpath + "/wallet.json",
                self.sdpath + "/wallet.json",
            ],
            [False],
        )

        self.assertEqual(result, self.sdpath + "/wallet.json")
        self.assertTrue(os.path.exists(self.sdpath + "/wallet.json"))
        self.assertEqual(gui.alerts, [])

    def test_delete_last_matching_file_returns_none(self):
        self.write_file("wallet.json")

        result, gui = self.run_select_file(
            [
                self.host.DELETE_FILE,
                self.sdpath + "/wallet.json",
            ],
            [True],
        )

        self.assertIsNone(result)
        self.assertFalse(os.path.exists(self.sdpath + "/wallet.json"))
        self.assertEqual(gui.alerts[0][0], "Success!")
