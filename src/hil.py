"""
Hardware-in-the-Loop (HIL) test mode module.

Enables automated testing over the debug UART (ST-Link VCP).
Activated by setting HIL_ENABLED = True in build_config.py (generated at build time).

Commands (sent over UART, newline-terminated):
  TEST_STATUS              -> OK:READY
  TEST_SCREEN              -> OK:SCREEN:<ClassName>:<id>[:<title>]
  TEST_KEYSTORE            -> OK:KEYSTORE:<name>
  TEST_UI:<json>           -> OK:UI (pass JSON value to screen.set_value)
  TEST_WIPE                -> OK:WIPED (wipe wallet storage, then reset)
  TEST_RESET               -> OK:RESET (soft reset)
  TEST_FINGERPRINT         -> OK:FINGERPRINT:<hex>
  TEST_MNEMONIC            -> OK:MNEMONIC:<words>

Examples:
  TEST_UI:""               -> set_value("") - proceed with default
  TEST_UI:1                -> set_value(1) - select option 1
  TEST_UI:true             -> set_value(True) - confirm
  TEST_UI:false            -> set_value(False) - cancel
  TEST_UI:"abandon ..."    -> set_value("abandon ...") - mnemonic
"""

HIL_DEFAULT_PIN = "1234"

_active_keystore_name = "unknown"
_active_keystore_ref = None


def set_keystore_name(name):
    global _active_keystore_name
    _active_keystore_name = name


def set_keystore_ref(ks):
    global _active_keystore_ref
    _active_keystore_ref = ks


def _get_keystore():
    return _active_keystore_ref


import json
from debug_trace import log, log_exception


class HILCommandHandler:
    """Handles HIL test commands received over UART.
    
    Mirrors the behavior of TCPGUI.tcp_loop() from the simulator.
    """

    def __init__(self, uart, gui=None):
        self.uart = uart
        self.gui = gui
        self._buffer = b""

    def set_gui(self, gui):
        """Set GUI reference after initialization."""
        self.gui = gui

    def poll(self):
        """Poll UART for incoming commands and process them.
        
        Called periodically by _hil_listener task.
        Returns True if a command was processed, False otherwise.
        """
        if self.uart is None:
            return False

        # Read available data
        try:
            chunk = self.uart.read(64)
        except Exception as e:
            log("HIL", "read error: %s" % e)
            return False

        if chunk is None or len(chunk) == 0:
            return False

        log("HIL", "RECV: %d bytes" % len(chunk))

        # Accumulate in buffer
        self._buffer += chunk

        # Process complete lines (newline-terminated)
        processed = 0
        while b"\n" in self._buffer:
            try:
                line, self._buffer = self._buffer.split(b"\n", 1)
            except ValueError:
                break

            line = line.strip()
            if len(line) == 0:
                continue

            self._process_line(line.decode())
            processed += 1

        if processed > 0:
            log("HIL", "Processed %d commands" % processed)

        return True

    def _process_line(self, line):
        """Process a single command line."""
        log("HIL", "CMD: %s" % line[:50])

        # TEST_STATUS - device ready check
        if line == "TEST_STATUS":
            self._respond("OK:READY")
            return

        if line == "TEST_SCREEN":
            self._respond(self._screen_info())
            return

        if line == "TEST_KEYSTORE":
            self._respond("OK:KEYSTORE:%s" % _active_keystore_name)
            return

        # TEST_UI:<json> - inject value into current screen
        if line.startswith("TEST_UI:"):
            json_val = line[len("TEST_UI:"):]
            self._inject_value(json_val)
            return

        # TEST_RESET - soft reset
        if line == "TEST_RESET":
            self._respond("OK:RESET")
            import pyb
            pyb.hard_reset()
            return

        # TEST_WIPE - wipe wallet and keystore storage
        if line == "TEST_WIPE":
            self._wipe_storage()
            return

        # TEST_FINGERPRINT - get current keystore fingerprint
        if line == "TEST_FINGERPRINT":
            self._get_fingerprint()
            return

        # TEST_MNEMONIC - export currently loaded mnemonic
        if line == "TEST_MNEMONIC":
            self._get_mnemonic()
            return

        # Fallback: try to parse as JSON (mirrors TCPGUI behavior)
        try:
            json.loads("[%s]" % line)
            self._inject_value(line)
            return
        except Exception:
            pass

        log("HIL", "Unknown command: %s" % line)
        self._respond("ERR:UNKNOWN")

    def _respond(self, message):
        """Send response over UART."""
        if self.uart is not None:
            self.uart.write(("%s\r\n" % message).encode())
        log("HIL", "RSP: %s" % message)

    def _inject_value(self, json_val):
        """Parse JSON value and inject into current screen.
        
        Mirrors TCPGUI.tcp_loop() behavior:
        - val = json.loads("[%s]" % cmd)[0]
        - if self.scr is not None: self.scr.set_value(val)
        """
        if self.gui is None:
            log("HIL", "No GUI for value injection")
            self._respond("ERR:NO_GUI")
            return

        # Parse JSON value (wrapped in array to handle all types)
        try:
            val = json.loads("[%s]" % json_val)[0]
        except Exception as e:
            log("HIL", "JSON parse error: %s" % e)
            self._respond("ERR:JSON")
            return

        # Inject into current screen (same pattern as TCPGUI)
        try:
            scr = self.gui.scr
            if scr is not None:
                if type(scr).__name__ == "PinScreen" and hasattr(scr, "pin"):
                    pin_val = val
                    if pin_val == "":
                        pin_val = HIL_DEFAULT_PIN
                    if pin_val is None:
                        pin_val = ""
                    scr.pin.set_text(str(pin_val))
                    scr.release()
                else:
                    scr.set_value(val)
                log("HIL", "Injected: %s" % repr(val)[:50])
                self._respond("OK:UI")
            else:
                log("HIL", "No screen available")
                self._respond("ERR:NO_SCREEN")
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:INJECT")

    def _screen_info(self):
        if self.gui is None:
            return "ERR:NO_GUI"
        try:
            scr = self.gui.scr
            if scr is None:
                return "OK:SCREEN:None:0"
            title = ""
            try:
                if hasattr(scr, 'title'):
                    t = scr.title
                    if hasattr(t, 'get_text'):
                        title = t.get_text()
                    elif isinstance(t, str):
                        title = t
            except Exception:
                pass
            if title:
                return "OK:SCREEN:%s:%d:%s" % (type(scr).__name__, id(scr), title)
            return "OK:SCREEN:%s:%d" % (type(scr).__name__, id(scr))
        except Exception:
            return "ERR:NO_SCREEN"

    def _wipe_storage(self):
        import platform
        try:
            wallet_path = platform.fpath("/qspi/wallets")
            try:
                platform.delete_recursively(wallet_path)
            except OSError:
                pass
            log("HIL", "Wiped: %s" % wallet_path)
            keystore_path = platform.fpath("/flash/keystore")
            if keystore_path:
                try:
                    platform.delete_recursively(keystore_path)
                except OSError:
                    pass
                log("HIL", "Wiped: %s" % keystore_path)
            self._respond("OK:WIPED")
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:WIPE_FAIL")

    def _get_fingerprint(self):
        try:
            ks = _get_keystore()
            if ks is None:
                self._respond("ERR:NO_KEYSTORE")
                return
            fp = ks.fingerprint
            if fp is None:
                self._respond("ERR:NO_FINGERPRINT")
            else:
                from binascii import hexlify
                self._respond("OK:FINGERPRINT:%s" % hexlify(fp).decode())
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:FINGERPRINT_FAIL")

    def _get_mnemonic(self):
        try:
            ks = _get_keystore()
            if ks is None:
                self._respond("ERR:NO_KEYSTORE")
                return
            mn = ks.mnemonic
            if mn is None:
                self._respond("ERR:NO_MNEMONIC")
            else:
                self._respond("OK:MNEMONIC:%s" % mn)
        except Exception as e:
            log_exception("HIL", e)
            self._respond("ERR:MNEMONIC_FAIL")
