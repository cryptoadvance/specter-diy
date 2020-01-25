import utime as time
from platform import simulator

if not simulator:
    import pyb
else:
    from unixport import pyb

class USBHost:
    def __init__(self, callback=None):
        self.usb = pyb.USB_VCP()
        self.callback = callback
        self.data = ""
        self.EOL = "\r"

    def process_data(self):
        if self.callback is None:
            self.data = ""
            return
        arr = self.data.split(self.EOL)
        self.data = ""
        for e in arr:
            if e.startswith("\n"):
                e = e[1:]
            if len(e) > 0:
                self.callback(e)

    def update(self):
        res = self.usb.read()
        if res is not None and len(res) > 0:
            self.data += res.decode('utf-8')
        if self.EOL in self.data:
            self.process_data()
