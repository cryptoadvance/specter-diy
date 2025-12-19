"""CPU control commands."""

import re

import click

from ..openocd import OpenOCD

_ocd = OpenOCD()


@click.group()
def cpu():
    """CPU control commands.

    Control the ARM Cortex-M4 CPU via JTAG/SWD through OpenOCD.
    These commands require OpenOCD to be running (disco ocd connect).

    \b
    ⚠️  WARNING: Halting the CPU disconnects USB CDC (REPL).
    Use 'disco cpu resume' or 'disco ocd cmd reset run' to restore.

    \b
    Typical debug workflow:
      1. disco ocd connect     # Start OpenOCD
      2. disco cpu halt        # Stop execution (USB disconnects!)
      3. disco cpu pc          # See where we are
      4. disco cpu regs        # Check register state
      5. disco cpu step        # Single-step through code
      6. disco cpu resume      # Continue running (USB reconnects)
    """
    pass


@cpu.command("halt")
def cpu_halt():
    """Halt the CPU.

    ⚠️  This disconnects USB CDC - REPL will be unavailable until resumed.
    """
    _ocd.require_running()
    _ocd.send("halt")
    click.secho("CPU halted", fg="green")
    click.secho("Note: USB CDC (REPL) disconnected while halted", fg="yellow")
    click.echo(_ocd.send("reg pc sp"))


@cpu.command("resume")
def cpu_resume():
    """Resume execution."""
    _ocd.require_running()
    _ocd.send("resume")
    click.secho("CPU resumed", fg="green")


@cpu.command("reset")
def cpu_reset():
    """Reset and halt."""
    _ocd.require_running()
    _ocd.send("reset halt")
    click.secho("CPU reset and halted", fg="green")
    click.echo(_ocd.send("reg pc sp"))


@cpu.command("step")
def cpu_step():
    """Single step."""
    _ocd.require_running()
    _ocd.send("step")
    click.echo(_ocd.send("reg pc"))


@cpu.command("regs")
def cpu_regs():
    """Show all CPU registers."""
    _ocd.require_running()
    click.secho("=== CPU Registers ===", fg="blue")
    _ocd.send("halt")
    click.echo(_ocd.send("reg"))


@cpu.command("pc")
def cpu_pc():
    """Show current PC and memory around it."""
    _ocd.require_running()
    click.secho("=== Current PC ===", fg="blue")
    _ocd.send("halt")

    result = _ocd.send("reg pc")
    match = re.search(r"0x[0-9a-fA-F]+", result)
    if match:
        pc_val = int(match.group(), 16)
        click.echo(f"PC: 0x{pc_val:08x}")
        click.echo()
        click.echo("Memory around PC:")
        pc_aligned = (pc_val & ~0xF) - 0x10
        click.echo(_ocd.send(f"mdw 0x{pc_aligned:08x} 16"))
    else:
        click.echo(result)


@cpu.command("stack")
@click.argument("count", default=16, type=int)
def cpu_stack(count: int):
    """Show stack (N words, default 16)."""
    _ocd.require_running()
    click.secho(f"=== Stack ({count} words) ===", fg="blue")
    _ocd.send("halt")

    result = _ocd.send("reg sp")
    match = re.search(r"0x[0-9a-fA-F]+", result)
    if match:
        sp_val = int(match.group(), 16)
        click.echo(f"SP: 0x{sp_val:08x}")
        click.echo(_ocd.send(f"mdw 0x{sp_val:08x} {count}"))
    else:
        click.echo(result)


@cpu.command("gdb")
@click.argument("elf", type=click.Path(exists=True), required=False)
@click.option("--run", is_flag=True, help="Actually launch GDB (default: just print command)")
def cpu_gdb(elf: str, run: bool):
    """Show or launch GDB command for debugging.

    \b
    With no arguments, prints the GDB command to connect to target.
    With --run, actually launches GDB.

    \b
    Examples:
      disco cpu gdb                           # Print GDB command
      disco cpu gdb firmware.elf              # Print command with ELF
      disco cpu gdb firmware.elf --run        # Launch GDB with ELF
      disco cpu gdb --run                     # Launch GDB without ELF

    \b
    GDB Commands Cheat Sheet:
      target remote :3333    # Connect to OpenOCD (done automatically)
      monitor halt           # Halt CPU via OpenOCD
      monitor reset halt     # Reset and halt
      load                   # Load ELF to target (if ELF provided)
      break main             # Set breakpoint
      continue               # Run
      step / next            # Step into / over
      info registers         # Show registers
      x/10x $sp              # Examine memory at SP
    """
    import os
    import shutil

    _ocd.require_running()

    # Find GDB
    gdb_names = ["arm-none-eabi-gdb", "gdb-multiarch", "gdb"]
    gdb_path = None
    for name in gdb_names:
        if shutil.which(name):
            gdb_path = name
            break

    if not gdb_path:
        click.secho("Error: No ARM GDB found. Install arm-none-eabi-gdb", fg="red")
        return

    # Build command
    cmd_parts = [gdb_path]
    if elf:
        cmd_parts.append(os.path.abspath(elf))
    cmd_parts.extend(["-ex", "target remote :3333"])

    cmd_str = " ".join(f'"{p}"' if " " in p else p for p in cmd_parts)

    if run:
        click.secho(f"Launching: {cmd_str}", fg="green")
        os.execvp(gdb_path, cmd_parts)
    else:
        click.secho("=== GDB Command ===", fg="blue")
        click.echo(cmd_str)
        click.echo()
        click.secho("Run with --run flag to launch, or copy/paste the command", fg="yellow")
