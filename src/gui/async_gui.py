import asyncio
from .core import init, update
from .screens import MenuScreen, Alert, QRAlert
from .decorators import cb_with_args
import lvgl as lv

class AsyncGUI:

    def __init__(self):
        # unlock event for host signalling
        # to avoid spamming GUI
        self.waiting = False
        # only one popup can be active at a time
        # another screen goes to the background
        self.background = None

    def release(self, *args, **kwargs):
        """
        Unlocks the GUI
        """
        self.args = args
        self.kwargs = kwargs
        self.waiting = True

    def load_screen(self, scr):
        old_scr = lv.scr_act()
        lv.scr_load(scr)
        old_scr.del_async()

    async def open_popup(self, scr):
        # wait for another popup to finish
        while self.background is not None:
            await asyncio.sleep_ms(100)
        self.background = lv.scr_act()
        lv.scr_load(scr)

    def close_popup(self):
        self.load_screen(self.background)
        self.background = None

    def start(self, rate:int=30):
        init()
        asyncio.create_task(self.update_loop(rate))

    async def update_loop(self, dt):
        while True:
            update(dt)
            await asyncio.sleep_ms(dt)

    async def menu(self, buttons:list=[], title:str="What do you want to do?", last=None):
        """
        Creates a menu with buttons. 
        buttons argument should be a list of tuples:
        (value, text)
        value is retured when the button is pressed
        text is the text on the button

        If add_back_button is set to True,
        < Back button is added to the bottom of the screen
        and if it is pressed AsyncGUI.BTN_CLOSE is returned (-99)
        """
        menu = MenuScreen(buttons=buttons, title=title, last=last)
        self.load_screen(menu)
        return await menu.result()

    async def alert(self, title, msg, button_text="OK"):
        """
        Shows an alert.
        """
        alert = Alert(title, msg, button_text=button_text)
        self.load_screen(alert)
        await alert.result()

    async def qr_alert(self, title, msg, qr_msg, qr_width=None, button_text="OK"):
        """
        Shows an alert.
        """
        alert = QRAlert(title, msg, qr_msg, qr_width=qr_width, button_text=button_text)
        self.load_screen(alert)
        await alert.result()

    async def error(self, msg):
        """
        Shows an error.
        """
        await self.alert("Error!", msg, button_text="OK")
