from ..util import encode
from binascii import hexlify
from uscard import SmartcardException


class ISOException(Exception):
    pass


class AppletException(Exception):
    pass


class Applet:
    SELECT = b"\x00\xA4\x04\x00"  # select command

    def __init__(self, connection, aid):
        self.conn = connection
        self.aid = aid

    def select(self):
        self.request(self.SELECT + encode(self.aid))

    def request(self, apdu, retry=True):
        if not self.conn.isCardInserted():
            raise AppletException("Card is not present")
        data = self.conn.transmit(apdu)
        sw = bytes(data[-2:])
        if sw != b"\x90\x00":
            raise ISOException(hexlify(sw).decode())
        if isinstance(data[0], bytes):
            return data[0]
        else:
            return data[:-2]
