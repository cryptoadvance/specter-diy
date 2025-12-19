"""REPL interaction commands."""

import os
import time
from contextlib import contextmanager

import click
import serial as pyserial

from ..serial import SerialDevice

_ser = SerialDevice()


@contextmanager
def _mpremote_transport(dev: str):
    """Context manager for mpremote SerialTransport."""
    from mpremote.transport_serial import SerialTransport
    transport = SerialTransport(dev, _ser.baud)
    transport.enter_raw_repl()
    try:
        yield transport
    finally:
        transport.exit_raw_repl()
        transport.close()


def _repl_exec(dev: str, code: str, timeout: float = 3.0) -> str:
    """Execute Python code on REPL and return output."""
    with pyserial.Serial(dev, _ser.baud, timeout=timeout) as ser:
        # Interrupt any running code
        ser.write(b"\x03")
        time.sleep(0.1)
        # Clear buffer
        ser.read(4096)

        # Send code
        ser.write(code.encode() + b"\r\n")
        time.sleep(0.5)

        # Read response
        data = ser.read(8192)
        text = data.decode("utf-8", errors="replace")

        # Filter output: remove command echo and trailing prompt
        lines = text.split("\n")
        output_lines = []
        for line in lines:
            line = line.rstrip("\r")
            # Skip command echo
            if line.strip() == code.strip():
                continue
            # Skip empty prompts
            if line.strip() in (">>>", "...", ""):
                continue
            # Remove leading >>> if present
            if line.startswith(">>> "):
                line = line[4:]
            elif line.startswith("... "):
                line = line[4:]
            output_lines.append(line)

        return "\n".join(output_lines).strip()


@click.group()
def repl():
    """MicroPython REPL interaction.

    Execute Python code and manage files on the board.

    \b
    Code execution:
      disco repl exec "print('hello')"
      disco repl exec "help()" --timeout 5
      disco repl info
      disco repl modules
      disco repl hello "Hi!"

    \b
    File operations (uses mpremote):
      disco repl ls                         # list /flash
      disco repl cat /flash/main.py         # print file
      disco repl cp local.py :/flash/       # copy to board
      disco repl cp :/flash/file.py ./      # copy from board
      disco repl rm /flash/test.py          # remove file
    """
    pass


@repl.command("exec")
@click.argument("code")
@click.option("--timeout", "-t", default=3, type=int, help="Response timeout in seconds")
def repl_exec(code: str, timeout: int):
    """Execute Python code on REPL.

    \b
    Examples:
      disco repl exec "1 + 1"
      disco repl exec "import gc; gc.collect(); gc.mem_free()"
      disco repl exec "help()"
    """
    dev = _ser.require_device()
    try:
        output = _repl_exec(dev, code, timeout)
        if output:
            click.echo(output)
    except pyserial.SerialException as e:
        raise click.ClickException(f"Serial error: {e}")


@repl.command("info")
def repl_info():
    """Show board info (sys.implementation, machine.freq, etc)."""
    dev = _ser.require_device()
    try:
        click.secho("=== Board Info ===", fg="blue")

        # Version
        output = _repl_exec(dev, "import sys; print(sys.implementation)", timeout=2)
        click.echo(f"Implementation: {output}")

        # Frequency
        output = _repl_exec(dev, "import machine; print(machine.freq())", timeout=2)
        click.echo(f"CPU Frequency: {output} Hz")

        # Memory
        output = _repl_exec(dev, "import gc; gc.collect(); print(gc.mem_free())", timeout=2)
        click.echo(f"Free Memory: {output} bytes")

        # Platform
        output = _repl_exec(dev, "import sys; print(sys.platform)", timeout=2)
        click.echo(f"Platform: {output}")

    except pyserial.SerialException as e:
        raise click.ClickException(f"Serial error: {e}")


@repl.command("modules")
@click.option("--timeout", "-t", default=5, type=int, help="Response timeout")
def repl_modules(timeout: int):
    """List available MicroPython modules."""
    dev = _ser.require_device()
    try:
        click.secho("=== Available Modules ===", fg="blue")
        output = _repl_exec(dev, "help('modules')", timeout=timeout)
        click.echo(output)
    except pyserial.SerialException as e:
        raise click.ClickException(f"Serial error: {e}")


@repl.command("help")
def repl_help():
    """Show MicroPython help."""
    dev = _ser.require_device()
    try:
        output = _repl_exec(dev, "help()", timeout=3)
        click.echo(output)
    except pyserial.SerialException as e:
        raise click.ClickException(f"Serial error: {e}")


@repl.command("reset")
def repl_reset():
    """Soft-reset the board (Ctrl-D)."""
    dev = _ser.require_device()
    try:
        with pyserial.Serial(dev, _ser.baud, timeout=3) as ser:
            # Send Ctrl-D for soft reset
            ser.write(b"\x03")  # Ctrl-C first
            time.sleep(0.1)
            ser.write(b"\x04")  # Ctrl-D
            time.sleep(1)
            data = ser.read(4096)
            click.echo(data.decode("utf-8", errors="replace"))
            click.secho("Soft reset sent", fg="green")
    except pyserial.SerialException as e:
        raise click.ClickException(f"Serial error: {e}")


@repl.command("hello")
@click.argument("message", default="Hello World!")
def repl_hello(message: str):
    """Display a message on the screen (large font, centered).

    \b
    Examples:
      disco repl hello
      disco repl hello "Specter DIY"
    """
    dev = _ser.require_device()
    try:
        # Initialize display with delay for hardware to settle
        click.echo("Initializing display...")
        _repl_exec(dev, "import display; display.init(True); import time; time.sleep_ms(100)", timeout=5)

        # Create label with large font (28 is max built-in size)
        escaped_msg = message.replace("'", "\\'")
        code = (
            f"import lvgl as lv; scr = lv.scr_act(); scr.clean(); "
            f"lbl = lv.label(scr); lbl.set_text('{escaped_msg}'); "
            f"style = lbl.get_style(lv.label.STYLE.MAIN); "
            f"style.text.font = lv.font_roboto_28; "
            f"lbl.refresh_style(); lbl.align(None, lv.ALIGN.CENTER, 0, 0)"
        )

        click.echo(f"Displaying: {message}")
        _repl_exec(dev, code, timeout=3)
        click.secho("Done!", fg="green")

    except pyserial.SerialException as e:
        raise click.ClickException(f"Serial error: {e}")


@repl.command("ls")
@click.argument("path", default="/flash")
def repl_ls(path: str):
    """List files on the board.

    \b
    Examples:
      disco repl ls
      disco repl ls /flash
      disco repl ls /sd
    """
    dev = _ser.require_device()
    with _mpremote_transport(dev) as transport:
        try:
            files = transport.fs_listdir(path)
            click.secho(f"=== {path} ===", fg="blue")
            for f in files:
                if f.st_mode & 0x4000:  # directory
                    click.secho(f"  {f.name}/", fg="cyan")
                else:
                    click.echo(f"  {f.name} ({f.st_size} bytes)")
        except Exception as e:
            raise click.ClickException(f"Error listing {path}: {e}")


@repl.command("cat")
@click.argument("path")
def repl_cat(path: str):
    """Print file contents from board.

    \b
    Examples:
      disco repl cat /flash/main.py
      disco repl cat /flash/boot.py
    """
    dev = _ser.require_device()
    with _mpremote_transport(dev) as transport:
        try:
            data = transport.fs_readfile(path)
            click.echo(data.decode("utf-8", errors="replace"))
        except Exception as e:
            raise click.ClickException(f"Error reading {path}: {e}")


@repl.command("cp")
@click.argument("src")
@click.argument("dest")
def repl_cp(src: str, dest: str):
    """Copy file to/from board.

    Use : prefix for board paths.

    \b
    Examples:
      disco repl cp local.py :/flash/local.py    # local -> board
      disco repl cp :/flash/main.py ./main.py    # board -> local
    """
    dev = _ser.require_device()

    if src.startswith(":") and not dest.startswith(":"):
        # Board -> local
        board_path = src[1:]
        local_path = dest
        with _mpremote_transport(dev) as transport:
            try:
                data = transport.fs_readfile(board_path)
                with open(local_path, "wb") as f:
                    f.write(data)
                click.secho(f"Copied {board_path} -> {local_path} ({len(data)} bytes)", fg="green")
            except Exception as e:
                raise click.ClickException(f"Error copying: {e}")

    elif not src.startswith(":") and dest.startswith(":"):
        # Local -> board
        local_path = src
        board_path = dest[1:]
        if not os.path.exists(local_path):
            raise click.ClickException(f"Local file not found: {local_path}")
        with open(local_path, "rb") as f:
            data = f.read()
        with _mpremote_transport(dev) as transport:
            try:
                transport.fs_writefile(board_path, data)
                click.secho(f"Copied {local_path} -> {board_path} ({len(data)} bytes)", fg="green")
            except Exception as e:
                raise click.ClickException(f"Error copying: {e}")

    else:
        raise click.ClickException("Use : prefix for board paths (e.g., :/flash/file.py)")


@repl.command("import")
@click.argument("module", default="hardwaretest")
@click.option("--timeout", "-t", default=10, type=int, help="Response timeout in seconds")
def repl_import(module: str, timeout: int):
    """Import a module and show output/errors.

    Useful for testing boot sequence - imports the module that boot.py
    would normally run via pyb.main(). Shows any import errors or
    stacktraces that occur during module initialization.

    \b
    This is the recommended way to debug boot failures:
      1. Flash debug firmware
      2. Run: disco repl import
      3. See any stacktraces from failed imports

    \b
    Examples:
      disco repl import                    # import hardwaretest (default)
      disco repl import gui                # test GUI module only
      disco repl import gui.components     # test specific submodule
    """
    from ..openocd import OpenOCD

    ocd = OpenOCD()

    # Stop OpenOCD if running (it blocks USB CDC)
    if ocd.is_running():
        click.echo("Stopping OpenOCD...")
        ocd.stop()
        time.sleep(1)

    # Wait for USB CDC device
    click.echo("Waiting for USB CDC device...")
    for i in range(10):
        dev = _ser.auto_detect()
        if dev:
            break
        time.sleep(1)
    else:
        raise click.ClickException("USB CDC device not found. Is miniUSB connected?")

    click.echo(f"Device: {dev}")
    click.echo(f"Importing '{module}'...")
    click.echo()

    try:
        output = _repl_exec(dev, f"import {module}", timeout=timeout)
        if output:
            click.echo(output)
        else:
            click.secho(f"Module '{module}' imported successfully (no output)", fg="green")
    except pyserial.SerialException as e:
        raise click.ClickException(f"Serial error: {e}")


@repl.command("rm")
@click.argument("path")
@click.option("--force", "-f", is_flag=True, help="Don't ask for confirmation")
def repl_rm(path: str, force: bool):
    """Remove file from board.

    \b
    Examples:
      disco repl rm /flash/test.py
      disco repl rm /flash/test.py -f
    """
    dev = _ser.require_device()
    if not force:
        if not click.confirm(f"Delete {path}?"):
            click.echo("Aborted")
            return

    with _mpremote_transport(dev) as transport:
        try:
            transport.fs_rmfile(path)
            click.secho(f"Removed {path}", fg="green")
        except Exception as e:
            raise click.ClickException(f"Error removing {path}: {e}")
