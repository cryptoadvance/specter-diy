"""Memory inspection commands."""

import re

import click

from ..openocd import OpenOCD

_ocd = OpenOCD()


@click.group()
def mem():
    """Memory inspection commands.

    Read memory from the STM32F469 via JTAG/OpenOCD. The CPU is halted
    during memory reads to ensure consistent data.

    \b
    STM32F469 Memory Map:
      0x08000000  Flash (2MB) - Bootloader starts here
      0x08020000  Firmware area (when using USE_DBOOT bootloader)
      0x20000000  SRAM (320KB)
      0x40000000  Peripherals
      0xE0000000  Cortex-M4 internal (SysTick, NVIC, etc.)

    \b
    Vector Table Format (first 8 words):
      [0] Initial SP      - Stack pointer after reset
      [1] Reset handler   - Entry point after reset
      [2] NMI handler     - Non-maskable interrupt
      [3] HardFault       - All fault types if not configured
      [4] MemManage       - Memory protection fault
      [5] BusFault        - Bus error
      [6] UsageFault      - Undefined instruction, etc.
      [7] Reserved

    \b
    Examples:
      disco mem read 0x20000000 16    # Read 16 words from SRAM
      disco mem vectors               # Show bootloader vectors
      disco mem vectors --fw          # Show firmware vectors
    """
    pass


@mem.command("read")
@click.argument("addr", default="0x08000000")
@click.argument("count", default=8, type=int)
def mem_read(addr: str, count: int):
    """Read memory words from address."""
    _ocd.require_running()
    click.secho(f"=== Memory @ {addr} ({count} words) ===", fg="blue")
    _ocd.send("halt")
    click.echo(_ocd.send(f"mdw {addr} {count}"))


@mem.command("vectors")
@click.option("--fw", is_flag=True, help="Show firmware vectors at 0x08020000 instead")
def mem_vectors(fw: bool):
    """Show vector table (bootloader or firmware)."""
    _ocd.require_running()
    _ocd.send("halt")

    if fw:
        click.secho("=== Vector Table @ 0x08020000 (Firmware) ===", fg="blue")
        click.echo(_ocd.send("mdw 0x08020000 8"))
    else:
        click.secho("=== Vector Table @ 0x08000000 (Bootloader) ===", fg="blue")
        result = _ocd.send("mdw 0x08000000 8")
        click.echo(result)
        click.echo()

        match = re.search(r":\s*(.+)", result)
        if match:
            words = match.group(1).split()
            labels = [
                "Initial SP", "Reset", "NMI", "HardFault",
                "MemManage", "BusFault", "UsageFault", "Reserved",
            ]
            for label, word in zip(labels, words[:8]):
                click.echo(f"  {label}: 0x{word}")


@mem.command("dump")
@click.argument("count", default=32, type=int)
def mem_dump(count: int):
    """Dump first N words from flash (default 32)."""
    _ocd.require_running()
    click.secho(f"=== Flash @ 0x08000000 ({count} words) ===", fg="blue")
    _ocd.send("halt")
    click.echo(_ocd.send(f"mdw 0x08000000 {count}"))


@mem.command("save")
@click.argument("file", type=click.Path())
@click.argument("addr")
@click.argument("size")
def mem_save(file: str, addr: str, size: str):
    """Save memory region to binary file.

    \b
    Arguments:
      FILE  Output filename
      ADDR  Start address (hex, e.g., 0x08000000)
      SIZE  Number of bytes (hex or decimal, e.g., 0x20000 or 131072)

    \b
    Examples:
      disco mem save flash.bin 0x08000000 0x200000    # Dump all flash (2MB)
      disco mem save firmware.bin 0x08020000 0x100000 # Dump firmware area
      disco mem save ram.bin 0x20000000 0x50000       # Dump SRAM
    """
    import os

    _ocd.require_running()
    _ocd.send("halt")

    # Parse size (support hex or decimal)
    if size.startswith("0x"):
        byte_count = int(size, 16)
    else:
        byte_count = int(size)

    file = os.path.abspath(file)
    click.secho(f"=== Saving Memory to File ===", fg="blue")
    click.echo(f"Address: {addr}")
    click.echo(f"Size: {byte_count:,} bytes ({byte_count // 1024} KB)")
    click.echo(f"File: {file}")

    # Use OpenOCD dump_image command
    result = _ocd.send(f"dump_image {file} {addr} {byte_count}", timeout=60)
    click.echo(result)

    if os.path.exists(file):
        actual_size = os.path.getsize(file)
        click.secho(f"Saved {actual_size:,} bytes to {file}", fg="green")
    else:
        click.secho("Failed to create file", fg="red")
