import asyncio

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
    def __init__(self, path):
        # storage for data
        self.path = path
        # set manager
        self.manager = None
        # set the button on the main screen
        # should be a tuple (text, callback)
        # keep None if you don't need a button
        self.button = None

    def init(self):
        """
        Define here what should happen before ioloop starts
        Configure hardware, do selfchecks etc.
        """
        pass

    def start(self, manager=None, rate:int=1):
        self.manager = manager
        self.init()
        asyncio.create_task(self.update_loop(rate))

    async def update(self):
        """
        Define here what should happen in a loop
        Like fetch data from uart or usb.
        """
        pass

    async def update_loop(self, dt):
        while True:
            await self.update()
            # Keep await sleep here
            # It allows other functions to run
            await asyncio.sleep_ms(dt)

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