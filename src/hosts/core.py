import asyncio
from platform import maybe_mkdir

class HostError(Exception):
    """
    Host-specific error
    """
    pass

class Host:
    """
    Abstract Host class
    Manages communication with the host
    Can be unidirectional like QRHost
    or bidirectional like USBHost or SDHost
    """
    # command types
    UNKNOWN         = 0x00
    SIGN_PSBT       = 0x01
    ADD_WALLET      = 0x02
    VERIFY_ADDRESS  = 0x03
    UNKNOWN         = -1
    def __init__(self, path):
        # storage for data
        self.path = path
        maybe_mkdir(path)
        # set manager
        self.manager = None
        # set the button on the main screen
        # should be a tuple (text, callback)
        # keep None if you don't need a button
        self.button = None
        self.enabled = False

    def init(self):
        """
        Define here what should happen before ioloop starts
        Configure hardware, do selfchecks etc.
        """
        pass

    def start(self, manager, rate:int=10):
        self.manager = manager
        asyncio.create_task(self.update_loop(rate))

    async def update(self):
        """
        Define here what should happen in a loop
        Like fetch data from uart or usb.
        """
        pass

    async def update_loop(self, dt:int):
        while not self.enabled:
            await asyncio.sleep_ms(100)
        self.init()
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

    async def get_data(self):
        """Implement how to get transaction from unidirectional host"""
        raise HostError("Data loading is not implemented for this class")

    async def send_data(self, tx, fingerprint):
        """Implement how to send the signed transaction to the host"""
        raise HostError("Sending data is not implemented for this class")

    def user_canceled(self):
        """
        Define what should happen if user pressed cancel.
        Maybe you want to tell the host that user cancelled?
        """
        pass