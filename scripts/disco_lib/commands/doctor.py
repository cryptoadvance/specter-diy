"""Automated board diagnostics command."""

import click

from ..openocd import OpenOCD
from ..serial import SerialDevice
from ..diagnostics import run_diagnostics

_ocd = OpenOCD()
_ser = SerialDevice()


@click.command()
@click.option("--verbose", "-v", is_flag=True, help="Show all check details")
@click.option("--no-log", is_flag=True, help="Skip writing log file")
def doctor(verbose: bool, no_log: bool):
    """Run automated board diagnostics.

    Performs non-invasive checks on OpenOCD, JTAG target, fault registers,
    FPU configuration, vector table, and USB/REPL connectivity.

    \b
    Diagnostic codes:
      OPENOCD_NOT_RUNNING    - OpenOCD server not started
      TARGET_NOT_RESPONDING  - JTAG connected but MCU not responding
      CPU_STUCK              - PC doesn't change (infinite loop/fault)
      USAGEFAULT_NOCP        - FPU instruction with FPU disabled
      HARDFAULT_FORCED       - Lower fault escalated to HardFault
      INVALID_MEMORY_ACCESS  - Bus fault at invalid address
      FPU_DISABLED           - CPACR doesn't enable FPU
      INVALID_INITIAL_SP     - Vector table SP not in RAM
      INVALID_RESET_VECTOR   - Reset handler not in Flash
      USB_OTG_MISSING        - No USB CDC device
      REPL_UNRESPONSIVE      - CDC present but no REPL response

    \b
    Logs are saved to: /tmp/disco_log/YYYY-MM-DD_HH-MM-SS.md
    """
    run_diagnostics(_ocd, _ser, verbose, no_log)
