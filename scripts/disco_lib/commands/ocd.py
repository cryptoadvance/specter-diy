"""OpenOCD server management commands."""

import click

from .. import GDB_PORT, OPENOCD_PORT
from ..openocd import OpenOCD

_ocd = OpenOCD()


@click.group()
def ocd():
    """OpenOCD server management.

    OpenOCD (Open On-Chip Debugger) provides JTAG/SWD access to the
    STM32F469 via the ST-LINK interface on the MicroUSB connector.

    \b
    The OpenOCD server must be running for most disco commands to work:
      - All 'cpu' commands (halt, resume, reset, step, etc.)
      - All 'mem' commands (read, vectors, dump)
      - All 'flash' commands (program, erase, info)
      - The 'check' diagnostic command

    \b
    Connection details:
      - Telnet port: 4444 (for manual commands)
      - GDB port: 3333 (for GDB debugging)
      - Config: board/stm32f469discovery.cfg
      - Log file: /tmp/openocd.log

    \b
    Troubleshooting:
      - Check MicroUSB cable is connected to ST-LINK port
      - Run 'disco cables' to verify JTAG connection
      - Check /tmp/openocd.log for errors
    """
    pass


@ocd.command("connect")
def ocd_connect():
    """Start OpenOCD server (background)."""
    _ocd.start()


@ocd.command("disconnect")
def ocd_disconnect():
    """Stop OpenOCD server."""
    _ocd.stop()


@ocd.command("status")
def ocd_status():
    """Check if OpenOCD is running and board connected."""
    if _ocd.is_running():
        click.secho("OpenOCD: running", fg="green")
        click.echo(f"Ports: telnet={OPENOCD_PORT}, gdb={GDB_PORT}")
        click.echo(_ocd.send("reg pc sp"))
    else:
        click.secho("OpenOCD: not running", fg="red")


@ocd.command("cmd")
@click.argument("command", nargs=-1, required=True)
def ocd_cmd(command):
    """Send raw OpenOCD command.

    \b
    Examples:
      disco ocd cmd halt
      disco ocd cmd "mdw 0x08000000 4"
      disco ocd cmd flash probe 0
      disco ocd cmd targets
    """
    _ocd.require_running()
    cmd_str = " ".join(command)
    click.secho(f"> {cmd_str}", fg="cyan")
    result = _ocd.send(cmd_str)
    if result:
        click.echo(result)
    else:
        click.secho("(no output)", fg="yellow")
