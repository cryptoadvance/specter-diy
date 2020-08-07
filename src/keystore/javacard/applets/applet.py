from ..util import encode
from binascii import hexlify

class ISOException(Exception):
    pass

class Applet:
    SELECT = b"\x00\xA4\x04\x00" # select command
    def __init__(self, connection, aid):
        self.conn = connection
        self.aid = aid

    def select(self):
        self.request(self.SELECT + encode(self.aid))

    def request(self, apdu):
        data = self.conn.transmit(apdu)
        sw = data[-2:]
        if sw!=b"\x90\x00":
            raise ISOException(hexlify(sw).decode())
        return data[:-2]
