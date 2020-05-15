import utime as time
from platform import simulator, USB_ENABLED
import pyb

class USBHost:
    def __init__(self, callback=None):
        self.callback = callback
        self.data = ""
        if USB_ENABLED:
            self.usb = pyb.USB_VCP()
        # alternatively make EOL "\r" and strip "\n"
        # self.EOL = "\r\n"

    def process_data(self):
        if not USB_ENABLED:
            return
        if self.callback is None:
            self.data = ""
            return
        arr = self.data.split("\r")
        self.data = ""
        for e in arr:
            if e.endswith("\n"):
                e = e[:-1]
            if len(e) > 0:
                self.callback(e)

    def respond(self, data):
        if not USB_ENABLED:
            return
        self.usb.write(data)
        self.usb.write("\r\n")

    def update(self):
        if not USB_ENABLED:
            return
        res = self.usb.read()
        if res is not None and len(res) > 0:
            # if non-unicode character is found - fail right away
            # and clear buffer
            try:
                self.data += res.decode('utf-8')
            except:
                self.data = ""
        if "\r" in self.data:
            self.process_data()
