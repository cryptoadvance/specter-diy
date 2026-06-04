import asyncio
import os
import sys
import tempfile
import types
import unittest

from native_support import setup_native_stubs


sys.platform = "linux"
setup_native_stubs()

microur = types.ModuleType("microur")
microur_decoder = types.ModuleType("microur.decoder")
microur_util = types.ModuleType("microur.util")
microur_decoder.FileURDecoder = type("FileURDecoder", (), {})
microur_util.cbor = object()
sys.modules["microur"] = microur
sys.modules["microur.decoder"] = microur_decoder
sys.modules["microur.util"] = microur_util

from hosts.sd import SDHost


class DummyGUI:
    def __init__(self):
        self.menus = []
        self.prompts = []
        self.alerts = []
        self._menu_responses = ["__delete_file__", None]

    async def menu(self, buttons, **kwargs):
        self.menus.append((buttons, kwargs))
        if kwargs.get("title") == "Delete SD card file":
            return buttons[0][0]
        return self._menu_responses.pop(0)

    async def prompt(self, title, msg):
        self.prompts.append((title, msg))
        return True

    async def alert(self, title, msg):
        self.alerts.append((title, msg))


class DummyManager:
    def __init__(self):
        self.gui = DummyGUI()


class SDHostDeleteTest(unittest.TestCase):
    def test_delete_file_from_select_menu(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep_path = os.path.join(tmp, "keep.psbt")
            delete_path = os.path.join(tmp, "delete.psbt")
            with open(keep_path, "wb") as f:
                f.write(b"keep")
            with open(delete_path, "wb") as f:
                f.write(b"delete")

            host = SDHost("/tmp", sdpath=tmp)
            host.manager = DummyManager()

            selected = asyncio.run(host.select_file([".psbt"]))

            self.assertIsNone(selected)
            self.assertTrue(os.path.exists(keep_path))
            self.assertFalse(os.path.exists(delete_path))
            self.assertEqual(host.manager.gui.prompts[0][0], "Delete file?")
            self.assertEqual(host.manager.gui.alerts[0][0], "Deleted")
            self.assertEqual(len(host.manager.gui.menus), 3)


if __name__ == "__main__":
    unittest.main()
