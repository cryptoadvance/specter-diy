from .core import Host, HostError
import pyb
import time
import asyncio
from platform import simulator, config
from io import BytesIO
import gc

QRSCANNER_TRIGGER = config.QRSCANNER_TRIGGER
# OK response from scanner
SUCCESS = b"\x02\x00\x00\x01\x00\x33\x31"
# serial port mode
SERIAL_ADDR = b"\x00\x0D"
SERIAL_VALUE = 0xA0  # use serial port for data

""" We switch the scanner to continuous mode to initiate scanning and
to command mode to stop scanning. No external trigger is necessary """
SETTINGS_ADDR = b"\x00\x00"
SETTINGS_CMD_MODE = 0xD1  # use command mode + aim light, no flash light
SETTINGS_CONT_MODE = 0xD2  # use continuous mode + aim light, no flash light

""" After basic scanner configuration (9600 bps) uart is set to 115200 bps
to support fast scanning of animated qrs """
BAUD_RATE_ADDR = b"\x00\x2A"
BAUD_RATE = b"\x1A\x00"  # 115200

# commands
SCAN_ADDR = b"\x00\x02"
# timeout
TIMOUT_ADDR = b"\x00\x06"

""" After the scanner obtains a scan it waits 100ms and starts a new scan."""
INTERVAL_OF_SCANNING_ADDR = b"\x00\x05"
INTERVAL_OF_SCANNING = 0x01  # 100ms

""" DELAY_OF_SAME_BARCODES of 5 seconds means scanning the same barcode again
(and sending it over uart) can happen only when the interval times out or resets
which happens if we scan a different qr code. """
DELAY_OF_SAME_BARCODES_ADDR = b"\x00\x13"
DELAY_OF_SAME_BARCODES = 0x85  # 5 seconds


class QRHost(Host):
    """
    QRHost class.
    Manages QR code scanner:
    - scan unsigned transaction and authentications
    - trigger display of the signed transaction
    """

    # time to wait after init
    RECOVERY_TIME = 30

    button = "Scan QR code"

    def __init__(self, path, trigger=None, uart="YA", baudrate=9600):
        super().__init__(path)

        if simulator:
            self.EOL = b"\r\n"
        else:
            self.EOL = b"\r"

        self.data = b""
        self.uart_bus = uart
        self.uart = pyb.UART(uart, baudrate, read_buf_len=2048)
        if simulator:
            print("Connect to 127.0.0.1:22849 to send QR code content")
        self.trigger = None
        self.is_configured = False
        if trigger is not None or simulator:
            self.trigger = pyb.Pin(trigger, pyb.Pin.OUT)
            self.trigger.on()
            self.is_configured = True
        self.scanning = False
        self.parts = None

    def query(self, data, timeout=100):
        """Blocking query"""
        self.uart.write(data)
        t0 = time.time()
        while self.uart.any() < 7:
            time.sleep_ms(10)
            t = time.time()
            if t > t0 + timeout / 1000:
                return None
        res = self.uart.read(7)
        return res

    def get_setting(self, addr):
        # only for 1 byte settings
        res = self.query(b"\x7E\x00\x07\x01" + addr + b"\x01\xAB\xCD")
        if res is None or len(res) != 7:
            return None
        return res[-3]

    def set_setting(self, addr, value):
        # only for 1 byte settings
        res = self.query(b"\x7E\x00\x08\x01" + addr + bytes([value]) + b"\xAB\xCD")
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
        ret = self.query(b"\x7E\x00\x08\x02" + BAUD_RATE_ADDR + BAUD_RATE + b"\xAB\xCD")
        if ret != SUCCESS:
            return False
        self.uart.deinit()
        self.uart.init(baudrate=115200, read_buf_len=2048)
        return True

    def init(self):
        if self.is_configured:
            return
        # if failed to configure - probably a different scanner
        # in this case fallback to PIN trigger mode FIXME
        self.clean_uart()
        self.is_configured = self.configure()
        if self.is_configured:
            return

        # Try one more time with different baudrate
        self.uart.deinit()
        self.uart.init(baudrate=115200, read_buf_len=2048)
        self.clean_uart()
        self.is_configured = self.configure()
        if self.is_configured:
            return

        # PIN trigger mode
        self.uart.deinit()
        self.uart.init(baudrate=9600, read_buf_len=2048)
        self.trigger = pyb.Pin(QRSCANNER_TRIGGER, pyb.Pin.OUT)
        self.trigger.on()
        self.is_configured = True
        pyb.LED(3).on()

    def clean_uart(self):
        self.uart.read()

    def stop_scanning(self):
        self.scanning = False
        if self.trigger is not None:
            self.trigger.on()
        else:
            self.set_setting(SETTINGS_ADDR, SETTINGS_CMD_MODE)

    def abort(self):
        self.data = None
        self.stop_scanning()

    async def scan(self):
        self.clean_uart()
        if self.trigger is not None:
            self.trigger.off()
        else:
            self.set_setting(SETTINGS_ADDR, SETTINGS_CONT_MODE)
        self.data = b""
        self.scanning = True
        self.animated = False
        self.parts = None
        self.bcur = False
        self.bcur_hash = b""
        gc.collect()
        while self.scanning:
            await asyncio.sleep_ms(10)
            # we will exit this loop from update()
            # or manual cancel from GUI
        self.animated = False
        if self.parts is not None:
            del self.parts
            self.parts = None
        gc.collect()
        return self.data

    async def update(self):
        if not self.scanning:
            self.clean_uart()
            return
        # read all available data
        if self.uart.any() > 0:
            d = self.uart.read()
            self.data += d
            # we got a full scan
            if self.data.endswith(self.EOL):
                # maybe two
                chunks = self.data.split(self.EOL)
                self.data = b""
                try:
                    for chunk in chunks[:-1]:
                        if self.process_chunk(chunk):
                            self.stop_scanning()
                            break
                        # animated in trigger mode
                        elif self.trigger is not None:
                            self.trigger.on()
                            await asyncio.sleep_ms(30)
                            self.trigger.off()
                except Exception as e:
                    print(e)
                    self.stop_scanning()
                    raise e

    def process_chunk(self, chunk):
        """Returns true when scanning complete"""
        # should not be there if trigger mode or simulator
        if chunk.startswith(SUCCESS):
            chunk = chunk[len(SUCCESS) :]
        # check if it's bcur encoding
        if chunk[:9].upper() == b"UR:BYTES/":
            self.bcur = True
            return self.process_bcur(chunk)
        else:
            return self.process_normal(chunk)

    def process_bcur(self, chunk):
        # check if it starts with pMofN
        arr = chunk.upper().split(b"/")
        # ur:bytes/MofN/hash/data
        if len(arr) < 4:
            if not self.animated:
                self.data = chunk
                return True
            else:
                self.stop_scanning()
                raise HostError("Ivalid QR code part encoding: %r" % chunk)
        # converting to pMofN to reuse parser
        prefix = b"p" + arr[1].lower()
        hsh = arr[2]
        data = arr[3]
        if not self.animated:
            try:
                m, n = self.parse_prefix(prefix)
                # if succeed - first animated frame,
                # allocate stuff
                self.animated = True
                self.parts = [b""] * n
                self.parts[m - 1] = data
                self.bcur_hash = hsh
                self.data = b""
                return False
            # failed - not animated, just unfortunately similar data
            except:
                raise HostError("Ivalid QR code part encoding: %r" % chunk)
        # expecting animated frame
        m, n = self.parse_prefix(prefix)
        if n != len(self.parts):
            raise HostError("Invalid prefix")
        if hsh != self.bcur_hash:
            print(hsh, self.bcur_hash)
            raise HostError("Checksum mismatch")
        self.parts[m - 1] = data
        # all have non-zero len
        if min([len(part) for part in self.parts]) > 0:
            self.data = b"UR:BYTES/" + self.bcur_hash + b"/" + b"".join(self.parts)
            return True
        else:
            return False

    def process_normal(self, chunk):
        # check if it starts with pMofN
        if b" " not in chunk:
            if not self.animated:
                self.data = chunk
                return True
            else:
                self.stop_scanning()
                raise HostError("Ivalid QR code part encoding: %r" % chunk)
        # space is there
        prefix, *args = chunk.split(b" ")
        if not self.animated:
            if prefix.startswith(b"p") and b"of" in prefix:
                try:
                    m, n = self.parse_prefix(prefix)
                    # if succeed - first animated frame,
                    # allocate stuff
                    self.animated = True
                    self.parts = [b""] * n
                    self.parts[m - 1] = b" ".join(args)
                    self.data = b""
                    return False
                # failed - not animated, just unfortunately similar data
                except:
                    self.data = chunk
                    return True
            else:
                self.data = chunk
                return True
        # expecting animated frame
        m, n = self.parse_prefix(prefix)
        if n != len(self.parts):
            raise HostError("Invalid prefix")
        self.parts[m - 1] = b" ".join(args)
        # all have non-zero len
        if min([len(part) for part in self.parts]) > 0:
            self.data = b"".join(self.parts)
            return True
        else:
            return False

    def parse_prefix(self, prefix):
        if not prefix.startswith(b"p") or b"of" not in prefix:
            raise HostError("Invalid prefix")
        m, n = prefix[1:].split(b"of")
        m = int(m)
        n = int(n)
        if n < m or m < 0 or n < 0:
            raise HostError("Invalid prefix")
        return m, n

    async def get_data(self):
        if self.manager is not None:
            # pass self so user can abort
            await self.manager.gui.show_progress(
                self, "Scanning...", "Point scanner to the QR code"
            )
        data = await self.scan()
        if data is not None:
            return BytesIO(data)

    async def send_data(self, stream, meta):
        response = stream.read().decode()
        title = "Your data:"
        note = None
        if "title" in meta:
            title = meta["title"]
        if "note" in meta:
            note = meta["note"]
        msg = response
        if "message" in meta:
            msg = meta["message"]
        await self.manager.gui.qr_alert(title, msg, response, note=note, qr_width=480)

    @property
    def in_progress(self):
        return self.scanning

    @property
    def progress(self):
        """
        Returns progress
        - either as a number between 0 and 1
        - or a list of True False for checkboxes
        """
        if not self.in_progress:
            return 1
        if not self.animated:
            return 0
        return [len(part) > 0 for part in self.parts]
