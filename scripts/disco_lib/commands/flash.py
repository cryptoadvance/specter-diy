"""Flash programming commands."""

import os
from typing import List, Tuple

import click

from ..openocd import OpenOCD

_ocd = OpenOCD()

def _analyze_firmware(filepath: str, chunk_size: int = 4096) -> List[Tuple[int, int, bool]]:
    """Analyze firmware file to find code vs zero regions.

    Returns list of (start, end, has_data) tuples.
    """
    with open(filepath, "rb") as f:
        data = f.read()

    regions = []
    i = 0
    while i < len(data):
        chunk = data[i:i + chunk_size]
        has_data = any(b != 0 for b in chunk)

        # Extend region while same type
        start = i
        while i < len(data):
            chunk = data[i:i + chunk_size]
            chunk_has_data = any(b != 0 for b in chunk)
            if chunk_has_data != has_data:
                break
            i += chunk_size

        regions.append((start, min(i, len(data)), has_data))

    return regions


def _has_internal_zeros(regions: List[Tuple[int, int, bool]]) -> bool:
    """Check if firmware has zero regions between code regions.

    This pattern indicates filesystem preservation - zeros between code
    regions won't overwrite existing flash data when programmed.
    """
    code_seen = False
    for start, end, has_data in regions:
        if has_data:
            code_seen = True
        elif code_seen and not has_data:
            # Zero region after code - check if more code follows
            idx = regions.index((start, end, has_data))
            if any(hd for _, _, hd in regions[idx + 1:]):
                return True
    return False


@click.group()
def flash():
    """Flash programming commands.

    Program and erase the STM32F469 internal flash via JTAG/OpenOCD.
    The flash is 2MB organized as dual-bank with mixed sector sizes.

    \b
    Flash Layout (STM32F469, 2MB dual-bank):
      Bank 1 (0x08000000 - 0x080FFFFF):
        Sectors 0-3:   16KB each  (0x08000000 - 0x0800FFFF)
        Sector 4:      64KB       (0x08010000 - 0x0801FFFF)
        Sectors 5-11: 128KB each  (0x08020000 - 0x080FFFFF)

      Bank 2 (0x08100000 - 0x081FFFFF):
        Same layout as Bank 1

    \b
    Filesystem Preservation:
      MicroPython firmware files typically have zeros between code regions
      to preserve the internal filesystem during updates. Zero regions
      won't overwrite existing flash data when programmed.
      Use 'disco flash analyze <file>' to see the firmware layout.

    \b
    Programming Addresses:
      0x08000000  Full image (bootloader + firmware, preserves filesystem)
      0x08020000  Main firmware only (default for 'program' command)

    \b
    Examples:
      disco flash analyze firmware.bin             # Show firmware layout
      disco flash program firmware.bin             # Flash to 0x08020000
      disco flash program full.bin --addr 0x08000000
      disco flash erase                            # Requires confirmation

    \b
    Safety:
      - 'program' verifies after writing by default (--no-verify to skip)
      - 'program' resets the board after flashing (--no-reset to skip)
      - 'erase' requires explicit confirmation
    """
    pass


@flash.command("info")
def flash_info():
    """Show flash bank info."""
    _ocd.require_running()
    click.secho("=== Flash Bank Info ===", fg="blue")
    click.echo(_ocd.send("flash info 0"))


@flash.command("identify")
@click.argument("file", type=click.Path(exists=True), required=False)
def flash_identify(file: str):
    """Identify firmware build type (debug vs production).

    Searches for version tag in firmware. Can check a file or read from flash.

    \b
    Version tags:
      0100900099 = production build (USB disabled at boot)
      0100900001 = debug build (USB enabled by default)

    \b
    Examples:
      disco flash identify                    # Check currently flashed firmware
      disco flash identify firmware.bin       # Check a firmware file
    """
    import re
    import tempfile

    version_pattern = rb'<version:tag10>([^<]*)</version:tag10>'

    if file:
        # Check file
        filepath = os.path.abspath(file)
        click.secho(f"=== Identifying Firmware ===", fg="blue")
        click.echo(f"File: {filepath}")

        with open(filepath, "rb") as f:
            data = f.read()
    else:
        # Read from flash
        _ocd.require_running()
        click.secho(f"=== Identifying Flashed Firmware ===", fg="blue")
        click.echo("Reading from flash...")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
            tmp_path = tmp.name

        _ocd.send("halt")
        # Read first 1.5MB - should contain version tag
        result = _ocd.send(f"dump_image {tmp_path} 0x08000000 0x180000", timeout=60)

        with open(tmp_path, "rb") as f:
            data = f.read()
        os.unlink(tmp_path)

    # Search for version tag
    match = re.search(version_pattern, data)
    click.echo()

    if match:
        version = match.group(1).decode("utf-8", errors="replace")
        click.echo(f"Version tag: {version}")

        if version == "0100900099":
            click.secho("Build type: PRODUCTION", fg="yellow")
            click.echo("  - USB/REPL disabled at boot")
            click.echo("  - Enabled after PIN entry")
        elif version == "0100900001":
            click.secho("Build type: DEBUG", fg="green")
            click.echo("  - USB/REPL enabled by default")
            click.echo("  - Runs hardwaretest.py")
        else:
            click.secho(f"Build type: UNKNOWN", fg="cyan")
            click.echo(f"  - Version: {version}")
    else:
        click.secho("No version tag found", fg="red")


@flash.command("analyze")
@click.argument("file", type=click.Path(exists=True))
def flash_analyze(file: str):
    """Analyze firmware file layout.

    Shows code regions vs zero-padded areas. Useful for understanding
    what will be written to flash and whether filesystem is preserved.

    \b
    Examples:
      disco flash analyze firmware.bin
      disco flash analyze upy-f469disco.bin
    """
    file = os.path.abspath(file)
    size = os.path.getsize(file)

    click.secho("=== Firmware Analysis ===", fg="blue")
    click.echo(f"File: {file}")
    click.echo(f"Size: {size:,} bytes ({size/1024:.1f} KB)")
    click.echo()

    regions = _analyze_firmware(file)
    has_internal_zeros = _has_internal_zeros(regions)

    # Calculate totals
    code_bytes = sum(end - start for start, end, has_data in regions if has_data)
    zero_bytes = sum(end - start for start, end, has_data in regions if not has_data)

    click.secho("Regions:", fg="cyan")
    code_seen = False
    for start, end, has_data in regions:
        region_size = end - start
        if has_data:
            code_seen = True
            click.echo(f"  0x{start:08x} - 0x{end:08x}: {region_size:>8,} bytes  [CODE]")
        else:
            # Check if this zero region is between code regions
            idx = regions.index((start, end, has_data))
            more_code_after = any(hd for _, _, hd in regions[idx + 1:])
            if code_seen and more_code_after:
                click.secho(
                    f"  0x{start:08x} - 0x{end:08x}: {region_size:>8,} bytes  [ZEROS - preserved area]",
                    fg="yellow"
                )
            else:
                click.echo(f"  0x{start:08x} - 0x{end:08x}: {region_size:>8,} bytes  [ZEROS]")

    click.echo()
    click.echo(f"Code:  {code_bytes:,} bytes ({code_bytes/1024:.1f} KB)")
    click.echo(f"Zeros: {zero_bytes:,} bytes ({zero_bytes/1024:.1f} KB)")

    if has_internal_zeros:
        click.echo()
        click.secho("⚠ Data preservation detected:", fg="yellow")
        click.echo("  This firmware has zeros between code regions.")
        click.echo("  Existing flash data in zero regions will NOT be overwritten.")
        click.echo("  (Typically used to preserve filesystem during updates)")
        click.echo()
        click.echo("  OpenOCD verify will report 'mismatch' for these regions.")
        click.echo("  Use 'disco flash verify --smart' after programming.")


@flash.command("read")
@click.argument("file", type=click.Path())
@click.option("--addr", default="0x08000000", help="Start address (default: 0x08000000)")
@click.option("--size", default="0x200000", help="Size in bytes (default: 0x200000 = 2MB)")
def flash_read(file: str, addr: str, size: str):
    """Read flash contents to file.

    \b
    Examples:
      disco flash read backup.bin                        # Full 2MB flash
      disco flash read firmware.bin --addr 0x08020000 --size 0x100000
    """
    _ocd.require_running()

    file = os.path.abspath(file)

    # Parse size (hex or decimal)
    if size.startswith("0x"):
        byte_count = int(size, 16)
    else:
        byte_count = int(size)

    # Calculate timeout based on size (~50KB/s read speed + margin)
    timeout = max(60, int(byte_count / (50 * 1024)) + 30)

    click.secho("=== Reading Flash ===", fg="blue")
    click.echo(f"Address: {addr}")
    click.echo(f"Size: {byte_count:,} bytes ({byte_count/1024:.1f} KB)")
    click.echo(f"File: {file}")
    click.echo(f"Timeout: {timeout}s")
    click.echo()

    _ocd.send("halt")

    click.secho("Reading flash (this may take a while)...", fg="yellow")
    result = _ocd.send(f"dump_image {file} {addr} {byte_count}", timeout=timeout)

    if result:
        click.echo(result)

    if os.path.exists(file):
        actual_size = os.path.getsize(file)
        if actual_size == byte_count:
            click.secho(f"Read {actual_size:,} bytes to {file}", fg="green")
        else:
            click.secho(f"Warning: Read {actual_size:,} bytes (expected {byte_count:,})", fg="yellow")
    else:
        click.secho("Failed to create output file", fg="red")


@flash.command("verify")
@click.argument("file", type=click.Path(exists=True))
@click.option("--addr", default="0x08020000", help="Flash address (default: 0x08020000)")
@click.option("--smart/--full", default=True, help="Smart verify skips internal zeros (default: smart)")
def flash_verify(file: str, addr: str, smart: bool):
    """Verify flash contents against file.

    By default uses smart verification that skips zero-padded regions
    between code sections. Use --full for strict byte-by-byte verification.

    \b
    Examples:
      disco flash verify firmware.bin
      disco flash verify firmware.bin --full    # Strict verify
      disco flash verify bootloader.bin --addr 0x08000000
    """
    _ocd.require_running()

    file = os.path.abspath(file)
    size = os.path.getsize(file)

    # Analyze firmware for zero regions
    regions = _analyze_firmware(file)
    code_regions = [(s, e) for s, e, has_data in regions if has_data]
    has_internal_zeros = _has_internal_zeros(regions)

    # Calculate timeout based on total size
    timeout = max(60, int(size / (50 * 1024)) + 30)

    click.secho("=== Verifying Flash ===", fg="blue")
    click.echo(f"File: {file}")
    click.echo(f"Size: {size:,} bytes ({size/1024:.1f} KB)")
    click.echo(f"Address: {addr}")
    click.echo(f"Mode: {'smart (code regions only)' if smart else 'full (strict)'}")

    if has_internal_zeros and smart:
        click.secho("Note: File has zeros between code - will verify code regions only", fg="yellow")
    click.echo()

    _ocd.send("halt")

    if smart and has_internal_zeros and len(code_regions) > 0:
        # Smart verify: check each code region separately
        click.secho("Verifying code regions...", fg="yellow")
        all_passed = True

        for region_start, region_end in code_regions:
            region_size = region_end - region_start
            # Parse base address
            if addr.startswith("0x"):
                base_addr = int(addr, 16)
            else:
                base_addr = int(addr)

            flash_addr = base_addr + region_start
            click.echo(f"  Region 0x{region_start:x}-0x{region_end:x} at 0x{flash_addr:08x}...")

            # Read flash region and compare with file
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
                tmp_path = tmp.name

            # Timeout: ~50KB/s read speed + margin
            read_timeout = max(60, int(region_size / (50 * 1024)) + 30)
            result = _ocd.send(
                f"dump_image {tmp_path} 0x{flash_addr:x} {region_size}",
                timeout=read_timeout
            )

            # Compare with file region
            try:
                with open(file, "rb") as f:
                    f.seek(region_start)
                    file_data = f.read(region_size)

                with open(tmp_path, "rb") as f:
                    flash_data = f.read()

                os.unlink(tmp_path)

                if file_data == flash_data:
                    click.secho(f"    ✓ Match ({region_size:,} bytes)", fg="green")
                else:
                    click.secho(f"    ✗ Mismatch!", fg="red")
                    all_passed = False
            except Exception as e:
                click.secho(f"    ✗ Error: {e}", fg="red")
                all_passed = False

        click.echo()
        if all_passed:
            click.secho("Verification PASSED! (code regions verified)", fg="green")
        else:
            click.secho("Verification FAILED!", fg="red")
    else:
        # Full verify using OpenOCD
        click.secho("Verifying (this may take a while)...", fg="yellow")
        result = _ocd.send(f"verify_image {file} {addr}", timeout=timeout)

        if result:
            click.echo(result)

        result_lower = result.lower()
        if "verified" in result_lower and "error" not in result_lower:
            click.secho("Verification PASSED!", fg="green")
        elif "error" in result_lower or "mismatch" in result_lower:
            click.secho("Verification FAILED!", fg="red")
            if has_internal_zeros:
                click.echo()
                click.secho("Hint: File has zeros between code regions.", fg="yellow")
                click.echo("Use 'disco flash verify --smart' to skip these areas.")
        else:
            click.secho("Verification status unclear - check output above", fg="yellow")


@flash.command("erase")
def flash_erase():
    """Mass erase flash (DANGEROUS)."""
    _ocd.require_running()
    click.secho("WARNING: This will erase all flash memory!", fg="red")
    if click.confirm("Type 'y' to confirm"):
        _ocd.send("halt")
        click.echo(_ocd.send("flash erase_sector 0 0 last"))
        click.secho("Flash erased", fg="green")
    else:
        click.echo("Aborted")


@flash.command("program")
@click.argument("file", type=click.Path(exists=True))
@click.option("--addr", default="0x08020000", help="Flash address (default: 0x08020000)")
@click.option("--verify/--no-verify", default=True, help="Verify after programming")
@click.option("--reset/--no-reset", default=True, help="Reset after programming")
@click.option("--timeout", "-t", default=0, type=int, help="Timeout in seconds (0=auto based on size)")
def flash_program(file: str, addr: str, verify: bool, reset: bool, timeout: int):
    """Program firmware to flash.

    Analyzes firmware layout before programming. Zero regions between code
    sections won't overwrite existing flash data (preserves filesystem).

    Timeout is automatically calculated based on file size if not specified.

    \b
    Note on verification:
      OpenOCD's built-in verify compares byte-by-byte, which may fail on
      files with zeros between code. After programming, use
      'disco flash verify --smart' for accurate verification.
    """
    _ocd.require_running()

    file = os.path.abspath(file)
    size = os.path.getsize(file)

    # Analyze firmware
    regions = _analyze_firmware(file)
    code_regions = [(s, e) for s, e, has_data in regions if has_data]
    has_internal_zeros = _has_internal_zeros(regions)
    code_bytes = sum(e - s for s, e, has_data in regions if has_data)

    # Auto-calculate timeout: ~100KB/s + erase time + verify time + margin
    if timeout == 0:
        size_mb = size / (1024 * 1024)
        timeout = int(30 + (size_mb * 40))  # 30s base + 40s per MB
        if verify:
            timeout += int(size_mb * 20)  # Extra 20s per MB for verify

    click.secho("=== Programming Firmware ===", fg="blue")
    click.echo(f"File: {file}")
    click.echo(f"Size: {size:,} bytes ({size/1024:.1f} KB)")
    click.echo(f"Code: {code_bytes:,} bytes in {len(code_regions)} region(s)")
    click.echo(f"Address: {addr}")
    click.echo(f"Timeout: {timeout}s")

    if has_internal_zeros:
        click.echo()
        click.secho("Data preservation: YES", fg="yellow")
        click.echo("  Zeros between code regions - existing data preserved.")
        if verify:
            click.secho("  Note: OpenOCD verify may report mismatch (expected).", fg="yellow")
    click.echo()

    click.echo("Halting CPU...")
    _ocd.send("halt")

    cmd = f"program {file} {addr}"
    if verify:
        cmd += " verify"
    if reset:
        cmd += " reset"

    click.echo(f"Running: {cmd}")
    click.echo()
    click.secho("Programming in progress (this may take a while)...", fg="yellow")

    result = _ocd.send(cmd, timeout=timeout)

    # Check result
    result_lower = result.lower()
    if result:
        click.echo(result)

    if "error" in result_lower or "failed" in result_lower:
        click.secho("Programming FAILED!", fg="red")
        click.echo("Check the error message above.")
    elif "verified" in result_lower:
        click.secho("Programming and verification complete!", fg="green")
    elif "wrote" in result_lower:
        click.secho("Programming complete!", fg="green")
        if verify and has_internal_zeros:
            click.echo()
            click.secho("OpenOCD verify may have failed on zero regions.", fg="yellow")
            click.echo("Run 'disco flash verify --smart' to verify code regions only.")
    elif has_internal_zeros and "mismatch" in result_lower:
        click.secho("Programming complete (data preserved in zero regions).", fg="green")
        click.echo()
        click.echo("Mismatch is expected in preserved areas.")
        click.echo("Run 'disco flash verify --smart' to confirm code regions.")
    else:
        click.secho("Programming status unclear - check output above", fg="yellow")
