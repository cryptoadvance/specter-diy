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
SUCCESS_LEN = len(SUCCESS)
# serial port mode
SERIAL_ADDR = b"\x00\x0D"
SERIAL_VALUE = 0xA0  # use serial port for data
READ_BUFFER_LEN = 4096 # Increased to avoid error when processing large single QR codes

# Consts for identified model
MODEL_UNKNOWN = 0
MODEL_GM65 = 1
MODEL_M3Y = 2

RETRY_DELAY_MS = 100
DELAY_AFTER_FACTORY_RESET = 200
CHUNK_TIMEOUT = 0.5

# ------ GM65 Scanner
# Header:0x7E 0x00 Types:0x08 Lens:0x01 Address:0x00D9 Data:0x55 (Restore to user setting) - 0x50 (Restore to factory setting) CRC: 0xABCD (no checksum)
HEADER = b"\x7E\x00"
CRC_NO_CHECKSUM = b"\xAB\xCD"
FACTORY_RESET_CMD = HEADER + b"\x08\x01\x00\xD9\x55" + CRC_NO_CHECKSUM

""" We switch the scanner to continuous mode to initiate scanning and
to command mode to stop scanning. No external trigger is necessary """
SETTINGS_ADDR = b"\x00\x00"

""" After basic scanner configuration (9600 bps) uart is set to 115200 bps
to support fast scanning of animated qrs """
BAUD_RATE_ADDR = b"\x00\x2A"
BAUD_RATE = b"\x1A\x00"  # 115200
BAUD_RATE_9600 = 9600
BAUD_RATE_57600 = 57600
BAUD_RATE_115200 = 115200

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

BAR_TYPE_ADDR = b"\x00\x2C"
QR_ADDR = b"\x00\x3F"

# ----- M3Y Scanner
M3Y_FACTORY_RESET_CMD = b"S_CMD_FFFF"
M3Y_DISABLE_ALL_SYMBOLOGIES = b"C_CMD_R000" # disable 1D/2D barcodes
M3Y_ENABLE_QR_SYMBOL = b"C_CMD_QR01" # enable reading QR codes
M3Y_GET_VERSION = b"T_OUT_CVER"
M3Y_READ_LED_INDICATOR = b"S_CMD_0407"
M3Y_EOL = b"S_CMD_059D"

M3Y_BAUDRATE_SET = b"S_CMD_H3BR" # add suffix: 9600 or 57600

# Add Suffix: 0=OFF / 1=ON
M3Y_CONFIG_MODE = b"S_CMD_000" # Read configuration QRs

# Add Suffix: 0=OFF / 2=ON (1=ON for SOUND)
M3Y_LIGHT = b"S_CMD_03L"
M3Y_AIM = b"S_CMD_03A"
M3Y_SOUND = b"S_CMD_04F"
M3Y_SOUND_TYPE = b"S_CMD_04T" # 1, 2 or 3
M3Y_SOUND_VOL = b"S_CMD_04V" # 0, 1 or 2 (H, M, L)

# Scan Modes
M3Y_CMD_MODE = b"S_CMD_020D" # command mode
M3Y_TRIGGER_TIMEOUT = b"S_CMD_MTRS0000" # infinite
M3Y_CONTINUOUS_TIMEOUT = b"S_CMD_MARS0000" # infinite
M3Y_CONT_ENABLE_REREAD_TIMEOUT = b"S_CMD_MA31"
M3Y_CONT_REREAD_TIMEOUT = b"S_CMD_MARI0100"

# Actions for CMD_MODE
M3Y_ENABLE_SCAN = b"SR030301"
M3Y_DISABLE_SCAN = b"SR030300"

# Communication protocol
M3Y_SERIAL_PROT = b"S_CMD_01H3"

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

    # Flag to change code behaviour depending on the scanner
    scanner_model = MODEL_UNKNOWN

    def __init__(self, path, trigger=None, uart="YA", baudrate=BAUD_RATE_9600):
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
        self.baudrate = baudrate
        self.uart = pyb.UART(uart, baudrate, read_buf_len=READ_BUFFER_LEN)
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
        self.chunk_timeout = CHUNK_TIMEOUT

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

    # unused
    # @property
    # def CONT_MODE(self):
    #     return self.MASK | 2
    
    def _wait_uart_fill_data(self, timeout=RETRY_DELAY_MS):
        t0 = time.time()
        while self.uart.any() < SUCCESS_LEN:
            time.sleep_ms(10)
            t = time.time()
            if t > t0 + timeout / 1000:
                return False
        return True

    def query(self, data: bytes, timeout=RETRY_DELAY_MS):
        """Blocking query"""
        self.uart.write(data)
        has_data = self._wait_uart_fill_data(timeout)
        if not has_data:
            return None
        
        if self.scanner_model == MODEL_M3Y:
            res = self.uart.read()
        else:
            res = self.uart.read(SUCCESS_LEN)
        return res
    
    def _compute_bcc(self, data: bytes):
        """BCC: Block Check Character (1-byte XOR checksum)"""
        bcc = 0
        for byte in data:
            bcc ^= byte
        return bytes([bcc])
    
    def _check_bcc(self, data_with_bcc: bytes):
        """BCC: Block Check Character (1-byte XOR checksum)"""
        if len(data_with_bcc) < 2:
            return False
        data = data_with_bcc[:-1]
        received_bcc = data_with_bcc[-1:]
        calculated_bcc = self._compute_bcc(data)
        return received_bcc == calculated_bcc
    
    def _build_cmd_m3y(self, command: bytes):
        command_len = len(command).to_bytes(2, 'big')
        return b"\x5A\x00" + command_len + command + self._compute_bcc(command_len + command) + b"\xA5"

    def _parse_response_m3y(self, res: bytes):
        if res is None or res == b"" or len(res) < 4:
            return None
        
        # Strict header check
        if res[0:2] != b"\x5A\x01":
            return None
        
        header_len = 4
        data_len = (res[2] << 8) | res[3]
        if not self._check_bcc(res[1:header_len + data_len + 1]):
            return None
        
        payload = res[header_len:header_len + data_len]
        if len(payload) == 2:
            if payload == b"\x90\x00":
                return True
            else:
                return None
        
        return payload

    def _send_and_parse_m3y(self, command: bytes):
        res = self.query(self._build_cmd_m3y(command))
        return self._parse_response_m3y(res)

    def _get_setting_once(self, addr: bytes):
        # only for 1 byte settings
        res = self.query(HEADER + b"\x07\x01" + addr + b"\x01" + CRC_NO_CHECKSUM)
        if res is None or len(res) != SUCCESS_LEN:
            return None
        return res[-3]

    def get_setting(self, addr: bytes, retries=3, retry_delay_ms=RETRY_DELAY_MS>>1, invalid_values=None):
        for _ in range(retries):
            if self.scanner_model == MODEL_M3Y:
                val = self._send_and_parse_m3y(addr)
            else:
                val = self._get_setting_once(addr)
            if val is None or (invalid_values is not None and val in invalid_values):
                time.sleep_ms(retry_delay_ms)
                self.clean_uart()
                continue
            return val
        return None
    
    def _set_setting_once(self, addr: bytes, value: int):
        # only for 1 byte settings
        res = self.query(HEADER + b"\x08\x01" + addr + bytes([value]) + CRC_NO_CHECKSUM)
        if res is None:
            return False
        return res == SUCCESS

    def set_setting(self, addr: bytes, value: int, retries=3, retry_delay_ms=RETRY_DELAY_MS>>1):
        for _ in range(retries):
            if self.scanner_model == MODEL_M3Y:
                if self._send_and_parse_m3y(addr):
                    return True
            else:
                if self._set_setting_once(addr, value):
                    return True
            time.sleep_ms(retry_delay_ms)
            self.clean_uart()
        return False

    def save_settings_on_scanner(self, retries=3, retry_delay_ms=RETRY_DELAY_MS):
        if self.scanner_model == MODEL_M3Y:
            return True
        
        for _ in range(retries):
            res = self.query(HEADER + b"\x09\x01\x00\x00\x00\xDE\xC8")
            if res == SUCCESS:
                return True
            time.sleep_ms(retry_delay_ms)
            self.clean_uart()
        return False
    
    def configure(self):
        """Tries to configure the scanner, returns True on success"""

        if self.scanner_model == MODEL_M3Y:
            def _try_baudrate(baud):
                if self.baudrate != baud:
                    self.get_setting(M3Y_BAUDRATE_SET + str(baud).encode())
                    self._set_baud(baud)
                return self.get_setting(M3Y_GET_VERSION)

            # Try fast baudrate first, then fallback
            val = _try_baudrate(BAUD_RATE_57600) or _try_baudrate(BAUD_RATE_9600)
            if not val:
                return False

            return self.configure_m3y(val)

        if self.scanner_model == MODEL_GM65:
            return self.configure_gm65()
        return False

    def configure_m3y(self, version):
        """Tries to configure M3Y scanner, returns True on success"""
        self.software_version = version.decode().strip()
        self.version_str = "Detected M3Y Scanner, SW:" + self.software_version

        # Disable read of configurable QRs and other configs
        required_configs = (
            M3Y_CONFIG_MODE + b"0", M3Y_DISABLE_ALL_SYMBOLOGIES, M3Y_ENABLE_QR_SYMBOL, 
            M3Y_READ_LED_INDICATOR, M3Y_EOL, M3Y_TRIGGER_TIMEOUT, M3Y_CONTINUOUS_TIMEOUT, 
            M3Y_CONT_ENABLE_REREAD_TIMEOUT, M3Y_CONT_REREAD_TIMEOUT, M3Y_CMD_MODE, M3Y_SERIAL_PROT
        )
        for config in required_configs:
            if self.get_setting(config, 2) is None:
                return False
        
        # Configure audio and features based on settings
        audio_configs = [M3Y_SOUND + (b"1" if self.settings.get("sound", True) else b"0")]
        if self.settings.get("sound", True):
            audio_configs.extend([M3Y_SOUND_TYPE + b"1", M3Y_SOUND_VOL + b"1"])
        
        for config in audio_configs:
            if self.get_setting(config) is None:
                return False

        # Aim
        aim_mode = b"2" if self.settings.get("aim", True) else b"0"
        if self.get_setting(M3Y_AIM + aim_mode) is None:
            return False
        
        # LED Light
        light_mode = b"2" if self.settings.get("light", False) else b"0"
        if self.get_setting(M3Y_LIGHT + light_mode) is None:
            return False
        
        return True

    def configure_gm65(self):
        """Tries to configure GM65 scanner, returns True on success"""
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

        # Configure scanner settings with a batch approach
        scanner_settings = (
            (SETTINGS_ADDR, self.CMD_MODE),
            (TIMOUT_ADDR, 0),
            (INTERVAL_OF_SCANNING_ADDR, INTERVAL_OF_SCANNING),
            (DELAY_OF_SAME_BARCODES_ADDR, DELAY_OF_SAME_BARCODES),
            (BAR_TYPE_ADDR, 0x01),
            (QR_ADDR, 0x01)
        )
        
        for addr, set_val in scanner_settings:
            val = self.get_setting(addr)
            if val is None:
                return False
            if val != set_val:
                if not self.set_setting(addr, set_val):
                    return False
                save_required = True

        # Check the module software and enable "RAW" mode if required
        val = self.get_setting(VERSION_ADDR, retries=5, retry_delay_ms=RETRY_DELAY_MS, invalid_values={0})
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
                    if not self.set_setting(RAW_MODE_ADDR, RAW_MODE_VALUE, retries=1, retry_delay_ms=RETRY_DELAY_MS):
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
        ret = self.query(HEADER + b"\x08\x02" + BAUD_RATE_ADDR + BAUD_RATE + CRC_NO_CHECKSUM)
        if ret != SUCCESS:
            return False
        self._set_baud(BAUD_RATE_115200)
        return True
    
    def _set_baud(self, baudrate):
        self.uart.deinit()
        self.baudrate=baudrate
        self.uart.init(baudrate=baudrate, read_buf_len=READ_BUFFER_LEN)
        self.clean_uart()

    def _try_m3y(self):
        self.scanner_model = MODEL_M3Y
        return bool(self.get_setting(M3Y_GET_VERSION, 2))

    def _try_gm65(self):
        self.scanner_model = MODEL_GM65
        return bool(self.get_setting(SERIAL_ADDR))

    def _update_scanner_model(self):
        if self.scanner_model != MODEL_UNKNOWN:
            return
        
        attempts = (
            (BAUD_RATE_9600,   (self._try_m3y, self._try_gm65)),
            (BAUD_RATE_57600,  (self._try_m3y,)),
            (BAUD_RATE_115200, (self._try_gm65,)),
        )

        for baud, probes in attempts:
            if self.baudrate != baud:
                self._set_baud(baud)

            for probe in probes:
                if probe():
                    return

        self.scanner_model = MODEL_UNKNOWN

    def init(self):
        if self.is_configured:
            return
        
        # Identify scanner and baudrate
        self._update_scanner_model()

        if self._boot_reset_pending:
            success = self._factory_reset_scanner_on_boot()
            self._boot_reset_pending = False
            if success:
                return
            else:
                print("QRHost: automatic factory reset failed, continuing with configuration")
        
        # if failed to configure - probably a different scanner
        # in this case fallback to PIN trigger mode FIXME
        self.is_configured = self.configure()
        if self.is_configured:
            return

        # PIN trigger mode
        self._set_baud(BAUD_RATE_9600)
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
        scanner_name = "unknown"
        if self.scanner_model == MODEL_GM65:
            scanner_name = "GM65"
        elif self.scanner_model == MODEL_M3Y:
            scanner_name = "M3Y"

        return "Scanner: {} | Firmware: {} | CompactQR fix: {}".format(
            scanner_name, version_text, raw_fix,
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
        self.settings = settings_snapshot
        configured = self.configure()
        if not configured:
            self.settings = previous_settings
            return False
        self.is_configured = True
        return True

    def _send_factory_reset(self):
        if self.scanner_model == MODEL_M3Y:
            # factory reset will change baudrate to 9600
            prev_baudrate = self.baudrate
            if self.baudrate != BAUD_RATE_9600:
                self.get_setting(M3Y_BAUDRATE_SET + str(BAUD_RATE_9600).encode())
                self._set_baud(BAUD_RATE_9600)
            
            res = self.get_setting(M3Y_FACTORY_RESET_CMD)

            if prev_baudrate != self.baudrate:
                self.get_setting(M3Y_BAUDRATE_SET + str(prev_baudrate).encode())
                self._set_baud(prev_baudrate)

            return bool(res)
        
        if self.scanner_model == MODEL_GM65:
            return bool(self.query(FACTORY_RESET_CMD))
        return False
    
    def _pre_reset_scanner(self):
        previous_settings = dict(self.settings)
        settings_snapshot = dict(previous_settings)
        settings_snapshot["raw_fix_applied"] = False
        return settings_snapshot, previous_settings

    def _factory_reset_scanner_on_boot(self):
        settings_snapshot, previous_settings = self._pre_reset_scanner()
        if not self._send_factory_reset():
            return False
        time.sleep_ms(DELAY_AFTER_FACTORY_RESET)
        if not self._apply_post_reset_configuration(settings_snapshot, previous_settings):
            return False
        self._mark_initial_reset_done()
        return True

    async def _factory_reset_scanner(self, keystore):
        settings_snapshot, previous_settings = self._pre_reset_scanner()
        if not self._send_factory_reset():
            return False
        await asyncio.sleep_ms(DELAY_AFTER_FACTORY_RESET)
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
            lv.SYMBOL.REFRESH + " Reset QR Module",
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

    def _start_scan(self, enable: int):
        """Send enable/disable command to scanner based on model"""
        if self.scanner_model == MODEL_M3Y:
            cmd = M3Y_ENABLE_SCAN if enable else M3Y_DISABLE_SCAN
            self.get_setting(cmd)
        else:
            self.set_setting(SCAN_ADDR, enable)

    def _stop_scanner(self):
        if self.trigger is not None:
            self.trigger.on()  # trigger is reversed, so on means disable
        else:
            self._start_scan(0)

    def _start_scanner(self):
        self.clean_uart()
        if self.trigger is not None:
            self.trigger.off()
        else:
            self._start_scan(1)

    async def _restart_scanner(self):
        # fix scanner race condition
        time.sleep_ms(RETRY_DELAY_MS)
        if self.trigger is not None:
            self.trigger.on()
            await asyncio.sleep_ms(30)
            self.trigger.off()
        else:
            self._start_scan(1)

    def stop_scanning(self):
        self.scanning = False
        # wait the execution of any previous async _restart_scanner call
        time.sleep_ms(RETRY_DELAY_MS)
        self._stop_scanner()

    def abort(self):
        with open(self.tmpfile, "wb"):
            pass
        self.cancelled = True
        self.stop_scanning()

    @property
    def tmpfile(self):
        return self.path + "/tmp"

    async def scan(self, raw=True, chunk_timeout=CHUNK_TIMEOUT):
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
                if d is None or len(d) < len(self.EOL):
                    raise ValueError("Failed to read data from scanner")
                accumulator_d = d
                # data should end with \r indicating a complete read
                while d[-len(self.EOL):] != self.EOL:
                    if not self.scanning:
                        self.clean_uart()
                        return
                    await asyncio.sleep(self.chunk_timeout)
                    if self.uart.any():
                        d = self.uart.read()
                        if d is None or len(d) < len(self.EOL):
                            raise ValueError("Failed to read data from scanner")
                    else:
                        self.stop_scanning()
                        if len(accumulator_d) >= READ_BUFFER_LEN:
                            raise ValueError("QR length exceeds READ_BUFFER_LEN=" + str(READ_BUFFER_LEN))
                        raise ValueError("Scanner stopped because no end of line found")
                    accumulator_d += d
                d = accumulator_d
                    
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
                raise HostError("Invalid QR code part encoding: %r" % chunk)
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
                raise HostError("Invalid QR code part encoding: %r" % chunk)
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
                raise HostError("Invalid QR code part encoding: %r" % chunk)
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

    async def get_data(self, raw=True, chunk_timeout=CHUNK_TIMEOUT):
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
