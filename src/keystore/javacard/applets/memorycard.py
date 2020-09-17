from .secureapplet import SecureApplet, SecureException
from .applet import ISOException

class MemoryCardApplet(SecureApplet):
    def __init__(self, connection):
        aid = b"\xB0\x0B\x51\x11\xCB\x01"
        super().__init__(connection, aid)

    def save_secret(self):
        pass

    def get_secret(self, secret):
        pass

    @property
    def is_empty(self):
        return True