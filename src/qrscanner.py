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

# OK responce from scanner
SUCCESS        = b"\x02\x00\x00\x01\x00\x33\x31"
# serial port mode
SERIAL_ADDR    = b"\x00\x0D"
SERIAL_VALUE   = 0xA0 # use serial port for data
# command mode, light settings
SETTINGS_ADDR  = b"\x00\x00"
SETTINGS_VALUE = 0xD1 # use command mode + aim light, no flash light
# commands
SCAN_ADDR      = b"\x00\x02"
# timeout
TIMOUT_ADDR    = b"\x00\x06"

class QRScanner:
    def __init__(self, trigger=None, uart="YA", baudrate=9600):
        if simulator:
            self.EOL = "\r\n"
        else:
            self.EOL = "\r"
        
        self.uart = pyb.UART(uart, baudrate, read_buf_len=2048)
        self.uart.read(self.uart.any())

        self.trigger = None
        self.is_configured = False
        # we autoconfigure scanner before the first scan, 
        # as we don't know if scanner already got power or not
        # during the constructor
        # and if we have scanner at all
        if trigger is not None or simulator:
            self.trigger = pyb.Pin(trigger, pyb.Pin.OUT)
            self.trigger.on()
            self.is_configured = True

        self.scanning = False
        self.t0 = None
        self.callback = None

    def query(self, data):
        self.uart.write(data)
        t0 = time.time()
        while self.uart.any() < 7:
            time.sleep_ms(10)
            t = time.time()
            if t > t0+0.1:
                return None
        res = self.uart.read(7)
        return res

    def get_setting(self, addr):
        res = self.query(b"\x7E\x00\x07\x01"+addr+b"\x01\xAB\xCD")
        if res is None or len(res) != 7:
            return None
        return res[-3]

    def set_setting(self, addr, value):
        res = self.query(b"\x7E\x00\x08\x01"+addr+bytes([value])+b"\xAB\xCD")
        if res is None:
            return False
        return res == SUCCESS

    def save_settings(self):
        res = self.query(b"\x7E\x00\x09\x01\x00\x00\x00\xDE\xC8")
        if res is None:
            return False
        return res == SUCCESS

    def configure(self):
        """Tries to configure scanner, returns True on success"""
        save_required = False
        val = self.get_setting(SERIAL_ADDR)
        if val is None:
            return False
        if val & 0x3 != 0:
            self.set_setting(SERIAL_ADDR, val & 0xFC)
            save_required = True

        val = self.get_setting(SETTINGS_ADDR)
        if val is None:
            return False
        if val != SETTINGS_VALUE:
            self.set_setting(SETTINGS_ADDR, SETTINGS_VALUE)
            save_required = True

        val = self.get_setting(TIMOUT_ADDR)
        if val is None:
            return False
        if val != 0:
            self.set_setting(TIMOUT_ADDR, 0)
            save_required = True

        if save_required:
            val = self.save_settings()
            # some log
            if val:
                print("QR scanner is configured")
            else:
                print("Failed to configure scanner")
            return val
        return True

    def init(self):
        # if failed to configure - probably a different scanner
        # in this case fallback to PIN trigger mode
        if not self.configure():
            trigger = QRSCANNER_TRIGGER
            self.trigger = pyb.Pin(trigger, pyb.Pin.OUT)
            self.trigger.on()

    def trigger_on(self):
        if not self.is_configured:
            self.init()
            self.is_configured = True

        if self.trigger is not None:
            self.trigger.off()
        else:
            self.set_setting(SCAN_ADDR, 1)

    def trigger_reset(self):
        if self.trigger is not None:
            self.trigger.on()
        else:
            self.set_setting(SCAN_ADDR, 0)

    def start_scan(self, callback=None, timeout=None):
        self.trigger_on()
        self.t0 = time.time()
        self.data = ""
        self.scanning = True
        self.callback = callback

    def scan(self, timeout=None):
        self.trigger_on()
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
        self.trigger_reset()
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
        self.trigger_reset()

    def stop(self):
        self.reset()
        return self.data
