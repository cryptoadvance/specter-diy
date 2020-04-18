import utime as time
import sys
from platform import simulator
from io import BytesIO
from ubinascii import hexlify

if not simulator:
    import pyb
else:
    from unixport import pyb

QRSCANNER_TRIGGER = "D5"

try:
    from config import QRSCANNER_TRIGGER
except:
    pass

# OK response from scanner
SUCCESS        = b"\x02\x00\x00\x01\x00\x33\x31"
# serial port mode
SERIAL_ADDR    = b"\x00\x0D"
SERIAL_VALUE   = 0xA0 # use serial port for data

""" We switch the scanner to continuous mode to initiate scanning and
to command mode to stop scanning. No external trigger is necessary """
SETTINGS_ADDR  = b"\x00\x00"
SETTINGS_CMD_MODE = 0xD1 # use command mode + aim light, no flash light
SETTINGS_CONT_MODE = 0xD2 # use continuous mode + aim light, no flash light

""" After basic scanner configuration (9600 bps) uart is set to 115200 bps
to support fast scanning of animated qrs """
BAUD_RATE_ADDR = b"\x00\x2A"
BAUD_RATE = b"\x1A\x00" # 115200

# commands
SCAN_ADDR      = b"\x00\x02"
# timeout
TIMOUT_ADDR    = b"\x00\x06"

""" After the scanner obtains a scan it waits 100ms and starts a new scan."""
INTERVAL_OF_SCANNING_ADDR = b"\x00\x05"
INTERVAL_OF_SCANNING = 0x01 # 100ms

""" DELAY_OF_SAME_BARCODES of 5 seconds means scanning the same barcode again
(and sending it over uart) can happen only when the interval times out or resets
which happens if we scan a different qr code. """
DELAY_OF_SAME_BARCODES_ADDR = b"\x00\x13"
DELAY_OF_SAME_BARCODES = 0x85 # 5 seconds


class QRScanner:
    uart_bus = None
    def __init__(self, trigger=None, uart="YA", baudrate=9600):
        if simulator:
            self.EOL = "\r\n"
            self.UART_EMPTY = b""
        else:
            self.EOL = "\r"
            self.UART_EMPTY = None
        QRScanner.uart_bus = uart
        self.uart = pyb.UART(uart, baudrate, read_buf_len=2048)
        self.trigger = None
        self.is_configured = False
        if trigger is not None or simulator:
            self.trigger = pyb.Pin(trigger, pyb.Pin.OUT)
            self.trigger.on()
            self.is_configured = True
        self.init()
        self.scanning = False
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
        # only for 1 byte settings
        res = self.query(b"\x7E\x00\x07\x01"+addr+b"\x01\xAB\xCD")
        if res is None or len(res) != 7:
            return None
        return res[-3]

    def set_setting(self, addr, value):
        # only for 1 byte settings
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
        if val != SETTINGS_CMD_MODE:
            self.set_setting(SETTINGS_ADDR, SETTINGS_CMD_MODE)
            save_required = True

        val = self.get_setting(TIMOUT_ADDR)
        if val is None:
            return False
        if val != 0:
            self.set_setting(TIMOUT_ADDR, 0)
            save_required = True

        val = self.get_setting(INTERVAL_OF_SCANNING_ADDR)
        if val is None:
            return False
        if val != INTERVAL_OF_SCANNING:
            self.set_setting(INTERVAL_OF_SCANNING_ADDR, INTERVAL_OF_SCANNING)
            save_required = True

        val = self.get_setting(DELAY_OF_SAME_BARCODES_ADDR)
        if val is None:
            return False
        if val != DELAY_OF_SAME_BARCODES:
            self.set_setting(DELAY_OF_SAME_BARCODES_ADDR, DELAY_OF_SAME_BARCODES)
            save_required = True

        if save_required:
            val = self.save_settings()
            if not val:
                return False

        # Set 115200 bps: this query is special - it has a payload of 2 bytes
        ret = self.query(b"\x7E\x00\x08\x02"+BAUD_RATE_ADDR+BAUD_RATE+b"\xAB\xCD")
        if ret != SUCCESS:
            return False
        self.uart = pyb.UART(QRScanner.uart_bus, 115200, read_buf_len=2048)
        return True

    def init(self):
        # if failed to configure - probably a different scanner
        # in this case fallback to PIN trigger mode FIXME
        if self.is_configured == False:
            self.clean_uart()
            self.is_configured = self.configure()
            if self.is_configured:
                print("Scanner: automatic mode")
                return

            # Try one more time with different baudrate
            self.uart = pyb.UART(QRScanner.uart_bus, 115200, read_buf_len=2048)
            self.clean_uart()
            self.is_configured = self.configure()
            if self.is_configured:
                print("Scanner: automatic mode")
                return

            # PIN trigger mode
            self.uart = pyb.UART(QRScanner.uart_bus, 9600, read_buf_len=2048)
            self.trigger = pyb.Pin(QRSCANNER_TRIGGER, pyb.Pin.OUT)
            self.trigger.on()
            self.is_configured = True
            print("Scanner: Pin trigger mode")

    def stop_scanning(self):
        self.set_setting(SETTINGS_ADDR, SETTINGS_CMD_MODE)

    def clean_uart(self):
        self.uart.read()

    def start_scan(self, callback=None):
        if self.trigger is not None:
            self.trigger.off()
        else:
            self.clean_uart()
            self.set_setting(SETTINGS_ADDR, SETTINGS_CONT_MODE)
        QRAnimated.clean()
        self.data = ""
        self.scanning = True
        self.callback = callback

    def update(self, cb_error=None):
        def process():
            assert cb_error != None, "callback missing"
            data = self.data[:-len(self.EOL)]
            self.data = ""
            if self.EOL in data:
                """ when scanning qrs fast many at once can be read.
                We split and handle them all """
                data = data.split(self.EOL)
                for w in data:
                    qr_anim = QRAnimated.process(w, self.trigger)
                    if qr_anim != "skip" and qr_anim != None:
                        # animated qr assembled
                        break
            else:
                qr_anim = QRAnimated.process(data, self.trigger)
            if qr_anim == "skip":
                return
            # is this animated QR code
            if qr_anim != None:
                data = qr_anim
            self.stop()
            self.callback(data)
        try:
            if self.scanning:
                res = self.uart.read()
                if not simulator and res is self.UART_EMPTY:
                    res = b""
                if len(res) > 0:
                    self.data += res.decode('utf-8')
                if self.is_done() and self.callback is not None:
                    process()
        except Exception as e:
            QRAnimated.clean()
            self.stop()
            b = BytesIO()
            sys.print_exception(e, b)
            cb_error("Something bad happened...\n\n%s" % b.getvalue().decode())

    def is_done(self):
        return self.data.endswith(self.EOL)

    def stop(self):
        QRAnimated.clean()
        self.scanning = False
        self.data = ""
        if self.trigger is not None:
            self.trigger.on()
        else:
            self.stop_scanning()

class QRAnimated:
    """
    Example of animated QR: "p1of3 payload"
    """
    # holds the current indices, e.g. for p1of3:  [1, 3]
    indx = []
    # list of payloads of animated qr codes
    payload = []

    @staticmethod
    def process(data, trigger_mode):
        if data.startswith('p'):
            # This is probably an animated qr
            datal = data.split(" ", 1)
            if len(datal) != 2:
                return None
            if "of" not in datal[0]:
                return None
            # This is definitely an animated qr
            # PIN trigger mode does not support animated qrs except with Simulator
            if not simulator:
                assert trigger_mode == None, \
                       "Your scanner does not support animated QRs!"
            m = datal[0][1:].split("of")
            ind = [int(m[0]), int(m[1])]
            if QRAnimated.indx == []:
                QRAnimated.payload = [None] * ind[1]
            elif QRAnimated.payload[ind[0]-1] != None:
                # we already have this part
                return "skip"
            QRAnimated.indx = ind
            QRAnimated.payload[ind[0]-1] = datal[1]
            if None in QRAnimated.payload:
                # we are still missing some parts, cant assemble yet
                return "skip"
            # return fully assembled qr code
            return "".join(QRAnimated.payload)
        # This is not an animated qr but a normal one
        return None

    @staticmethod
    def clean():
        QRAnimated.indx = []
        QRAnimated.payload = []
