import asyncio
from platform import maybe_mkdir
from errors import BaseError


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
    # set the button on the main screen
    # should be a tuple (text, callback)
    # keep None if you don't need a button
    button = None

    def __init__(self, path):
        # storage for data
        self.path = path
        maybe_mkdir(path)
        # set manager
        self.manager = None
        # check this flag in update function
        # if disabled - throw all incoming data
        self.enabled = False
        self.initialized = False
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

    async def get_data(self):
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
