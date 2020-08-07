from .applet import Applet, ISOException
from .securechannel import SecureChannel

class SecureException(Exception):
    """
    Raised when exception was on the card, 
    but not due to the secure channel
    """
    pass

class SecureApplet(Applet):
    SECURE_RANDOM = b"\x01\x00"
    PIN_STATUS    = b"\x03\x00"

    def __init__(self, connection, aid):
        super().__init__(connection, aid)
        # secure channel
        self.sc = SecureChannel(self)
        self._pin_attempts_left = None
        self._pin_attempts_max = None
        self._pin_status = None

    def open_secure_channel(self):
        self.sc.open()

    def close_secure_channel(self):
        self.sc.close()

    @property
    def is_secure_channel_open(self):
        return self.sc.is_open

    def _get_pin_status(self):
        status = self.sc.request(self.PIN_STATUS)
        (self._pin_attempts_left, 
         self._pin_attempts_max, 
         self.pin_status) = list(status)
        return tuple(status)

    def get_random(self):
        return self.sc.request(self.SECURE_RANDOM)

    @property
    def is_pin_set(self):
        if self._pin_status is None:
            self._get_pin_status()
        return self._pin_status > 0
