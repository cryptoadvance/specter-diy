import asyncio
from .core import init, update
from .screens import Menu, Alert, QRAlert, Prompt, InputScreen
from .components.modal import Modal
from .components.battery import Battery
import lvgl as lv


class AsyncGUI:
    def __init__(self):
        # unlock event for host signalling
        # to avoid spamming GUI
        self.waiting = False
        # only one popup can be active at a time
        # another screen goes to the background
        self.background = None
        self.scr = None
        self.battery_callback = None
        self.battery_interval = 1000

    def set_battery_callback(self, cb, dt=1000):
        self.battery_callback = cb
        self.battery_interval = dt

    def release(self, *args, **kwargs):
        """
        Unlocks the GUI
        """
        self.args = args
        self.kwargs = kwargs
        self.waiting = True

    def show_loader(self,
                    text="Please wait until the process is complete.",
                    title="Processing..."):
        if self.scr is not None:
            self.scr.show_loader(text, title)

    def hide_loader(self):
        if self.scr is None:
            return
        self.scr.hide_loader()
        if self.background is not None:
            self.background.hide_loader()

    async def load_screen(self, scr):
        while self.background is not None:
            await asyncio.sleep_ms(10)
        old_scr = lv.screen_active()
        lv.screen_load(scr)
        self.scr = scr
        old_scr.delete_async()

    async def open_popup(self, scr):
        # wait for another popup to finish
        while self.background is not None:
            await asyncio.sleep_ms(10)
        self.background = self.scr
        self.scr = scr
        lv.screen_load(scr)

    async def close_popup(self):
        scr = self.background
        self.background = None
        await self.load_screen(scr)

    def show_screen(self, popup=False):
        """
        Return a function to show a new screen
        as a popup or not
        """

        async def fn(scr):
            if popup:
                await self.open_popup(scr)
            else:
                await self.load_screen(scr)
            res = await scr.result()
            if popup:
                await self.close_popup()
            return res

        return fn

    async def get_input(
        self,
        title="Enter your BIP-39 password:",
        note="This password creates a completely different set of keys\n"
             "and it is never stored on the device. Don't forget it!",
        suggestion="",
    ):
        """
        Asks the user for a password
        """
        scr = InputScreen(title, note, suggestion)
        await self.load_screen(scr)
        return await scr.result()

    def start(self, rate: int = 30, dark=True):
        init(dark=dark)
        asyncio.create_task(self.update_loop(rate))
        if self.battery_callback is not None and self.battery_interval is not None:
            asyncio.create_task(self.update_battery(self.battery_interval))

    async def update_battery(self, dt):
        while True:
            level, charging = self.battery_callback()
            if level is None:
                return
            Battery.VALUE = level
            Battery.CHARGING = charging
            if self.scr is not None and hasattr(self.scr, "battery"):
                self.scr.battery.update()
            await asyncio.sleep_ms(dt)

    async def update_loop(self, dt):
        while True:
            update(dt)
            await asyncio.sleep_ms(dt)

    async def menu(
        self,
        buttons: list = [],
        title: str = "What do you want to do?",
        note=None,
        last=None,
    ):
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
        menu = Menu(buttons=buttons, title=title, note=note, last=last)
        await self.load_screen(menu)
        return await menu.result()

    async def alert(self, title, msg, button_text="OK", note=None):
        """Shows an alert"""
        alert = Alert(title, msg, button_text=button_text, note=note)
        await self.load_screen(alert)
        await alert.result()

    async def qr_alert(
        self, title, msg, qr_msg, qr_width=None, button_text="OK", note=None
    ):
        """Shows an alert with QR code"""
        alert = QRAlert(
            title, msg, qr_msg, qr_width=qr_width, button_text=button_text, note=note
        )
        await self.load_screen(alert)
        return await alert.result()

    async def error(self, msg, popup=False):
        """Shows an error"""
        alert = Alert("Error!", msg, button_text="OK")
        if popup:
            await self.open_popup(alert)
        else:
            await self.load_screen(alert)
        res = await alert.result()
        if popup:
            await self.close_popup()
        return res

    async def prompt(self, title, msg, popup=False):
        """Asks the user to confirm action"""
        scr = Prompt(title, msg)
        if popup:
            await self.open_popup(scr)
        else:
            await self.load_screen(scr)
        res = await scr.result()
        if popup:
            await self.close_popup()
        return res
