from .async_gui import AsyncGUI
from .screens import (Screen, PinScreen, 
                      MnemonicScreen, NewMnemonicScreen, RecoverMnemonicScreen,
                      PasswordScreen,
                      )
import rng

class SpecterGUI(AsyncGUI):

    async def get_pin(self, title="Enter your PIN code", get_word=None):
        """
        Async version of the PIN screen.
        Waits for an event that is set in the callback.
        """
        pin_scr = PinScreen(title=title, 
            note="Do you recognize these words?", 
            get_word=get_word)
        self.load_screen(pin_scr)
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
        self.load_screen(pin_scr)
        
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
        self.load_screen(scr)
        return await scr.result()

    async def new_mnemonic(self, generator):
        """
        Generates a new mnemonic and shows it on the screen
        """
        scr = NewMnemonicScreen(generator)
        self.load_screen(scr)
        return await scr.result()

    async def recover(self, checker=None, lookup=None):
        """
        Asks the user for his recovery phrase.
        checker(mnemonic) - a function that validates recovery phrase
        lookup(word, num_candidates) - a function that 
                returns num_candidates words starting with word
        """
        scr = RecoverMnemonicScreen(checker, lookup)
        self.load_screen(scr)
        return await scr.result()

    async def get_password(self):
        """
        Asks the user for a password
        """
        scr = PasswordScreen()
        self.load_screen(scr)
        return await scr.result()

    def set_network(self, net):
        Screen.network = net