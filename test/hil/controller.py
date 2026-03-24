"""
Hardware controller for HIL testing - mirrors SimController interface exactly.

SimController:
  - TCP socket on port 8787 for GUI commands
  - TCP socket on port 8789 for USB protocol
  - gui.send(val) -> passes JSON value to screen.set_value(val)

HardwareController:
  - Serial port /dev/ttyACM0 (debug UART) for GUI commands
  - Serial port /dev/ttyACM1 (USB VCP) for USB protocol
  - gui.send(val) -> sends "TEST_UI:<json>" to firmware

Both expose identical interface:
  - start(): Reset device
  - load(): GUI flow to unlock device, connect USB
  - query(data, commands=[]): Send command, handle confirmations
  - shutdown(): Clean up
"""
import json
import glob
import os
import re
import subprocess
import time

try:
    import serial
except ImportError:
    serial = None


class SerialSocket:
    """Serial port wrapper matching TCPSocket interface.

    Handles mixed debug logs and HIL responses on the same UART.
    Log format: [HIL] CMD: ..., [HIL] Injected: ..., [HIL] RSP: OK:...
    Response pattern within logs: OK:READY, OK:UI, ERR:...
    """

    def __init__(self, port, baudrate=9600, timeout=5):
        if serial is None:
            raise RuntimeError("pyserial required")
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.s = None
        self._stash = b""
        self._open()

    def _open(self):
        self.s = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)

    def _reopen(self):
        try:
            if self.s is not None:
                self.s.close()
        except Exception:
            pass
        time.sleep(0.2)
        try:
            self._open()
        except Exception as e:
            print("[SerialSocket] reopen failed on %s: %s" % (self.port, e))

    def _safe_read(self, size):
        try:
            return self.s.read(size)
        except Exception as e:
            print("[SerialSocket] read error on %s: %s" % (self.port, e))
            self._reopen()
            return b""

    def _safe_write(self, data):
        try:
            self.s.write(data)
            return True
        except Exception as e:
            print("[SerialSocket] write error on %s: %s" % (self.port, e))
            self._reopen()
            try:
                self.s.write(data)
                return True
            except Exception as e:
                print("[SerialSocket] write retry failed on %s: %s" % (self.port, e))
                return False

    def read_all(self, timeout=0.5):
        res = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                waiting = self.s.in_waiting
            except Exception:
                self._reopen()
                waiting = 0
            if waiting:
                res += self._safe_read(waiting)
            time.sleep(0.01)
        return res

    def readline(self, eol=b"\r\n", timeout=3):
        res = b""
        t0 = time.time()
        while eol not in res:
            if time.time() - t0 > timeout:
                break
            try:
                waiting = self.s.in_waiting
            except Exception:
                self._reopen()
                waiting = 0
            if waiting:
                res += self._safe_read(waiting)
            time.sleep(0.01)
        return res

    def read_response(self, timeout=3, expected_prefix=None):
        data = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                waiting = self.s.in_waiting
            except Exception:
                self._reopen()
                waiting = 0
            if waiting:
                data += self._safe_read(waiting)
                matches = re.findall(rb'(OK:[^\r\n]*\r\n|ERR:[^\r\n]*\r\n)', data)
                if matches:
                    for candidate in reversed(matches):
                        if candidate.startswith(b"ERR:"):
                            return candidate
                        if expected_prefix is None or candidate.startswith(expected_prefix):
                            return candidate
            time.sleep(0.01)
        return data

    def _flush(self, quiet_period=0.15):
        """Read all pending data, waiting until buffer is quiet."""
        while True:
            data = self.read_all(timeout=quiet_period)
            if len(data) == 0:
                break

    def command(self, cmd, timeout=2):
        self._flush()
        if not cmd.endswith("\n"):
            cmd = cmd + "\n"
        if not self._safe_write(cmd.encode()):
            return b""
        expected_prefix = None
        if cmd.startswith("TEST_STATUS"):
            expected_prefix = b"OK:READY"
        elif cmd.startswith("TEST_SCREEN"):
            expected_prefix = b"OK:SCREEN"
        elif cmd.startswith("TEST_UI:"):
            expected_prefix = b"OK:UI"
        elif cmd.startswith("TEST_WIPE"):
            expected_prefix = b"OK:WIPED"
        elif cmd.startswith("TEST_KEYSTORE"):
            expected_prefix = b"OK:KEYSTORE"
        elif cmd.startswith("TEST_FINGERPRINT"):
            expected_prefix = b"OK:FINGERPRINT"
        return self.read_response(timeout=timeout, expected_prefix=expected_prefix)

    def send(self, cmd):
        self._flush()

        json_cmd = json.dumps([cmd])[1:-1]
        msg = "TEST_UI:%s\r\n" % json_cmd
        if not self._safe_write(msg.encode()):
            return b""

        resp = self.read_response(timeout=3, expected_prefix=b"OK:UI")
        if b"OK:" in resp:
            time.sleep(0.3)
        return resp

    def status(self):
        return self.command("TEST_STATUS", timeout=1)

    def screen(self):
        for _ in range(3):
            resp = self.command("TEST_SCREEN", timeout=1)
            if resp.startswith(b"OK:SCREEN:") or resp.startswith(b"ERR:"):
                return resp
            time.sleep(0.1)
        return resp

    def query(self, data):
        self._stash = b""
        self._safe_write(data)
        buf = b""
        deadline = time.time() + 4
        ack = b"ACK\r\n"
        while time.time() < deadline:
            try:
                waiting = self.s.in_waiting
            except Exception:
                self._reopen()
                waiting = 0
            if waiting:
                buf += self._safe_read(waiting)
                idx = buf.find(ack)
                if idx != -1:
                    after = buf[idx + len(ack):]
                    self._stash = after
                    return ack
            time.sleep(0.01)
        self._stash = buf
        return b""

    def receive(self):
        if self._stash:
            buf = self._stash
            self._stash = b""
        else:
            buf = b""
        t0 = time.time()
        timeout = 10
        while b"\r\n" not in buf:
            if time.time() - t0 > timeout:
                break
            try:
                waiting = self.s.in_waiting
            except Exception:
                self._reopen()
                waiting = 0
            if waiting:
                buf += self._safe_read(waiting)
            time.sleep(0.01)
        idx = buf.find(b"\r\n")
        if idx != -1:
            leftover = buf[idx + 2:]
            if leftover:
                self._stash = leftover
            return buf[:idx]
        self._stash = buf
        return buf

    def _drain_popup(self, timeout=2.0):
        """Drain LVGL popup text that leaks into USB VCP after GUI confirmation.

        When showaddr displays a WalletScreen popup, LVGL label text
        ("Text", "bitcoin:<addr>") appears on USB VCP before the actual
        address response. This reads all available data, filters out
        popup noise, and preserves any non-popup lines in the stash
        for receive() to pick up as the actual response.
        """
        collected = b""
        quiet_deadline = time.time() + timeout
        while time.time() < quiet_deadline:
            try:
                waiting = self.s.in_waiting
            except Exception:
                self._reopen()
                waiting = 0
            if waiting:
                collected += self._safe_read(waiting)
                quiet_deadline = time.time() + 0.3
            else:
                time.sleep(0.01)
        if not collected:
            return
        lines = collected.split(b"\r\n")
        non_popup = []
        for line in lines:
            if not line:
                continue
            if line.startswith(b"Text") or line.startswith(b"bitcoin:"):
                continue
            non_popup.append(line)
        if non_popup:
            self._stash = non_popup[0] + b"\r\n"

    def close(self):
        if self.s:
            self.s.close()


class HardwareController:
    """Controls Specter-DIY hardware - mirrors SimController interface."""

    def __init__(self):
        self.started = False
        self.gui = None
        self.usb = None
        self.debug_port = os.environ.get(
            "HIL_DEBUG_PORT",
            self._find_stlink_uart() or "/dev/ttyACM0"
        )
        self.vcp_port = os.environ.get(
            "HIL_VCP_PORT",
            self._find_micropython_vcp() or "/dev/ttyACM1"
        )
        self._debug_log = []

    def _detect_keystore(self, timeout=30):
        """Wait for firmware to detect and set the active keystore.

        TEST_STATUS returns OK:READY before keystore detection completes,
        so we must retry TEST_KEYSTORE until the firmware has finished
        polling keystores and set _active_keystore_name.

        Returns keystore name string, or 'internal' if detection times out.
        """
        t0 = time.time()
        while time.time() - t0 < timeout:
            resp = self.gui.command("TEST_KEYSTORE", timeout=2)
            prefix = b"OK:KEYSTORE:"
            if prefix in resp:
                ks_name = resp.split(prefix, 1)[1].strip().decode()
                if ks_name != "unknown":
                    print("Detected keystore: %s" % ks_name)
                    return ks_name
            time.sleep(0.5)
        print("Keystore detection timed out, defaulting to internal")
        return "internal"

    @staticmethod
    def _find_stlink_uart():
        matches = sorted(glob.glob("/dev/serial/by-id/usb-STMicroelectronics_STM32_STLink_*-if02"))
        return matches[0] if matches else None

    @staticmethod
    def _find_micropython_vcp():
        matches = sorted(glob.glob("/dev/serial/by-id/usb-MicroPython_Pyboard_*-if00"))
        return matches[0] if matches else None

    def _send_with_retry(self, value, label, require_change=False):
        prev_screen = self.gui.screen()
        for _ in range(5):
            resp = self.gui.send(value)
            if b"OK:UI" in resp:
                last_screen = self.gui.screen()
                changed = False
                t0 = time.time()
                while time.time() - t0 < 4:
                    cur = self.gui.screen()
                    if cur.startswith(b"OK:SCREEN") and cur != prev_screen:
                        last_screen = cur
                        changed = True
                        break
                    time.sleep(0.1)
                if require_change and not changed:
                    time.sleep(0.3)
                    continue
                print(f"{label}: {resp} from={prev_screen} to={last_screen} changed={changed}")
                if b"OK:SCREEN:Alert:" in last_screen:
                    time.sleep(0.3)
                    continue
                return
            time.sleep(0.4)
        raise RuntimeError(f"{label} failed, last response: {resp}")

    def _wait_for_usb_vcp(self):
        print(f"Waiting for USB VCP at {self.vcp_port}...")
        vcp_timeout = 30
        vcp_start = time.time()
        while not os.path.exists(self.vcp_port):
            elapsed = time.time() - vcp_start
            if elapsed > vcp_timeout:
                print(f"Available ports: {os.listdir('/dev') if os.path.exists('/dev') else 'N/A'}")
                raise RuntimeError(f"USB VCP not found after {vcp_timeout}s")
            if int(elapsed) % 5 == 0:
                print(f"  Still waiting... ({int(elapsed)}s)")
            time.sleep(0.5)

        self.usb = SerialSocket(self.vcp_port, baudrate=115200, timeout=10)
        print("USB VCP connected")

        print("Waiting for USB host ACK readiness...")
        current_screen = self.gui.screen()
        print(f"Screen before USB ACK wait: {current_screen}")
        if b"OK:SCREEN:Alert:" in current_screen:
            raise RuntimeError(f"Cannot start USB flow from Alert screen: {current_screen}")
        ack_ready = False
        for _ in range(30):
            ack = self.usb.query(b"\r\n")
            if ack == b"ACK\r\n":
                self.usb.receive()
                ack_ready = True
                break
            time.sleep(0.3)
        if not ack_ready:
            raise RuntimeError("USB host did not become ACK-ready")

    def _load_internal_flash(self):
        """Load mnemonic via internal flash keystore.

        Mirrors SimController.load() exactly:
        1. Choose PIN (first setup_pin screen)
        2. Confirm PIN (second setup_pin screen)
        3. Select "Enter recovery phrase" from initmenu
        4. Enter mnemonic
        """
        self._send_with_retry("1234", "PIN choose", require_change=True)
        time.sleep(0.5)
        self._send_with_retry("1234", "PIN confirm", require_change=True)
        time.sleep(1)
        # After PIN, device may show Alert briefly (init_apps timing).
        # Wait for stable screen before proceeding.
        for _ in range(10):
            screen = self.gui.screen()
            if b"OK:SCREEN:Menu:" in screen:
                break
            if b"OK:SCREEN:Alert:" in screen:
                # Dismiss alert and wait for next screen
                self.gui.send(True)
                time.sleep(1)
                continue
            time.sleep(0.3)
        self._send_with_retry(1, "Menu: recovery phrase", require_change=True)
        mnemonic = "abandon " * 11 + "about"
        self._send_with_retry(mnemonic, "Mnemonic", require_change=True)

    def start(self):
        print("Resetting device...")
        self.gui = SerialSocket(self.debug_port, baudrate=9600, timeout=5)
        self.gui.command("TEST_RESET", timeout=5)
        time.sleep(3)
        self.gui._reopen()
        self.started = True

    def load(self):
        self.gui = SerialSocket(self.debug_port, baudrate=9600, timeout=5)

        print("Waiting for device ready...")
        for i in range(60):
            try:
                resp = self.gui.status()
                if b"OK:READY" in resp:
                    print("Device ready")
                    break
            except Exception as e:
                print(f"Poll error: {e}")
            time.sleep(0.5)
        else:
            raise RuntimeError("Device not ready")

        print("Wiping wallet storage...")
        wipe_ok = False
        for attempt in range(3):
            resp = self.gui.command("TEST_WIPE", timeout=5)
            if b"OK:WIPED" in resp:
                wipe_ok = True
                break
            print("Wipe failed (attempt %d), retrying..." % (attempt + 1))
            time.sleep(1)
        if not wipe_ok:
            raise RuntimeError("Wipe failed after 3 attempts: %s" % repr(resp))
        print("Wallet storage wiped, resetting device...")
        self.gui.command("TEST_RESET", timeout=5)
        time.sleep(3)
        self.gui._reopen()
        for i in range(60):
            try:
                resp = self.gui.status()
                if b"OK:READY" in resp:
                    print("Device ready after wipe")
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Device not ready after wipe")

        self._load_internal_flash()
        self._wait_for_usb_vcp()

    def shutdown(self):
        errors = self.dump_debug_log()
        if errors:
            print("\n=== Device errors during test run ===")
            for line in errors:
                print("  " + line)
            print("=== End device errors ===\n")
        print("Shutting down...")
        if self.gui is not None:
            try:
                self.gui.close()
            except Exception:
                pass
        if self.usb is not None:
            try:
                self.usb.close()
            except Exception:
                pass
        time.sleep(0.5)

    def _capture_debug(self):
        try:
            import serial
            s = serial.Serial(self.debug_port, 9600, timeout=0.5)
            try:
                while s.in_waiting:
                    line = s.readline()
                    if line:
                        text = line.decode(errors='replace').rstrip()
                        self._debug_log.append(text)
            except Exception:
                pass
            s.close()
        except Exception:
            pass

    def dump_debug_log(self):
        self._capture_debug()
        errors = [l for l in self._debug_log if 'EXCEPTION' in l or 'TRACEBACK' in l or 'error' in l.lower()]
        self._debug_log.clear()
        return errors

    def query(self, data, commands=[]):
        if isinstance(data, str):
            data = data.encode()
        if data[-1:] not in b"\r\n":
            data = data + b"\r\n"
        res = b""
        for _ in range(3):
            res = self.usb.query(data)
            if res == b"ACK\r\n":
                break
            time.sleep(0.4)
        assert res == b"ACK\r\n", f"Expected ACK, got: {res}"
        for command in commands:
            self.gui.send(command)
            time.sleep(1.5)
        if commands:
            self.usb._stash = b""
            self.usb._drain_popup()
            if self.usb._stash:
                res = self.usb.receive()
                return res.strip()
        res = self.usb.receive()
        return res.strip()


sim = HardwareController()
