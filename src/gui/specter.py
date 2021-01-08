from .async_gui import AsyncGUI
from .screens import (
    Screen,
    Progress,
    MnemonicScreen,
    NewMnemonicScreen,
    RecoverMnemonicScreen,
    DevSettings,
)
import rng
import asyncio


class SpecterGUI(AsyncGUI):
    """Specter-related GUI"""

    async def show_mnemonic(self, mnemonic: str):
        """
        Shows mnemonic on the screen
        """
        scr = MnemonicScreen(mnemonic)
        await self.load_screen(scr)
        return await scr.result()

    async def new_mnemonic(self, generator, wordlist, fix):
        """
        Generates a new mnemonic and shows it on the screen
        """
        scr = NewMnemonicScreen(generator, wordlist, fix)
        await self.load_screen(scr)
        return await scr.result()

    async def recover(self, checker=None, lookup=None, fix=None):
        """
        Asks the user for his recovery phrase.
        checker(mnemonic) - a function that validates recovery phrase
        lookup(word, num_candidates) - a function that
                returns num_candidates words starting with word
        """
        scr = RecoverMnemonicScreen(checker, lookup, fix)
        await self.load_screen(scr)
        return await scr.result()

    def set_network(self, net):
        """Changes color of the top line on all screens to network color"""
        Screen.network = net

    async def show_progress(self, host, title, message):
        """
        Shows progress screen and cancel button
        to cancel communication with the host
        """
        scr = Progress(title, message, button_text="Cancel")
        await self.open_popup(scr)
        asyncio.create_task(self.coro(host, scr))

    async def coro(self, host, scr):
        """
        Waits for one of two events:
        - either user presses something on the screen
        - or host finishes processing
        Also updates progress screen
        """
        while host.in_progress and scr.waiting:
            await asyncio.sleep_ms(30)
            scr.tick(5)
            scr.set_progress(host.progress)
        if host.in_progress:
            host.abort()
        if scr.waiting:
            scr.waiting = False
        await self.close_popup()

    async def devscreen(self, dev=False, usb=False, note=None):
        scr = DevSettings(dev=dev, usb=usb, note=note)
        await self.load_screen(scr)
        return await scr.result()
