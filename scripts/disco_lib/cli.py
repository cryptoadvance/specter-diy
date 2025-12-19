"""Main CLI entry point for disco."""

import re

import click

from .openocd import OpenOCD
from .serial import SerialDevice
from .commands import ocd, cpu, mem, flash, serial, repl, doctor

_ocd = OpenOCD()
_ser = SerialDevice()


@click.group()
def cli():
    """STM32F469 Discovery board debugging utility.

    Commands are organized into groups:

    \b
      ocd     - OpenOCD server management
      cpu     - CPU control (halt, resume, reset, step)
      mem     - Memory inspection
      flash   - Flash programming
      serial  - Serial device detection
      repl    - MicroPython REPL interaction

    Top-level commands:

    \b
      doctor  - Automated diagnostics with logging
      check   - Run full board diagnostics
      cables  - Detect connected USB cables
    """
    pass


# Register command groups
cli.add_command(ocd)
cli.add_command(cpu)
cli.add_command(mem)
cli.add_command(flash)
cli.add_command(serial)
cli.add_command(repl)
cli.add_command(doctor)


# =============================================================================
# TOP-LEVEL COMMANDS
# =============================================================================


@cli.command()
def cables():
    """Detect connected USB cables."""
    click.secho("=== Cable Detection ===", fg="blue")

    stlink_serial = False
    usb_otg_serial = False

    devices = _ser.list_devices()
    for path, blacklisted in devices:
        if blacklisted:
            continue
        match = re.search(r'usbmodem(\w+)', path)
        if match:
            port_id = match.group(1)
            if len(port_id) <= 6:
                stlink_serial = True
            else:
                usb_otg_serial = True

    jtag_ok = False
    ocd_running = _ocd.is_running()
    if ocd_running:
        # Briefly halt to read PC, then resume to keep USB working
        _ocd.send("halt")
        result = _ocd.send("reg pc")
        _ocd.send("resume")
        jtag_ok = "0x" in result

    click.echo()
    click.echo("MicroUSB (ST-LINK connector):")
    if jtag_ok:
        click.secho("  JTAG: connected", fg="green")
    elif ocd_running:
        click.secho("  JTAG: OpenOCD running but target not responding", fg="yellow")
    else:
        click.secho("  JTAG: OpenOCD not running (use 'disco ocd connect')", fg="red")
    if stlink_serial:
        click.secho("  Serial (VCP): available", fg="green")
    else:
        click.secho("  Serial (VCP): not detected", fg="yellow")

    click.echo()
    click.echo("MiniUSB (USB OTG connector):")
    if usb_otg_serial:
        click.secho("  Serial (CDC): available - REPL should work", fg="green")
    else:
        click.secho("  Serial (CDC): not connected - REPL unavailable", fg="red")

    click.echo()
    if not usb_otg_serial:
        click.secho("Tip: Connect miniUSB cable for REPL access", fg="yellow")


@cli.command()
@click.option("--no-resume", is_flag=True, help="Keep CPU halted after check (disconnects USB)")
def check(no_resume: bool):
    """Run full board diagnostics.

    By default, resumes CPU after check to keep USB CDC working.
    Use --no-resume to keep halted for further debugging.
    """
    _ocd.require_running()
    click.secho("=== Board Diagnostic Check ===", fg="blue")
    _ocd.send("halt")

    click.secho("\n1. CPU State", fg="yellow")
    click.echo(_ocd.send("reg pc"))
    click.echo(_ocd.send("reg sp"))
    click.echo(_ocd.send("reg lr"))

    click.secho("\n2. Vector Table (0x08000000)", fg="yellow")
    click.echo(_ocd.send("mdw 0x08000000 4"))

    click.secho("\n3. Firmware Area (0x08020000)", fg="yellow")
    click.echo(_ocd.send("mdw 0x08020000 4"))

    click.secho("\n4. RAM Check (0x20000000)", fg="yellow")
    click.echo(_ocd.send("mdw 0x20000000 4"))

    click.secho("\n5. Flash Info", fg="yellow")
    click.echo(_ocd.send("flash info 0"))

    if no_resume:
        click.secho("\nCPU left halted (--no-resume). USB CDC disconnected.", fg="yellow")
    else:
        _ocd.send("resume")
        click.secho("\nCPU resumed. USB CDC should reconnect.", fg="green")
