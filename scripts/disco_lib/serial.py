"""Serial device detection and communication."""

import glob
import os
import sys
import time

import click
import serial

from . import BAUD_RATE, SERIAL_BLACKLIST


class SerialDevice:
    """Handle serial device detection and communication."""

    def __init__(self, blacklist: list[str] = None):
        self.blacklist = SERIAL_BLACKLIST if blacklist is None else blacklist
        self.baud = BAUD_RATE

    def is_blacklisted(self, path: str) -> bool:
        """Check if device path matches blacklist."""
        return any(pattern in path for pattern in self.blacklist)

    def list_devices(self) -> list[tuple[str, bool]]:
        """List USB modem devices. Returns (path, is_blacklisted) tuples.

        Only lists tty.* devices (terminal access). cu.* devices are for
        callout/modems and can have carrier-detect issues.
        """
        devices = []
        for path in glob.glob("/dev/tty.usbmodem*"):
            devices.append((path, self.is_blacklisted(path)))

        # Sort by path length descending - longer IDs (like 335D375F33382)
        # are USB OTG, shorter (like 21403) are ST-LINK VCP
        return sorted(devices, key=lambda x: len(x[0]), reverse=True)

    def auto_detect(self) -> str | None:
        """Auto-detect serial device, filtering blacklist."""
        # Check env override first
        env_dev = os.environ.get("SERIAL_DEV")
        if env_dev:
            if os.path.exists(env_dev):
                return env_dev
            click.secho(f"SERIAL_DEV={env_dev} does not exist", fg="red", err=True)
            return None

        # Find first non-blacklisted device
        for path, blacklisted in self.list_devices():
            if not blacklisted:
                return path

        return None

    def require_device(self) -> str:
        """Get serial device or raise exception."""
        dev = self.auto_detect()
        if not dev:
            raise click.ClickException(
                "No USB modem device found (after filtering blacklist)"
            )
        return dev

    def read_timeout(self, dev: str, timeout: float) -> str:
        """Read from serial port with timeout."""
        try:
            with serial.Serial(dev, self.baud, timeout=timeout) as ser:
                data = ser.read(4096)
                return data.decode("utf-8", errors="replace")
        except serial.SerialException as e:
            raise click.ClickException(f"Serial error: {e}")

    def repl_test(self, dev: str, timeout: float) -> str | None:
        """Send wake sequence and wait for REPL response.

        Keep connection open during wake+read to avoid missing response.
        """
        try:
            with serial.Serial(dev, self.baud, timeout=timeout) as ser:
                # Ctrl-C to interrupt any running code
                ser.write(b"\x03")
                time.sleep(0.1)
                # Multiple newlines to wake REPL
                ser.write(b"\r\n\r\n\r\n")
                time.sleep(0.3)
                # One more to trigger prompt
                ser.write(b"\r\n")

                # Read response
                click.echo(f"Waiting {timeout}s for response...")
                data = ser.read(4096)
                return data.decode("utf-8", errors="replace") if data else None
        except serial.SerialException as e:
            raise click.ClickException(f"Serial error: {e}")

    def exec_console(self, dev: str) -> None:
        """Replace process with screen for interactive console."""
        click.secho(f"Opening console: {dev} @ {self.baud}", fg="green")
        click.echo("Press Ctrl-A then K to exit")
        os.execvp("screen", ["screen", dev, str(self.baud)])

    def show_devices(self) -> None:
        """Display available serial devices."""
        click.secho("=== Serial Devices ===", fg="blue")
        click.echo("USB Modem devices (tty.*):")

        devices = self.list_devices()
        visible = [(p, b) for p, b in devices if not b]
        blacklisted_count = sum(1 for _, b in devices if b)

        if visible:
            for path, _ in visible:
                click.echo(f"  {path}")
        else:
            click.echo("  (none)")

        if blacklisted_count:
            click.secho(f"  ({blacklisted_count} blacklisted)", fg="yellow")

        click.echo()
        click.echo("USB Serial devices (tty.usbserial*):")
        usb_serial = glob.glob("/dev/tty.usbserial*")
        if usb_serial:
            for path in usb_serial:
                click.echo(f"  {path}")
        else:
            click.echo("  (none)")
