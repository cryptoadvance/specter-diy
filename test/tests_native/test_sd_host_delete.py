"""
Tests for the delete/format actions in the SD host's file picker.

The picker used to be able to open files and nothing else - a card that
filled up with old PSBTs and descriptors could only be cleaned on a
computer. This covers the two additions: deleting a single file, which
goes through platform.secure_delete_file() rather than os.remove(), and
formatting the whole card, which goes through
platform.sdcard.erase_and_format().
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import os
from unittest import TestCase

import platform
import hosts.sd as sd_module
from hosts.sd import SDHost, DELETE_ACTION, FORMAT_ACTION
from hosts.core import HostError
from tests.util import TEST_DIR, clear_testdir


def _run(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeProgress:
    """gui.screens.Progress is an LVGL screen; the native stub takes no
    arguments. Record what the format flow drives instead."""

    def __init__(self, *args, **kwargs):
        self.progress = []
        self.ticks = 0

    def set_progress(self, fraction):
        self.progress.append(fraction)

    def tick(self, d=10):
        self.ticks += 1


class _FakeGUI:
    def __init__(self, menu_results=None, prompt_results=None):
        self.menu_results = list(menu_results or [])
        self.prompt_results = list(prompt_results or [])
        self.menus = []
        self.prompts = []
        self.alerts = []
        self.screens = []

    async def menu(self, buttons, title="", note=None, last=None):
        self.menus.append({"title": title, "buttons": buttons, "last": last})
        return self.menu_results.pop(0)

    async def prompt(self, title, msg, popup=False):
        self.prompts.append((title, msg))
        return self.prompt_results.pop(0)

    async def alert(self, title, msg, button_text="OK", note=None):
        self.alerts.append((title, msg))

    async def load_screen(self, scr):
        self.screens.append(scr)


class _FakeManager:
    def __init__(self, gui):
        self.gui = gui


class _SDHostTestBase(TestCase):
    EXTENSIONS = [".psbt", ".txt", ".json"]

    def setUp(self):
        clear_testdir()
        platform.maybe_mkdir(TEST_DIR)
        self.sdpath = TEST_DIR + "/sd"
        platform.maybe_mkdir(self.sdpath)
        self.host = SDHost(TEST_DIR + "/host", sdpath=self.sdpath)
        self._real_progress = sd_module.Progress
        sd_module.Progress = _FakeProgress

    def tearDown(self):
        sd_module.Progress = self._real_progress
        clear_testdir()

    def _make_files(self, *names):
        for name in names:
            with open("%s/%s" % (self.sdpath, name), "wb") as f:
                f.write(b"x" * 64)

    def _gui(self, menu_results=None, prompt_results=None):
        gui = _FakeGUI(menu_results, prompt_results)
        self.host.manager = _FakeManager(gui)
        return gui


class SelectFileMenuTest(_SDHostTestBase):
    def test_delete_action_is_its_own_section(self):
        """It is a destructive action. Appended straight after the last
        extension group it reads as one more file of that group, which is
        what the review of the original delete PR asked to change."""
        self._make_files("a.psbt", "b.json")
        gui = self._gui(menu_results=[self.sdpath + "/a.psbt"])

        _run(self.host.select_file(self.EXTENSIONS))

        buttons = gui.menus[0]["buttons"]
        values = [b[0] for b in buttons]
        self.assertIn(DELETE_ACTION, values)
        index = values.index(DELETE_ACTION)
        # blank spacer, then a heading of its own, then the action
        self.assertEqual(buttons[index - 2], (None, None))
        self.assertIsNone(buttons[index - 1][0])
        self.assertIsNotNone(buttons[index - 1][1])
        # and it is the last entry, not buried between file groups
        self.assertEqual(index, len(buttons) - 1)

    def test_opening_a_file_still_returns_its_path(self):
        self._make_files("a.psbt")
        target = self.sdpath + "/a.psbt"
        gui = self._gui(menu_results=[target])

        self.assertEqual(_run(self.host.select_file(self.EXTENSIONS)), target)
        self.assertEqual(len(gui.menus), 1)

    def test_cancelling_the_picker_returns_none(self):
        self._make_files("a.psbt")
        self._gui(menu_results=[None])

        self.assertIsNone(_run(self.host.select_file(self.EXTENSIONS)))

    def test_no_matching_files_still_raises(self):
        self._gui()

        with self.assertRaises(HostError):
            _run(self.host.select_file(self.EXTENSIONS))


class DeleteFileTest(_SDHostTestBase):
    def test_confirmed_delete_overwrites_and_removes_the_file(self):
        """os.remove() only unlinks - the contents stay on the card until
        the space is reused. The delete has to go through
        secure_delete_file()."""
        self._make_files("a.psbt", "b.psbt")
        target = self.sdpath + "/a.psbt"
        gui = self._gui(
            menu_results=[DELETE_ACTION, target, self.sdpath + "/b.psbt"],
            prompt_results=[True],
        )
        calls = []
        real = platform.secure_delete_file
        platform.secure_delete_file = lambda path: calls.append(path) or real(path)
        try:
            res = _run(self.host.select_file(self.EXTENSIONS))
        finally:
            platform.secure_delete_file = real

        self.assertEqual(calls, [target])
        self.assertFalse(platform.file_exists(target))
        # back in the picker afterwards, with the deleted file gone from it
        self.assertEqual(res, self.sdpath + "/b.psbt")
        self.assertEqual(
            [b[0] for b in gui.menus[2]["buttons"] if b[0] not in (None, DELETE_ACTION)],
            [self.sdpath + "/b.psbt"],
        )

    def test_cancelled_confirmation_keeps_the_file(self):
        self._make_files("a.psbt")
        target = self.sdpath + "/a.psbt"
        self._gui(menu_results=[DELETE_ACTION, target, None], prompt_results=[False])

        _run(self.host.select_file(self.EXTENSIONS))

        self.assertTrue(platform.file_exists(target))

    def test_cancelling_the_delete_menu_returns_to_the_picker(self):
        self._make_files("a.psbt")
        target = self.sdpath + "/a.psbt"
        gui = self._gui(menu_results=[DELETE_ACTION, None, target])

        self.assertEqual(_run(self.host.select_file(self.EXTENSIONS)), target)
        self.assertTrue(platform.file_exists(target))
        self.assertEqual(len(gui.prompts), 0)

    def test_deleting_the_last_file_leaves_quietly(self):
        """Raising "no matching files" at the user after they deliberately
        deleted the last one would report their own action as an error."""
        self._make_files("a.psbt")
        target = self.sdpath + "/a.psbt"
        self._gui(menu_results=[DELETE_ACTION, target], prompt_results=[True])

        self.assertIsNone(_run(self.host.select_file(self.EXTENSIONS)))

    def test_a_failed_delete_is_reported_as_a_host_error(self):
        self._make_files("a.psbt")
        target = self.sdpath + "/a.psbt"
        self._gui(menu_results=[DELETE_ACTION, target], prompt_results=[True])

        real = platform.secure_delete_file

        def failing(path):
            raise OSError("simulated I/O failure")

        platform.secure_delete_file = failing
        try:
            with self.assertRaises(HostError):
                _run(self.host.select_file(self.EXTENSIONS))
        finally:
            platform.secure_delete_file = real
        self.assertTrue(platform.file_exists(target))


class FormatCardTest(_SDHostTestBase):
    def setUp(self):
        super().setUp()
        self.erase_calls = []
        self._real_sdcard = platform.sdcard

        test = self

        class _FakeCard:
            is_present = True

            async def erase_and_format(self, progress_cb=None):
                test.erase_calls.append(True)
                if progress_cb is not None:
                    await progress_cb(0.5)
                    await progress_cb(1.0)

            def mount(self):
                pass

            def unmount(self):
                pass

        platform.sdcard = _FakeCard()

    def tearDown(self):
        platform.sdcard = self._real_sdcard
        super().tearDown()

    def test_format_is_offered_from_the_delete_menu(self):
        self._make_files("a.psbt")
        gui = self._gui(menu_results=[DELETE_ACTION, None, None])

        _run(self.host.select_file(self.EXTENSIONS))

        values = [b[0] for b in gui.menus[1]["buttons"]]
        self.assertIn(FORMAT_ACTION, values)
        # last entry, in its own section, and marked as destructive
        button = gui.menus[1]["buttons"][values.index(FORMAT_ACTION)]
        self.assertEqual(values.index(FORMAT_ACTION), len(values) - 1)
        self.assertEqual(len(button), 4)  # (value, text, enabled, colour)

    def test_both_confirmations_are_required(self):
        self._make_files("a.psbt")
        # first prompt declined
        self._gui(menu_results=[DELETE_ACTION, FORMAT_ACTION, None], prompt_results=[False])
        _run(self.host.select_file(self.EXTENSIONS))
        self.assertEqual(self.erase_calls, [])

        # first accepted, second declined
        self._gui(
            menu_results=[DELETE_ACTION, FORMAT_ACTION, None],
            prompt_results=[True, False],
        )
        _run(self.host.select_file(self.EXTENSIONS))
        self.assertEqual(self.erase_calls, [])

    def test_confirmed_format_erases_the_card_and_stops_listing_it(self):
        """erase_and_format() leaves the card unmounted and powered down,
        so the picker must not go back and list it again."""
        self._make_files("a.psbt")
        gui = self._gui(
            menu_results=[DELETE_ACTION, FORMAT_ACTION], prompt_results=[True, True]
        )

        res = _run(self.host.select_file(self.EXTENSIONS))

        self.assertIsNone(res)
        self.assertEqual(len(self.erase_calls), 1)
        self.assertEqual(len(gui.menus), 2)  # picker, delete menu, and stop
        self.assertEqual(len(gui.alerts), 1)
        # the progress screen was driven by the erase
        self.assertEqual(gui.screens[0].progress, [0.5, 1.0])

    def test_a_failed_format_is_reported_as_a_host_error(self):
        self._make_files("a.psbt")
        self._gui(
            menu_results=[DELETE_ACTION, FORMAT_ACTION], prompt_results=[True, True]
        )

        async def failing(progress_cb=None):
            raise RuntimeError("card removed")

        platform.sdcard.erase_and_format = failing

        with self.assertRaises(HostError) as ctx:
            _run(self.host.select_file(self.EXTENSIONS))
        self.assertIn("card removed", str(ctx.exception))
