"""Behavioural tests for the GM65 factory-reset path in hosts/qr.py.

The reset path is hard to get right for two reasons that a naive mock
hides, so the fake scanner below models both:

  * it only answers when the host UART baud matches its own, so a
    host/scanner baud desync shows up as silence rather than as a
    convenient error, and
  * a factory reset reboots the module, leaving it unresponsive for a
    while and emitting boot noise that is not a protocol reply.

Register semantics are taken from the GM65-S User Manual, chapter 9:
a read reply is seven bytes with the value at index 4 (``res[-3]``),
a successful write is ACKed with exactly ``SUCCESS``, and Form 2-1
gives the factory defaults as standard TTL-232 at 9600 baud.
"""

import unittest

import pyb

import hosts.qr as qr
from hosts.qr import (
    BAR_TYPE_ADDR,
    DEFAULT_SCANNER_SETTINGS,
    BAUD_RATE_9600,
    BAUD_RATE_115200,
    BAUD_RATE_ADDR,
    DELAY_OF_SAME_BARCODES_ADDR,
    HEADER,
    INTERVAL_OF_SCANNING_ADDR,
    MODEL_GM65,
    QR_ADDR,
    RAW_MODE_ADDR,
    RAW_MODE_VALUE,
    SERIAL_ADDR,
    SETTINGS_ADDR,
    SUCCESS,
    TIMOUT_ADDR,
    VERSION_ADDR,
    VERSION_NEEDS_RAW,
)

# Reply frame: 0x02 0x00 | 0x00 0x01 | <data> | CRC(2). The GM65 branch of
# _get_setting_once() only checks the length and reads res[-3], and the write
# ACK is this frame with a zero data byte, so the CRC can stay constant.
_REPLY_HEAD = b"\x02\x00\x00\x01"
_REPLY_CRC = b"\x33\x31"

# Zone bit 0x00D9 <- 0x55 is "reset to defaults" (manual ch. 9, register table)
RESET_ADDR = b"\x00\xD9"
RESET_VALUE = 0x55

# 0x1A in BAUD_RATE_ADDR selects 115200 in the GM65 baud table
_BAUD_CODES = {0x1A: BAUD_RATE_115200, 0x00: BAUD_RATE_9600}


def _reply(value):
    return _REPLY_HEAD + bytes([value]) + _REPLY_CRC


class VirtualClock:
    """Deterministic clock. Nothing in these tests actually sleeps."""

    def __init__(self):
        self.now_ms = 0

    def time(self):
        return self.now_ms / 1000.0

    def sleep_ms(self, ms):
        self.now_ms += ms

    def sleep(self, seconds):
        self.now_ms += int(seconds * 1000)


class FakeGM65:
    """A GM65 that is picky about baud and reboots on a factory reset."""

    # Form 2-1: standard TTL-232 at 9600. Every zone bit the host touches
    # reads back as 0 in the factory state unless listed here.
    FACTORY_DEFAULTS = {
        SERIAL_ADDR: 0x00,
        SETTINGS_ADDR: 0x00,
        TIMOUT_ADDR: 0x64,
        INTERVAL_OF_SCANNING_ADDR: 0x00,
        DELAY_OF_SAME_BARCODES_ADDR: 0x00,
        BAR_TYPE_ADDR: 0x00,
        QR_ADDR: 0x00,
        RAW_MODE_ADDR: 0x00,
        BAUD_RATE_ADDR: 0x00,
    }

    def __init__(
        self,
        clock,
        version=VERSION_NEEDS_RAW,
        reboot_ms=0,
        ack_reset=True,
        boot_noise=b"",
        raw_mode=RAW_MODE_VALUE,
    ):
        self.clock = clock
        self.version = version
        self.reboot_ms = reboot_ms
        self.ack_reset = ack_reset
        self.boot_noise = boot_noise
        self.baudrate = BAUD_RATE_9600
        self.busy_until_ms = -1
        self.saved = None
        self.reset_count = 0
        self.registers = dict(self.FACTORY_DEFAULTS)
        self.registers[RAW_MODE_ADDR] = raw_mode
        self.registers[VERSION_ADDR] = version

    # --- state helpers used by assertions -------------------------------
    @property
    def raw_mode_on(self):
        return self.registers.get(RAW_MODE_ADDR) == RAW_MODE_VALUE

    @property
    def busy(self):
        return self.clock.now_ms < self.busy_until_ms

    def _factory_reset(self):
        self.reset_count += 1
        self.registers = dict(self.FACTORY_DEFAULTS)
        self.registers[VERSION_ADDR] = self.version
        self.baudrate = BAUD_RATE_9600
        self.busy_until_ms = self.clock.now_ms + self.reboot_ms
        self.saved = None

    # --- wire protocol ---------------------------------------------------
    def on_host_write(self, data, host_baud):
        """Return the bytes the scanner puts on the wire, if any."""
        if host_baud != self.baudrate:
            # Framing garbage in both directions; the scanner sees no
            # valid command and the host would not get a usable reply.
            return b""
        if self.busy:
            return b""
        if not data.startswith(HEADER):
            return b""

        kind = data[2]
        length = data[3]

        if kind == 0x07:  # read
            addr = data[4:6]
            return _reply(self.registers.get(addr, 0x00))

        if kind == 0x09:  # save settings to EEPROM
            self.saved = dict(self.registers)
            return SUCCESS

        if kind == 0x08:  # write
            addr = data[4:6]
            payload = data[6:6 + length]
            if addr == RESET_ADDR and payload[:1] == bytes([RESET_VALUE]):
                self._factory_reset()
                out = SUCCESS if self.ack_reset else b""
                return out + self.boot_noise
            if addr == BAUD_RATE_ADDR and length == 2:
                self.registers[addr] = payload[0]
                new_baud = _BAUD_CODES.get(payload[0])
                if new_baud is not None:
                    self.baudrate = new_baud
                return SUCCESS
            self.registers[addr] = payload[0]
            return SUCCESS

        return b""


class FakeUART:
    def __init__(self, scanner, baudrate):
        self.scanner = scanner
        self.baudrate = baudrate
        self.rx = bytearray()

    def init(self, baudrate=None, read_buf_len=None):
        if baudrate is not None:
            self.baudrate = baudrate
        # A real deinit/init drops whatever was latched in the peripheral.
        self.rx = bytearray()

    def deinit(self):
        pass

    def write(self, data):
        self.rx += self.scanner.on_host_write(bytes(data), self.baudrate)

    def any(self):
        return len(self.rx)

    def read(self, nbytes=None):
        if nbytes is None:
            out, self.rx = bytes(self.rx), bytearray()
            return out or None
        out, self.rx = bytes(self.rx[:nbytes]), self.rx[nbytes:]
        return out or None


class QRResetTestCase(unittest.TestCase):
    def make_host(self, **scanner_kwargs):
        clock = VirtualClock()
        scanner = FakeGM65(clock, **scanner_kwargs)

        # qr.py reaches for the module-level `time`; swap in the clock so
        # the reboot window is exercised without real sleeping.
        self._saved_time = qr.time
        qr.time = clock
        self.addCleanup(self._restore_time)

        saved_uart = pyb.UART
        pyb.UART = lambda *a, **kw: FakeUART(scanner, BAUD_RATE_9600)
        try:
            host = qr.QRHost(self._testdir())
        finally:
            pyb.UART = saved_uart

        host.scanner_model = MODEL_GM65
        host.is_configured = True
        # `simulator` is true under the native stubs, so __init__ already
        # handed out a trigger pin. A GM65 driven over UART on hardware has
        # none, and that is the state these tests care about.
        host.trigger = None
        return host, scanner, clock

    def _restore_time(self):
        qr.time = self._saved_time

    def _testdir(self):
        import tempfile

        return tempfile.mkdtemp()

    # -- the baud contract ------------------------------------------------

    def test_host_follows_scanner_to_9600_after_reset(self):
        """A reset drops the scanner to 9600, so the host has to follow."""
        host, scanner, _ = self.make_host()
        host._set_baud(BAUD_RATE_115200)
        scanner.baudrate = BAUD_RATE_115200

        self.assertTrue(host._send_factory_reset())
        self.assertEqual(scanner.reset_count, 1)
        self.assertEqual(host.baudrate, BAUD_RATE_9600)
        self.assertEqual(host.baudrate, scanner.baudrate)

    def test_host_follows_even_when_the_reset_ack_is_lost(self):
        """The reset is fire-and-forget: no readable ACK still means 9600.

        This is the case issue #355 describes. The scanner applies the
        9600 default while the reply is still in flight at 115200, so the
        host reads nothing usable - but the reset did happen.
        """
        host, scanner, _ = self.make_host(ack_reset=False)
        host._set_baud(BAUD_RATE_115200)
        scanner.baudrate = BAUD_RATE_115200

        result = host._send_factory_reset()

        self.assertEqual(scanner.reset_count, 1, "reset should have been sent")
        self.assertEqual(
            host.baudrate,
            BAUD_RATE_9600,
            "host must follow the scanner to 9600 even without an ACK",
        )
        self.assertTrue(
            result,
            "the scanner answers at 9600, so the reset must be reported as done",
        )

    def test_unreachable_scanner_reports_failure_and_restores_baud(self):
        """When the scanner answers nowhere, say so and put the baud back.

        A host cannot tell "reset accepted, still rebooting" from "nothing
        heard" by the ACK alone, so success is decided by whether the
        scanner talks at 9600 afterwards. The unambiguous failure is a
        scanner that answers neither the reset nor a read.
        """
        host, scanner, _ = self.make_host()
        host._set_baud(BAUD_RATE_115200)
        scanner.baudrate = BAUD_RATE_115200
        scanner.busy_until_ms = 10 ** 9  # module never comes back

        self.assertFalse(host._send_factory_reset())
        self.assertEqual(
            host.baudrate,
            BAUD_RATE_115200,
            "a failed reset must not strand the host on a different baud",
        )

    # -- the reboot window ------------------------------------------------

    def test_reconfiguration_survives_the_module_reboot(self):
        """A GM65 reboots on reset; configuration must wait it out.

        This is the hardware failure: the reset is accepted, but the
        module is still coming up when configure_gm65() starts writing,
        so the configuration silently does not land.
        """
        host, scanner, _ = self.make_host(reboot_ms=1500)
        snapshot, previous = host._pre_reset_scanner()

        self.assertTrue(host._send_factory_reset())
        self.assertTrue(
            host._apply_post_reset_configuration(snapshot, previous),
            "configuration must succeed once the module has finished rebooting",
        )
        self.assertTrue(
            scanner.raw_mode_on,
            "the RAW compatibility fix has to be re-applied after a reset",
        )
        self.assertEqual(scanner.baudrate, BAUD_RATE_115200)
        self.assertEqual(host.baudrate, scanner.baudrate)

    def test_boot_noise_does_not_poison_the_next_reply(self):
        """Bytes the module emits past the ACK must not be read as a reply."""
        host, scanner, _ = self.make_host(boot_noise=b"\x00\xff\xff\x00\xff\xff\x00\xff")
        snapshot, previous = host._pre_reset_scanner()

        self.assertTrue(host._send_factory_reset())
        self.assertTrue(host._apply_post_reset_configuration(snapshot, previous))
        self.assertTrue(scanner.raw_mode_on)

    # -- what the reset is supposed to restore ----------------------------

    def test_reset_puts_the_scanner_preferences_back_to_defaults(self):
        """A factory reset means factory defaults, preferences included."""
        host, scanner, _ = self.make_host()
        host.settings.update(
            {"sound": False, "aim": False, "light": True, "enabled": False}
        )

        snapshot, previous = host._pre_reset_scanner()
        self.assertTrue(host._send_factory_reset())
        self.assertTrue(host._apply_post_reset_configuration(snapshot, previous))

        for key, value in DEFAULT_SCANNER_SETTINGS.items():
            self.assertEqual(host.settings[key], value, key)
        self.assertFalse(
            host.settings["enabled"],
            "'enabled' controls the main-menu button, not the scanner, so a "
            "scanner reset must leave it alone",
        )

    def test_failed_reset_gives_the_preferences_back(self):
        """Nothing was restored, so the user's choices must survive."""
        host, scanner, _ = self.make_host()
        host.settings.update({"sound": False, "aim": False, "light": True})

        snapshot, previous = host._pre_reset_scanner()
        self.assertTrue(host._send_factory_reset())
        scanner.busy_until_ms = 10 ** 9
        self.assertFalse(host._apply_post_reset_configuration(snapshot, previous))

        self.assertFalse(host.settings["sound"])
        self.assertFalse(host.settings["aim"])
        self.assertTrue(host.settings["light"])

    # -- not leaving the scanner worse than we found it -------------------

    def test_failed_reconfiguration_still_leaves_a_usable_scanner(self):
        """A wiped scanner plus a failed configure must not be the end state.

        init() falls back to PIN trigger mode when configure() fails. The
        reset path has to do the same, otherwise the scanner stays wiped
        and unconfigured until the next power cycle - and because
        Host.enable() only calls init() once per session, nothing retries.
        """
        host, scanner, _ = self.make_host()
        snapshot, previous = host._pre_reset_scanner()
        self.assertTrue(host._send_factory_reset())

        # the module dies right after the reset
        scanner.busy_until_ms = 10 ** 9

        self.assertFalse(host._apply_post_reset_configuration(snapshot, previous))
        self.assertIsNotNone(
            host.trigger,
            "a failed post-reset configuration must fall back to PIN trigger mode",
        )

    def test_info_line_does_not_claim_a_raw_fix_the_scanner_lost(self):
        """The reported RAW state must come from the scanner, not a host flag."""
        host, scanner, _ = self.make_host()
        host.settings["raw_fix_applied"] = True
        host.software_version = VERSION_NEEDS_RAW
        snapshot, previous = host._pre_reset_scanner()
        self.assertTrue(host._send_factory_reset())

        scanner.busy_until_ms = 10 ** 9
        self.assertFalse(host._apply_post_reset_configuration(snapshot, previous))

        self.assertFalse(scanner.raw_mode_on, "the reset wiped RAW mode")
        self.assertNotIn(
            "Applied",
            host._format_scanner_info(),
            "must not report a RAW fix that the scanner no longer has",
        )


if __name__ == "__main__":
    unittest.main()
