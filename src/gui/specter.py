from .async_gui import AsyncGUI
from .screens import (Screen, PinScreen, Progress,
                      MnemonicScreen, NewMnemonicScreen, RecoverMnemonicScreen,
                      InputScreen, XPubScreen, DerivationScreen, WalletScreen,
                      TransactionScreen, ConfirmWalletScreen)
import rng, asyncio

class SpecterGUI(AsyncGUI):
    """Specter-related GUI"""
    async def get_pin(self, title="Enter your PIN code", get_word=None):
        """
        Async version of the PIN screen.
        Waits for an event that is set in the callback.
        """
        pin_scr = PinScreen(title=title, 
            note="Do you recognize these words?", 
            get_word=get_word)
        await self.load_screen(pin_scr)
        return await pin_scr.result()

    async def setup_pin(self, get_word=None):
        """
        PIN setup screen - first choose, then confirm
        If PIN codes are the same -> return the PIN
        If not -> try again
        """
        pin_scr = PinScreen(title="Choose your PIN code", 
            note="Remember these words, they will stay the same on this device.", 
            get_word=get_word)
        await self.load_screen(pin_scr)
        
        pin1 = await pin_scr.result()

        pin_scr.reset()
        pin_scr.title.set_text("Confirm your PIN code")
        pin2 = await pin_scr.result()

        # check if PIN is the same
        if pin1 == pin2:
            return pin1
        # if not - show an error
        await self.error("PIN codes are different!")
        return await self.setup_pin(get_word)

    async def show_mnemonic(self, mnemonic:str):
        """
        Shows mnemonic on the screen
        """
        scr = MnemonicScreen(mnemonic)
        await self.load_screen(scr)
        return await scr.result()

    async def new_mnemonic(self, generator):
        """
        Generates a new mnemonic and shows it on the screen
        """
        scr = NewMnemonicScreen(generator)
        await self.load_screen(scr)
        return await scr.result()

    async def recover(self, checker=None, lookup=None):
        """
        Asks the user for his recovery phrase.
        checker(mnemonic) - a function that validates recovery phrase
        lookup(word, num_candidates) - a function that 
                returns num_candidates words starting with word
        """
        scr = RecoverMnemonicScreen(checker, lookup)
        await self.load_screen(scr)
        return await scr.result()

    async def get_input(self):
        """
        Asks the user for a password
        """
        scr = InputScreen()
        await self.load_screen(scr)
        return await scr.result()

    def set_network(self, net):
        """Changes color of the top line on all screens to network color"""
        Screen.network = net

    async def get_derivation(self, title="Enter derivation path"):
        """Asks user to enter derivation path"""
        scr = DerivationScreen(title=title)
        await self.load_screen(scr)
        return await scr.result()

    async def show_xpub(self, xpub, slip132=None, prefix=None, 
                    title="Your master public key"):
        """Shows xpub with slip132 and prefix switches"""
        scr = XPubScreen(xpub=xpub, slip132=slip132, prefix=prefix, title=title)
        await self.load_screen(scr)
        return await scr.result()

    async def show_wallet(self, w, network, idx=None):
        scr = WalletScreen(w, network, idx=idx)
        await self.load_screen(scr)
        return await scr.result()

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
        self.close_popup()

    async def confirm_transaction(self, wallet_name, meta):
        scr = TransactionScreen(wallet_name, meta)
        await self.load_screen(scr)
        return await scr.result()

    async def confirm_new_wallet(self, name, policy, keys):
        scr = ConfirmWalletScreen(name, policy, keys)
        await self.load_screen(scr)
        return await scr.result()