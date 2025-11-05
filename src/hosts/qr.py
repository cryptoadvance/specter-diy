from .core import Host, HostError
import pyb
import time
import asyncio
from platform import simulator, config, delete_recursively, file_exists, sync
import gc
import lvgl as lv
from gui.common import add_button, add_label
from gui.decorators import on_release
from gui.screens.settings import HostSettings
from gui.screens import Alert
from helpers import read_until, read_write, a2b_base64_stream
from microur.decoder import FileURDecoder
from microur.util import cbor

QRSCANNER_TRIGGER = config.QRSCANNER_TRIGGER
# OK response from scanner
SUCCESS = b"\x02\x00\x00\x01\x00\x33\x31"
# serial port mode
SERIAL_ADDR = b"\x00\x0D"
SERIAL_VALUE = 0xA0  # use serial port for data

# factory reset command (restore defaults)
FACTORY_RESET_CMD = b"\x7E\x00\x08\x01\x00\xD9\x55\xAB\xCD"

""" We switch the scanner to continuous mode to initiate scanning and
to command mode to stop scanning. No external trigger is necessary """
SETTINGS_ADDR = b"\x00\x00"

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

""" Address for software version check.
(The ability to check firmware version via this memory was removed from newer GM65 type devices, but still lets us identify versions that need a fix)"""
VERSION_ADDR = b"\x00\xE2"
VERSION_NEEDS_RAW = 0x69  # A version of GM65 that needs RAW mode to be turned on...

""" Some newer GM65 Scanners need to be set to "RAW" mode to correctly scan binary QR codes.
(The address for this is actually undocumented and doesn't seem to work the same on newer varients like the GM805)"""
RAW_MODE_ADDR = b"\x00\xBC"
RAW_MODE_VALUE = 0x08


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
    settings_button = "QR scanner"

    # Some Information to report device to user
    version_str = "No Scanner Detected"

    def __init__(self, path, trigger=None, uart="YA", baudrate=9600):
        super().__init__(path)

        # default settings, extend it with more settings if applicable
        self.settings = {
            "enabled": True,
            "aim": True,
            "light": False,
            "sound": True,
            # internal flag that indicates whether RAW compatibility fix
            # has been applied and persisted on the scanner
            "raw_fix_applied": False,
        }

        self._initial_reset_marker = None
        self._boot_reset_pending = False
        if self.SETTINGS_DIR:
            marker = self.SETTINGS_DIR + "/.qr_factory_reset_done"
            self._initial_reset_marker = marker
            try:
                self._boot_reset_pending = not file_exists(marker)
            except Exception as e:
                # Avoid repeated attempts if storage is unavailable.
                print("QRHost: failed to check reset marker:", e)
                self._boot_reset_pending = False

        if simulator:
            self.EOL = b"\r\n"
        else:
            self.EOL = b"\r"

        self.f = None
        self.software_version = None
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
        self.raw = False
        self.chunk_timeout = 0.5

    @property
    def MASK(self):
        b = (1 << 7)
        if self.settings.get("sound", True):
            b |= (1 << 6)
        if self.settings.get("aim", True):
            b |= (1 << 4)
        if self.settings.get("light", False):
            b |= (1 << 2)
        return b

    @property
    def CMD_MODE(self):
        return self.MASK | 1

    @property
    def CONT_MODE(self):
        return self.MASK | 2

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

    def _get_setting_once(self, addr):
        # only for 1 byte settings
        res = self.query(b"\x7E\x00\x07\x01" + addr + b"\x01\xAB\xCD")
        if res is None or len(res) != 7:
            return None
        return res[-3]

    def get_setting(self, addr, retries=3, retry_delay_ms=50, invalid_values=None):
        if invalid_values:
            invalid_values = set(invalid_values)
        else:
            invalid_values = None
        for attempt in range(retries):
            val = self._get_setting_once(addr)
            if val is None or (invalid_values is not None and val in invalid_values):
                time.sleep_ms(retry_delay_ms)
                self.clean_uart()
                continue
            return val
        return None

    def _set_setting_once(self, addr, value):
        # only for 1 byte settings
        res = self.query(b"\x7E\x00\x08\x01" + addr + bytes([value]) + b"\xAB\xCD")
        if res is None:
            return False
        return res == SUCCESS

    def set_setting(self, addr, value, retries=3, retry_delay_ms=50):
        for attempt in range(retries):
            if self._set_setting_once(addr, value):
                return True
            time.sleep_ms(retry_delay_ms)
            self.clean_uart()
        return False

    def save_settings_on_scanner(self, retries=3, retry_delay_ms=100):
        for attempt in range(retries):
            res = self.query(b"\x7E\x00\x09\x01\x00\x00\x00\xDE\xC8")
            if res == SUCCESS:
                return True
            time.sleep_ms(retry_delay_ms)
            self.clean_uart()
        return False

    def configure(self):
        """Tries to configure scanner, returns True on success"""
        save_required = False
        settings_changed = False
        raw_fix_applied = self.settings.get("raw_fix_applied", False)

        # Set Serial Output Mode
        val = self.get_setting(SERIAL_ADDR)
        if val is None:
            return False
        if val & 0x3 != 0:
            if not self.set_setting(SERIAL_ADDR, val & 0xFC):
                return False
            save_required = True

        # Set Command Mode
        val = self.get_setting(SETTINGS_ADDR)
        if val is None:
            return False
        if val != self.CMD_MODE:
            if not self.set_setting(SETTINGS_ADDR, self.CMD_MODE):
                return False
            save_required = True

        # Set scanning timeout
        val = self.get_setting(TIMOUT_ADDR)
        if val is None:
            return False
        if val != 0:
            if not self.set_setting(TIMOUT_ADDR, 0):
                return False
            save_required = True

        # Set interval between scans
        val = self.get_setting(INTERVAL_OF_SCANNING_ADDR)
        if val is None:
            return False
        if val != INTERVAL_OF_SCANNING:
            if not self.set_setting(INTERVAL_OF_SCANNING_ADDR, INTERVAL_OF_SCANNING):
                return False
            save_required = True

        # Set delay beteen re-reading the same barcode
        val = self.get_setting(DELAY_OF_SAME_BARCODES_ADDR)
        if val is None:
            return False
        if val != DELAY_OF_SAME_BARCODES:
            if not self.set_setting(DELAY_OF_SAME_BARCODES_ADDR, DELAY_OF_SAME_BARCODES):
                return False
            save_required = True

        # Check the module software and enable "RAW" mode if required
        val = self.get_setting(
            VERSION_ADDR, retries=5, retry_delay_ms=100, invalid_values=(0,)
        )
        if val is None:
            return False
        self.software_version = val
        self.version_str = "Detected GM65 Scanner, SW:" + str(val)
        if val == VERSION_NEEDS_RAW:
            val = self.get_setting(RAW_MODE_ADDR)
            if val is None:
                return False
            if val != RAW_MODE_VALUE:
                if not self.set_setting(RAW_MODE_ADDR, RAW_MODE_VALUE):
                    return False
                # Re-read to confirm the scanner accepted the value, retrying
                # once more if necessary. Some scanners take a short while to
                # commit this particular setting right after power-on.
                val_check = self.get_setting(RAW_MODE_ADDR)
                if val_check is None:
                    return False
                if val_check != RAW_MODE_VALUE:
                    if not self.set_setting(RAW_MODE_ADDR, RAW_MODE_VALUE, retries=1, retry_delay_ms=100):
                        return False
                    val_check = self.get_setting(RAW_MODE_ADDR)
                    if val_check is None or val_check != RAW_MODE_VALUE:
                        return False
                save_required = True
            if not raw_fix_applied:
                raw_fix_applied = True
                settings_changed = True
        elif raw_fix_applied:
            # Clear the flag if we are no longer dealing with a scanner that
            # requires the RAW mode compatibility tweak.
            raw_fix_applied = False
            settings_changed = True

        # Save settings to EEPROM if anything has changed.
        if save_required:
            val = self.save_settings_on_scanner()
            if not val:
                return False
            settings_changed = True

        if settings_changed and self.manager is not None:
            keystore = getattr(self.manager, "keystore", None)
            if keystore is not None:
                # persist the updated host settings (including the
                # compatibility flag) so the device keeps track of whether
                # the RAW mode fix has already been applied
                self.settings["raw_fix_applied"] = raw_fix_applied
                try:
                    self.save_settings(keystore)
                except Exception as e:
                    print("Failed to persist QR host settings:", e)
            else:
                # still update the in-memory settings to reflect the current
                # state even if we cannot persist them yet
                self.settings["raw_fix_applied"] = raw_fix_applied
        else:
            # keep the internal flag in sync if no persistence step occurred
            self.settings["raw_fix_applied"] = raw_fix_applied

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
        if self._boot_reset_pending:
            success = self._factory_reset_scanner_on_boot()
            self._boot_reset_pending = False
            if success:
                return
            else:
                print("QRHost: automatic factory reset failed, continuing with configuration")
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

    def _format_scanner_info(self):
        version = self.software_version
        version_text = "unknown" if version is None else str(version)
        raw_fix_applied = self.settings.get("raw_fix_applied", False)
        if version is None:
            raw_fix = "Unknown"
        elif version == VERSION_NEEDS_RAW:
            raw_fix = "Applied" if raw_fix_applied else "Not applied"
        else:
            raw_fix = "Not needed"
        return "Scanner: GM65 | Firmware: {} | CompactQR fix: {}".format(
            version_text,
            raw_fix,
        )

    def _mark_initial_reset_done(self):
        if not self._initial_reset_marker:
            return
        try:
            with open(self._initial_reset_marker, "wb") as f:
                f.write(b"1")
            sync()
        except Exception as e:
            print("QRHost: failed to persist reset marker:", e)

    def _apply_post_reset_configuration(self, settings_snapshot, previous_settings):
        self.uart.deinit()
        self.uart.init(baudrate=9600, read_buf_len=2048)
        self.clean_uart()
        self.settings = settings_snapshot
        configured = self.configure()
        if not configured:
            self.settings = previous_settings
            return False
        self.is_configured = True
        return True

    def _send_factory_reset(self):
        res = self.query(FACTORY_RESET_CMD)
        return res == SUCCESS

    def _factory_reset_scanner_on_boot(self):
        previous_settings = dict(self.settings)
        settings_snapshot = dict(previous_settings)
        settings_snapshot["raw_fix_applied"] = False
        self.clean_uart()
        if not self._send_factory_reset():
            return False
        time.sleep_ms(200)
        if not self._apply_post_reset_configuration(settings_snapshot, previous_settings):
            return False
        self._mark_initial_reset_done()
        return True

    async def _factory_reset_scanner(self, keystore):
        previous_settings = dict(self.settings)
        settings_snapshot = dict(previous_settings)
        settings_snapshot["raw_fix_applied"] = False
        self.clean_uart()
        if not self._send_factory_reset():
            return False
        await asyncio.sleep_ms(200)
        if not self._apply_post_reset_configuration(settings_snapshot, previous_settings):
            return False
        if keystore is not None:
            try:
                self.save_settings(keystore)
            except Exception as e:
                print("Failed to persist QR host settings:", e)
        return True

    async def settings_menu(self, show_screen, keystore):
        title = "QR scanner"
        note = self.version_str
        controls = [{
            "label": "Enable QR scanner",
            "hint": "Enable or disable QR scanner and remove corresponding button from the main menu",
            "value": self.settings.get("enabled", True)
        }, {
            "label": "Sound",
            "hint": "To beep or not to beep?",
            "value": self.settings.get("sound", True)
        }, {
            "label": "Aim light",
            "hint": "Laser eyes!",
            "value": self.settings.get("aim", True)
        }, {
            "label": "Flashlight",
            "hint": "Can create blicks on the screen",
            "value": self.settings.get("light", False)
        }]
        scr = HostSettings(controls, title=title, note=note)
        info_y = scr.next_y + 20
        info = add_label(
            self._format_scanner_info(),
            y=info_y,
            scr=scr.page,
            style="hint",
        )

        reset_y = info.get_y() + info.get_height() + 30

        def trigger_factory_reset():
            scr.show_loader(
                text="Resetting scanner to defaults...",
                title="Factory reset",
            )
            scr.set_value("factory_reset")

        reset_btn = add_button(
            lv.SYMBOL.REFRESH + " Factory reset",
            on_release(trigger_factory_reset),
            scr=scr.page,
            y=reset_y,
        )
        res = await show_screen(scr)
        if res == "factory_reset":
            scr.hide_loader()
            success = await self._factory_reset_scanner(keystore)
            if success:
                await show_screen(
                    Alert(
                        "Success!",
                        "\n\nScanner restored and settings re-applied.",
                        button_text="Close",
                    )
                )
            else:
                await show_screen(
                    Alert(
                        "Error",
                        "\n\nFailed to factory reset scanner!",
                        button_text="Close",
                    )
                )
            return await self.settings_menu(show_screen, keystore)

        if res:
            enabled, sound, aim, light = res
            raw_fix_applied = self.settings.get("raw_fix_applied", False)
            self.settings = {
                "enabled": enabled,
                "aim": aim,
                "light": light,
                "sound": sound,
                "raw_fix_applied": raw_fix_applied,
            }
            self.save_settings(keystore)
            if not self.configure():
                await show_screen(Alert("Error", "\n\nFailed to configure scanner!", button_text="Close"))
                return
            await show_screen(Alert("Success!", "\n\nSettings updated!", button_text="Close"))

    def clean_uart(self):
        self.uart.read()

    def _stop_scanner(self):
        if self.trigger is not None:
            self.trigger.on()  # trigger is reversed, so on means disable
        else:
            self.set_setting(SCAN_ADDR, 0)

    def _start_scanner(self):
        self.clean_uart()
        if self.trigger is not None:
            self.trigger.off()
        else:
            self.set_setting(SCAN_ADDR, 1)

    async def _restart_scanner(self):
        if self.trigger is not None:
            self.trigger.on()
            await asyncio.sleep_ms(30)
            self.trigger.off()
        else:
            self.set_setting(SCAN_ADDR, 1)

    def stop_scanning(self):
        self.scanning = False
        self._stop_scanner()

    def abort(self):
        with open(self.tmpfile, "wb"):
            pass
        self.cancelled = True
        self.stop_scanning()

    @property
    def tmpfile(self):
        return self.path + "/tmp"

    async def scan(self, raw=True, chunk_timeout=0.5):
        self.raw = raw
        self.chunk_timeout = chunk_timeout
        self._start_scanner()
        # clear the data
        with open(self.tmpfile, "wb") as f:
            pass
        if self.f is not None:
            self.f.close()
            self.f = None
        self.scanning = True
        self.cancelled = False
        self.animated = False
        self.parts = None
        self.bcur = False
        self.bcur2 = False
        self.decoder = FileURDecoder(self.path)
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
        del self.decoder
        self.decoder = None
        gc.collect()
        if self.cancelled:
            return None
        self.f = open(self.path + "/data.txt", "rb")
        return self.f

    def check_animated(self, data: bytes):
        try:
            # should be only ascii characters
            d = data.decode().strip().lower()
            if d.startswith("ur:"):  # ur:bytes or ur:crypto-psbt
                return True
            # this will raise if it's not a valid prefix
            self.parse_prefix(data.split(b" ")[0])
            return True
        except Exception as e:
            print("Exception at check animated", e)
            return False
        return False

    async def update(self):
        if not self.scanning:
            self.clean_uart()
            return
        # read all available data
        if self.uart.any() > 0:
            if not self.animated:  # read only one QR code
                # let all data to come on the first QR code
                await asyncio.sleep(self.chunk_timeout)
                d = self.uart.read()
                # if not animated -> stop and return
                if not self.check_animated(d):
                    if d[-len(self.EOL):] == self.EOL:
                        d = d[:-len(self.EOL)]
                    self._stop_scanner()
                    fname = self.path + "/data.txt"
                    with open(fname, "wb") as fout:
                        fout.write(d)
                    self.stop_scanning()
                    return
            else:
                # if animated - we process chunks one at a time
                d = self.uart.read()
            # no new lines - just write and continue
            if d[-len(self.EOL):] != self.EOL:
                with open(self.tmpfile, "ab") as f:
                    f.write(d)
                return
            # restart scan while processing data
            await self._restart_scanner()
            # slice to write
            d = d[:-len(self.EOL)]
            with open(self.tmpfile, "ab") as f:
                f.write(d)
            try:
                if self.process_chunk():
                    self.stop_scanning()
            except Exception as e:
                self.stop_scanning()
                raise e
            # erase the content of the file
            with open(self.tmpfile, "wb") as f:
                pass

    def process_chunk(self):
        """Returns true when scanning complete"""
        # should not be there if trigger mode or simulator
        with open(self.tmpfile, "rb") as f:
            c = f.read(len(SUCCESS))
            while c == SUCCESS:
                c = f.read(len(SUCCESS))
            f.seek(-len(c), 1)
            # check if it's bcur encoding
            start = f.read(9).upper()
            f.seek(-len(start), 1)
            if start == b"UR:BYTES/":
                self.bcur = True
                return self.process_bcur(f)
            # bcur2 encoding
            elif start == b"UR:CRYPTO":
                self.bcur2 = True
                return self.process_bcur2(f)
            else:
                return self.process_normal(f)

    def process_bcur2(self, f):
        gc.collect()
        if self.decoder.read_part(f):
            self._stop_scanner()
            fname = self.path + "/data.txt"
            with self.decoder.result() as b:
                msglen = cbor.read_bytes_len(b)
                with open(fname, "wb") as fout:
                    read_write(b, fout)
            gc.collect()
            return True
        return False

    def process_bcur(self, f):
        # check if starts with UR:BYTES/
        chunk, char = read_until(f, b"/", return_on_max_len=True)
        chunk = chunk or b""
        assert chunk.upper() == b"UR:BYTES"
        assert char == b"/"
        # format: ur:bytes/MofN/hash/data
        # check if next part is MofN,
        # if not - 64 bytes is enough to read the hash
        chunk, char = read_until(f, b"/", max_len=64, return_on_max_len=True)
        chunk = chunk or b""
        # if next / is not found or OF not there
        if char is None or b"OF" not in chunk.upper():
            if not self.animated:
                # maybe there is a hash, but no parts
                fname = self.path + "/data.txt"
                with open(fname, "wb") as fout:
                    fout.write(b"UR:BYTES/")
                    fout.write(chunk)
                    fout.write(char or b"")
                    read_write(f, fout)
                return True
            else:
                self.stop_scanning()
                raise HostError("Ivalid QR code part encoding: %r" % chunk)
        # converting to pMofN to reuse parser
        prefix = b"p" + chunk.lower()
        hsh, char = read_until(f, b"/", max_len=80, return_on_max_len=True)
        hsh = hsh or b""
        assert char == b"/"
        if not self.animated:
            try:
                m, n = self.parse_prefix(prefix)
                # if succeed - first animated frame,
                # allocate stuff
                self.animated = True
                self.parts = [None] * n
                fname = "%s/p%d.txt" % (self.path, m - 1)
                with open(fname, "wb") as fout:
                    read_write(f, fout)
                self.parts[m - 1] = fname
                self.bcur_hash = hsh
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
        fname = "%s/p%d.txt" % (self.path, m - 1)
        with open(fname, "wb") as fout:
            fout.write(f.read())
        self.parts[m - 1] = fname
        # all have non-zero len
        if None not in self.parts:
            self._stop_scanner()
            fname = self.path + "/data.txt"
            with open(fname, "wb") as fout:
                fout.write(b"UR:BYTES/")
                fout.write(self.bcur_hash)
                fout.write(b"/")
                for part in self.parts:
                    with open(part, "rb") as fp:
                        read_write(fp, fout)
            return True
        else:
            return False

    def process_normal(self, f):
        # check if it starts with pMofN
        chunk, char = read_until(f, b" ", max_len=10, return_on_max_len=True)
        chunk = chunk or b""
        if char is None:
            if not self.animated:
                fname = self.path + "/data.txt"
                with open(fname, "wb") as fout:
                    fout.write(chunk)
                    read_write(f, fout)
                return True
            else:
                self.stop_scanning()
                raise HostError("Ivalid QR code part encoding: %r" % chunk)
        # space is there
        if not self.animated:
            if chunk.startswith(b"p") and b"of" in chunk:
                try:
                    m, n = self.parse_prefix(chunk)
                    # if succeed - first animated frame,
                    # allocate stuff
                    self.animated = True
                    self.parts = [None] * n
                    fname = "%s/p%d.txt" % (self.path, m - 1)
                    with open(fname, "wb") as fout:
                        read_write(f, fout)
                    self.parts[m - 1] = fname
                    return False
                # failed - not animated, just unfortunately similar data
                except:
                    fname = self.path + "/data.txt"
                    with open(fname, "wb") as fout:
                        fout.write(chunk)
                        fout.write(char)
                        read_write(f, fout)
                    return True
            else:
                fname = self.path + "/data.txt"
                with open(fname, "wb") as fout:
                    fout.write(chunk)
                    fout.write(char)
                    read_write(f, fout)
                return True
        # expecting animated frame
        m, n = self.parse_prefix(chunk)
        if n != len(self.parts):
            raise HostError("Invalid prefix")
        fname = "%s/p%d.txt" % (self.path, m - 1)
        with open(fname, "wb") as fout:
            read_write(f, fout)
        self.parts[m - 1] = fname
        # all have non-zero len
        if None not in self.parts:
            self._stop_scanner()
            fname = self.path + "/data.txt"
            with open(fname, "wb") as fout:
                for part in self.parts:
                    with open(part, "rb") as fp:
                        read_write(fp, fout)
            return True
        else:
            return False

    def parse_prefix(self, prefix: bytes):
        print(prefix)
        if not prefix.startswith(b"p") or b"of" not in prefix:
            raise HostError("Invalid prefix, should be in pMofN format")
        m, n = prefix[1:].split(b"of")
        m = int(m)
        n = int(n)
        if n < m or m < 0 or n < 0:
            raise HostError("Invalid prefix")
        return m, n

    async def get_data(self, raw=True, chunk_timeout=0.5):
        delete_recursively(self.path)
        if self.manager is not None:
            # pass self so user can abort
            await self.manager.gui.show_progress(
                self, "Scanning...", "Point scanner to the QR code"
            )
        stream = await self.scan(raw=raw, chunk_timeout=chunk_timeout)
        if stream is not None:
            return stream

    async def send_data(self, stream, meta, *args, **kwargs):
        # if it's str - it's a file
        if isinstance(stream, str):
            with open(stream, "rb") as f:
                return await self.send_data(f, meta, *args, **kwargs)
        title = meta.get("title", "Your data:")
        note = meta.get("note")
        start = stream.read(4)
        stream.seek(-len(start), 1)
        if start in [b"cHNi", b"cHNl"]:  # convert from base64 for QR encoder
            with open(self.tmpfile, "wb") as f:
                a2b_base64_stream(stream, f)
            with open(self.tmpfile, "rb") as f:
                return await self.send_data(f, meta, *args, **kwargs)

        if start not in [b"psbt", b"pset"]:
            response = stream.read().decode()
            msg = meta.get("message", response)
            return await self.manager.gui.qr_alert(title, msg, response, note=note, qr_width=480)

        EncoderCls = None
        if self.bcur2:  # we need binary
            from qrencoder import CryptoPSBTEncoder as EncoderCls
        elif self.bcur:
            from qrencoder import LegacyBCUREncoder as EncoderCls
        else:
            from qrencoder import Base64QREncoder as EncoderCls
        with EncoderCls(stream, tempfile=self.path + "/qrtmp") as enc:
            await self.manager.gui.qr_alert(title, "", enc, note=note, qr_width=480)

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
        if self.bcur2 and self.decoder:
            return self.decoder.progress
        if not self.in_progress:
            return 1
        if not self.animated:
            return 0
        return [part is not None for part in self.parts]
