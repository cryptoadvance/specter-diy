import utime as time
import sys
from platform import simulator
from io import BytesIO

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
        self.callback_animated_qr = None

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

    def start_scan(self, callback=None, callback_animated_qr=None, callback_animated_next=None, timeout=None):
        self.trigger_on()
        self.t0 = time.time()
        self.data = ""
        self.scanning = True
        self.callback = callback
        self.callback_animated_qr = callback_animated_qr
        self.callback_animated_next = callback_animated_next

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

    def update(self, cb_error=None):
        def process():
            assert cb_error != None, "callback missing"
            data = self.data[:-len(self.EOL)]
            self.reset()
            qr_anim = QRAnimated.process(data)
            # is this animated QR code
            if qr_anim is not None and self.callback_animated_qr is not None:
                data = qr_anim
                assert QRAnimated.indx[0] <= QRAnimated.indx[1], "QRAnim: encoding"
                if QRAnimated.prev_indx == []:
                    assert QRAnimated.indx[0] == 1, "QRAnim: wrong first code"
                else:
                    assert QRAnimated.indx[0] > QRAnimated.prev_indx[0], "QRAnim: wrong order"
                    assert QRAnimated.indx[1] == QRAnimated.prev_indx[1], "QRAnim: wrong code"
                self.callback_animated_qr(QRAnimated.indx, self.callback_animated_next)
                QRAnimated.prev_indx = QRAnimated.indx
                if QRAnimated.indx[0] is not QRAnimated.indx[1]:
                    return
            self.callback(data)
            QRAnimated.clean()
        try:
            if self.scanning:
                res = self.uart.read(self.uart.any())
                if len(res) > 0:
                    self.data += res.decode('utf-8')
                if self.is_done() and self.callback is not None:
                    process()
        except Exception as e:
            QRAnimated.clean()
            self.reset()
            b = BytesIO()
            sys.print_exception(e, b)
            cb_error("Something bad happened...\n\n%s" % b.getvalue().decode())

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

class QRAnimated:
    """
    Example of animated QR: "p1of3 payload"
    """
    # holds the current indices, e.g. for p1of3:  [1, 3]
    indx = []
    # holds the previous indices
    prev_indx = []
    # list of payloads of animated qr codes
    payload = []

    @staticmethod
    def process(data):
        if data.startswith('p'):
            datal = data.split(" ", 1)
            if len(datal) != 2:
                return None
            if "of" not in datal[0]:
                return None
            m = datal[0][1:].split("of")
            QRAnimated.indx = [int(m[0]), int(m[1])]
            QRAnimated.payload.append(datal[1])
            return "".join(QRAnimated.payload)
        return None

    @staticmethod
    def clean():
        QRAnimated.indx = []
        QRAnimated.prev_indx = []
        QRAnimated.payload = []
