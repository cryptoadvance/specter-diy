from .core import Host, HostError
import asyncio
from platform import simulator
from io import BytesIO
from binascii import b2a_base64, a2b_base64
import time
import pyb

QRSCANNER_TRIGGER = "D5"
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

class QRHost(Host):
    """
    QRHost class.
    Manages QR code scanner:
    - scan unsigned transaction and authentications
    - trigger display of the signed transaction
    """
    def __init__(self, trigger=None, uart="YA", baudrate=9600):
        super().__init__()
        self.button = "Scan QR code"

        if simulator:
            self.EOL = "\r\n"
            self.UART_EMPTY = b""
        else:
            self.EOL = "\r"
            self.UART_EMPTY = None

        self.data = b""
        self.uart_bus = uart
        self.uart = pyb.UART(uart, baudrate, read_buf_len=2048)
        self.trigger = None
        self.is_configured = False
        if trigger is not None or simulator:
            self.trigger = pyb.Pin(trigger, pyb.Pin.OUT)
            self.trigger.on()
            self.is_configured = True
        self.init()
        self.scanning = False

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
        self.uart = pyb.UART(self.uart_bus, 115200, read_buf_len=2048)
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
            self.uart = pyb.UART(self.uart_bus, 115200, read_buf_len=2048)
            self.clean_uart()
            self.is_configured = self.configure()
            if self.is_configured:
                print("Scanner: automatic mode")
                return

            # PIN trigger mode
            self.uart = pyb.UART(self.uart_bus, 9600, read_buf_len=2048)
            self.trigger = pyb.Pin(QRSCANNER_TRIGGER, pyb.Pin.OUT)
            self.trigger.on()
            self.is_configured = True
            print("Scanner: Pin trigger mode")

    def stop_scanning(self):
        self.set_setting(SETTINGS_ADDR, SETTINGS_CMD_MODE)
        self.scanning = False

    def clean_uart(self):
        self.uart.read()

    def stop_scanning(self):
        self.scanning = False
        self.set_setting(SETTINGS_ADDR, SETTINGS_CMD_MODE)

    async def scan(self):
        self.clean_uart()
        if self.trigger is not None:
            self.trigger.off()
        else:
            self.set_setting(SETTINGS_ADDR, SETTINGS_CONT_MODE)
        self.data = b""
        self.scanning = True
        while self.scanning:
            # read all available data
            res = self.uart.read()
            if res is not None:
                if res.endswith(self.EOL):
                    # check if it is animated
                    if res.startswith(b'p'):
                        self.stop_scanning()
                        raise HostError("Animated QR codes are not supported yet")
                    self.data += res[:-len(self.EOL)]
                    self.stop_scanning()
                    return self.data
                else:
                    self.data += res
            await asyncio.sleep_ms(10)
        # raise if scan was interrupted
        raise HostError("Scan failed")

    async def get_data(self):
        # scan_progress is a QR scanning specific screen
        # that shows that QR code(s) is being scanned
        # and displays cancel button that calls self.stop_scanning()
        # self.manager.scan_progress([])
        data = await self.scan()
        tx, auths = data.split(b" ")
        tx = a2b_base64(tx)
        auths = a2b_base64(auths)
        mvtx = memoryview(tx)
        mvauths = memoryview(auths)
        sigs = []
        b = BytesIO(auths)
        cur = 0
        while True:
            bb = b.read(1)
            # cant read? - done
            if len(bb) == 0:
                break
            cur += 1
            l = bb[0]
            # ignore empty sig
            if l == 0:
                continue
            b.read(l)
            sigs.append(BytesIO(mvauths[cur:cur+l]))
            cur += l
        return BytesIO(mvtx), sigs

    async def send_data(self, tx, fingerprint=None):
        tx.unknown = {}
        for inp in tx.inputs:
            inp.unknown = {}
        for out in tx.outputs:
            out.unknown = {}
        txt = b2a_base64(tx.serialize()).decode().strip("\n")
        if self.manager is not None:
            await self.manager.gui.qr_alert("Transaction is signed!", 
                        "Scan this QR code with your wallet", txt, qr_width=450)
