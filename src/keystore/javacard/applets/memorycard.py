from .secureapplet import SecureApplet, SecureError
from .applet import ISOException

class MemoryCardApplet(SecureApplet):
    GET_SECRET = b"\x05\x00"
    SET_SECRET = b"\x05\x01"
    def __init__(self, connection):
        aid = b"\xB0\x0B\x51\x11\xCB\x01"
        super().__init__(connection, aid)

    def save_secret(self, secret:bytes):
        return self.sc.request(self.SET_SECRET + secret)

    def get_secret(self):
        return self.sc.request(self.GET_SECRET)

    @property
    def is_empty(self):
        return True