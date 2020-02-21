import utime as time
from platform import simulator

if not simulator:
    import pyb
else:
    from unixport import pyb

QRSCANNER_TRIGGER = "D5"
try:
    from config import QRSCANNER_TRIGGER
except:
    pass

class QRScanner:
    def __init__(self, trigger=QRSCANNER_TRIGGER, uart="YA", baudrate=9600):
        if simulator:
            self.EOL = "\r\n"
        else:
            self.EOL = "\r"
        self.trigger = pyb.Pin(trigger, pyb.Pin.OUT)
        self.trigger.on()
        self.uart = pyb.UART(uart, baudrate, read_buf_len=1024)
        self.uart.read(self.uart.any())
        self.scanning = False
        self.t0 = None
        self.callback = None

    def start_scan(self, callback=None, timeout=None):
        self.trigger.off()
        self.t0 = time.time()
        self.data = ""
        self.scanning = True
        self.callback = callback

    def scan(self, timeout=None):
        self.trigger.off()
        r = ""
        t0 = time.time()
        while len(r)==0 or not r.endswith(self.EOL):
            res = self.uart.read(self.uart.any())
            if len(res) > 0:
                r += res.decode('utf-8')
            time.sleep(0.01)
            if timeout is not None:
                if time.time() > t0+timeout:
                    break
        self.trigger.on()
        if r.endswith(self.EOL):
            return r[:-len(self.EOL)]
        return r

    def update(self):
        if self.scanning:
            res = self.uart.read(self.uart.any())
            if len(res) > 0:
                self.data += res.decode('utf-8')
            if self.is_done() and self.callback is not None:
                data = self.data[:-len(self.EOL)]
                self.reset()
                self.callback(data)

    def is_done(self):
        return self.data.endswith(self.EOL)

    def reset(self):
        self.scanning = False
        self.data = ""
        self.t0 = None
        self.trigger.on()

    def stop(self):
        self.reset()
        return self.data
