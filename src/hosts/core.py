import asyncio
from platform import maybe_mkdir
from errors import BaseError
import json
from gui.screens.settings import HostSettings
from gui.screens import Alert

class HostError(BaseError):
    NAME = "Host error"


class Host:
    """
    Abstract Host class
    Manages communication with the host
    Can be unidirectional like QRHost
    or bidirectional like USBHost or SDHost
    """

    # time to wait after init
    RECOVERY_TIME = 1
    # store device settings here with unique filename
    # common for all hosts
    SETTINGS_DIR = None
    # set the button on the main screen
    # should be a tuple (text, callback)
    # keep None if you don't need a button
    button = None
    # button text for settings menu, None if nothing to configure
    settings_button = None
    # link to specter instance
    parent = None

    def __init__(self, path):
        # storage for data
        self.path = path
        maybe_mkdir(path)
        if self.SETTINGS_DIR:
            maybe_mkdir(self.SETTINGS_DIR)
        # set manager
        self.manager = None
        # check this flag in update function
        # if disabled - throw all incoming data
        self.enabled = False
        self.initialized = False
        # default settings, extend it with more settings if applicable
        self.settings = { "enabled": True }
        # if host can be triggered by the user
        # this is monitored by the manager
        # self.in_progress = False
        # this is the current state of the host
        # can be a float between 0 and 1 or
        # a list of [True, False, ...] (for QR code)
        # self.progress = 0

    def init(self):
        """
        Define here what should happen when host is initialized
        Configure hardware, do selfchecks etc.
        """
        pass

    @property
    def is_enabled(self):
        return self.settings.get("enabled", True)

    @property
    def settings_fname(self):
        return self.SETTINGS_DIR + "/" + type(self).__name__ + ".settings"

    def load_settings(self, keystore):
        try:
            adata, _ = keystore.load_aead(self.settings_fname, key=keystore.settings_key)
            settings = json.loads(adata.decode())
            self.settings = settings
        except Exception as e:
            print(e)
        return self.settings

    def save_settings(self, keystore):
        keystore.save_aead(self.settings_fname,
                           adata=json.dumps(self.settings).encode(),
                           key=keystore.settings_key
        )

    async def settings_menu(self, show_screen, keystore):
        title = self.settings_button or "Settings"
        controls = [{
            "label": "Enable " + title,
            "hint": "This setting will completely enable or disable this communication channel and remove corresponding button from the main menu",
            "value": self.settings["enabled"]
        }]
        scr = HostSettings(controls, title=title)
        res = await show_screen(scr)
        if res:
            self.settings["enabled"] = res[0]
            self.save_settings(keystore)
            await show_screen(Alert("Success!", "\n\nSettings updated!", button_text="Close"))

    def start(self, manager, rate: int = 10):
        self.manager = manager
        asyncio.create_task(self.update_loop(rate))

    async def update(self):
        """
        Define here what should happen in a loop
        Like fetch data from uart or usb.
        """
        pass

    async def update_loop(self, dt: int):
        while not self.enabled:
            await asyncio.sleep_ms(100)
        while True:
            if self.enabled:
                try:
                    await self.update()
                except Exception as e:
                    self.abort()
                    if self.manager is not None:
                        await self.manager.host_exception_handler(e)
            # Keep await sleep here
            # It allows other functions to run
            await asyncio.sleep_ms(dt)

    def abort(self):
        """What should happen if exception?"""
        pass

    async def enable(self):
        """
        What should happen when host enables?
        Maybe you want to remove all pending data first?
        """
        if not self.initialized:
            self.init()
            await asyncio.sleep_ms(self.RECOVERY_TIME)
            self.initialized = True
        self.enabled = True

    async def disable(self):
        """
        What should happen when host disables?
        """
        self.enabled = False

    async def get_data(self, raw=False, chunk_timeout=0.1):
        """Implement how to get transaction from unidirectional host"""
        raise HostError("Data loading is not implemented for this class")

    async def send_psbt(self, psbt):
        """Implement how to send the signed transaction to the host"""
        raise HostError("Sending data is not implemented for this class")

    def user_canceled(self):
        """
        Define what should happen if user pressed cancel.
        Maybe you want to tell the host that user cancelled?
        """
        pass
