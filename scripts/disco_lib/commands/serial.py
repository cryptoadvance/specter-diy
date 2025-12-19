"""Serial/REPL communication commands."""

import re
import time

import click

from ..openocd import OpenOCD
from ..serial import SerialDevice

_ocd = OpenOCD()
_ser = SerialDevice()


def _check_usb_otg_connected() -> bool:
    """Check if USB OTG serial (REPL) is available."""
    for path, blacklisted in _ser.list_devices():
        if blacklisted:
            continue
        match = re.search(r'usbmodem(\w+)', path)
        if match and len(match.group(1)) > 6:
            return True
    return False


@click.group()
def serial():
    """Serial/REPL communication.

    Communicate with the MicroPython REPL via USB CDC serial. The REPL
    is available on the USB OTG port (miniUSB connector), not the ST-LINK
    port (microUSB).

    \b
    USB Connections (STM32F469-Discovery):
      MicroUSB (CN1)  - ST-LINK: JTAG/SWD + Virtual COM Port (VCP)
      MiniUSB (CN13)  - USB OTG: MicroPython REPL (CDC serial)

    \b
    Device Detection:
      - Only /dev/tty.* devices are used (not /dev/cu.*)
      - ST-LINK VCP has short ID (e.g., "21403")
      - USB OTG CDC has long ID (e.g., "335D375F33382")
      - USB OTG is preferred for REPL access

    \b
    REPL Wake Sequence:
      The 'repl' command sends Ctrl-C + multiple newlines to wake the
      REPL from any state. Connection is kept open during wake to avoid
      missing the response.

    \b
    Troubleshooting:
      - Run 'disco cables' to check USB connections
      - Ensure miniUSB cable is connected for REPL
      - USB CDC only appears after firmware enables USB communication
      - If no response, try 'disco serial console' for interactive debug

    \b
    Examples:
      disco serial list           # See available devices
      disco serial repl           # Quick REPL test (3s)
      disco serial repl 10        # Longer timeout
      disco serial console        # Interactive session (Ctrl-A K to exit)
    """
    pass


@serial.command("list")
def serial_list():
    """List available serial devices."""
    _ser.show_devices()


@serial.command("test")
def serial_test():
    """Quick test for serial output (2 sec)."""
    click.secho("=== Serial Port Test ===", fg="blue")
    dev = _ser.require_device()
    click.echo(f"Testing: {dev} @ {_ser.baud}")
    click.echo("Waiting 2 seconds for output...")
    output = _ser.read_timeout(dev, 2.0)
    if output:
        click.echo(output)
    else:
        click.echo("(no output received)")


@serial.command("repl")
@click.argument("timeout", default=3, type=int)
def serial_repl(timeout: int):
    """Test REPL connection (default 3s timeout)."""
    click.secho(f"=== REPL Test ({timeout}s timeout) ===", fg="blue")

    if not _check_usb_otg_connected():
        click.secho("Warning: USB OTG (miniUSB) not detected!", fg="red")
        click.secho("REPL requires miniUSB cable connected to USB OTG port", fg="yellow")
        click.echo()

    dev = _ser.require_device()
    click.echo(f"Device: {dev}")
    click.echo("Sending wake-up sequence...")

    output = _ser.repl_test(dev, timeout)
    if output:
        click.secho("Response received:", fg="green")
        click.echo(output)
        if ">>>" in output:
            click.secho("REPL prompt detected!", fg="green")
    else:
        click.secho("(no response)", fg="yellow")


@serial.command("boot")
@click.argument("timeout", default=5, type=int)
def serial_boot(timeout: int):
    """Reset board and capture boot output (default 5s)."""
    click.secho(f"=== Boot Capture ({timeout}s timeout) ===", fg="blue")
    dev = _ser.require_device()
    _ocd.require_running()

    click.echo(f"Device: {dev}")
    click.echo("Resetting board and capturing output...")

    _ocd.send("reset run")
    time.sleep(0.3)
    output = _ser.read_timeout(dev, timeout)

    if output:
        click.echo(output)
    click.secho("\nCapture complete", fg="green")


@serial.command("console")
def serial_console():
    """Open interactive serial console (screen)."""
    dev = _ser.require_device()
    _ser.exec_console(dev)
