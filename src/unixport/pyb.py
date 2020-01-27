from micropython import const
from .tcphost import TCPHost
from binascii import hexlify

class Pin:
    IN = const(0)
    OUT = const(1)
    # other values?
    def __init__(self, name, *args, **kwargs):
        self._name = name

    def on(self):
        print("Pin", self._name, "set to ON")

    def off(self):
        print("Pin", self._name, "set to OFF")

class UART(TCPHost):
    def __init__(self, name, *args, **kwargs):
        # port will be 5941 for YA
        port = int(hexlify(name))
        super().__init__(port)
        print("Running TCP-UART on 127.0.0.1 port %d - connect with telnet" % port)

class USB_VCP(TCPHost):
    def __init__(self, *args, **kwargs):
        port = 8789
        super().__init__(port)
        print("Running TCP-USB_VCP on 127.0.0.1 port %d - connect with telnet" % port)

    def any(self):
        # USB_VCP returns a bool here
        return (super().any() > 0)
