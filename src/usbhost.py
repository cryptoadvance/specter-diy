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
        # alternatively make EOL "\r" and strip "\n"
        # self.EOL = "\r\n"

    def process_data(self):
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
        self.usb.write(data)
        self.usb.write("\r\n")

    def update(self):
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
