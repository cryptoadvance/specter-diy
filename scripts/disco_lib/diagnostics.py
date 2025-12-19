"""Board diagnostics logic."""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import click

from .openocd import OpenOCD
from .serial import SerialDevice

# Memory regions (STM32F469)
FLASH_START = 0x08000000
FLASH_END = 0x08200000
FIRMWARE_START = 0x08020000
RAM_START = 0x20000000
RAM_END = 0x20060000  # 384KB SRAM

# Cortex-M4 System Control Block registers
CFSR = 0xE000ED28  # Configurable Fault Status Register
HFSR = 0xE000ED2C  # Hard Fault Status Register
BFAR = 0xE000ED38  # Bus Fault Address Register
CPACR = 0xE000ED88  # Coprocessor Access Control Register

# CFSR bit definitions
CFSR_NOCP = 1 << 19  # UsageFault: No coprocessor
CFSR_BFARVALID = 1 << 15  # BusFault: BFAR valid
CFSR_PRECISERR = 1 << 9  # BusFault: Precise data bus error

# HFSR bit definitions
HFSR_FORCED = 1 << 30  # Fault escalated from lower priority


class Level(Enum):
    ERROR = "error"
    WARN = "warn"
    OK = "ok"


@dataclass
class Diagnostic:
    code: str
    level: Level
    message: str
    details: str = ""


@dataclass
class DiagnosticReport:
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    # Connection state
    openocd_running: bool = False
    target_responding: bool = False
    usb_cdc_present: bool = False
    repl_responsive: bool = False
    # CPU state
    pc: int = 0
    sp: int = 0
    lr: int = 0
    was_halted: bool = False
    cpu_stuck: bool = False
    # Fault registers
    cfsr: int = 0
    hfsr: int = 0
    bfar: int = 0
    cpacr: int = 0
    # Vectors
    vector_sp: int = 0
    vector_reset: int = 0

    def add(self, code: str, level: Level, message: str, details: str = ""):
        self.diagnostics.append(Diagnostic(code, level, message, details))

    @property
    def errors(self) -> int:
        return sum(1 for d in self.diagnostics if d.level == Level.ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for d in self.diagnostics if d.level == Level.WARN)


def _parse_reg(output: str) -> int | None:
    """Parse register value from OpenOCD output like 'pc (/32): 0x080dc37c'."""
    match = re.search(r"0x([0-9a-fA-F]+)", output)
    return int(match.group(1), 16) if match else None


def _parse_mdw(output: str) -> list[int]:
    """Parse memory words from OpenOCD 'mdw' output.

    OpenOCD format: '0xADDRESS: VALUE1 VALUE2 ...'
    """
    words = []
    match = re.search(r"0x[0-9a-fA-F]+:\s*(.+)", output)
    if match:
        for val in match.group(1).split():
            try:
                words.append(int(val.strip(), 16))
            except ValueError:
                pass
    return words


def _in_range(addr: int, start: int, end: int) -> bool:
    return start <= addr < end


def check_openocd(ocd: OpenOCD, report: DiagnosticReport) -> bool:
    """Check if OpenOCD is running."""
    report.openocd_running = ocd.is_running()
    if not report.openocd_running:
        report.add("OPENOCD_NOT_RUNNING", Level.ERROR, "OpenOCD server not started")
        return False
    return True


def check_target(ocd: OpenOCD, report: DiagnosticReport) -> bool:
    """Check if target is responding."""
    try:
        result = ocd.send("reg pc")
        report.pc = _parse_reg(result)
        if report.pc is None:
            report.add("TARGET_NOT_RESPONDING", Level.ERROR,
                       "JTAG connected but MCU not responding")
            return False
        report.target_responding = True
        return True
    except Exception:
        report.add("TARGET_NOT_RESPONDING", Level.ERROR,
                   "JTAG connected but MCU not responding")
        return False


def capture_cpu_state(ocd: OpenOCD, report: DiagnosticReport) -> bool:
    """Capture CPU state. Returns True if was running (needs restore)."""
    try:
        result = ocd.send("reg pc")
        pc1 = _parse_reg(result)
        time.sleep(0.05)
        result = ocd.send("reg pc")
        pc2 = _parse_reg(result)
        report.was_halted = (pc1 == pc2)
    except Exception:
        report.was_halted = True

    ocd.send("halt")
    time.sleep(0.05)

    result = ocd.send("reg pc")
    report.pc = _parse_reg(result) or 0
    result = ocd.send("reg sp")
    report.sp = _parse_reg(result) or 0
    result = ocd.send("reg lr")
    report.lr = _parse_reg(result) or 0

    return not report.was_halted


def check_cpu_stuck(ocd: OpenOCD, report: DiagnosticReport):
    """Sample PC 3 times to detect if CPU is stuck."""
    samples = [report.pc]
    for _ in range(2):
        time.sleep(0.1)
        ocd.send("step")
        result = ocd.send("reg pc")
        pc = _parse_reg(result)
        if pc:
            samples.append(pc)

    ocd.send(f"reg pc {report.pc:#x}")

    if len(set(samples)) == 1:
        report.cpu_stuck = True
        report.add("CPU_STUCK", Level.ERROR,
                   "PC doesn't change (infinite loop/fault)",
                   f"PC={report.pc:#010x}")


def check_faults(ocd: OpenOCD, report: DiagnosticReport):
    """Read and decode fault status registers."""
    result = ocd.send(f"mdw {CFSR:#x}")
    words = _parse_mdw(result)
    report.cfsr = words[0] if words else 0

    result = ocd.send(f"mdw {HFSR:#x}")
    words = _parse_mdw(result)
    report.hfsr = words[0] if words else 0

    if report.cfsr & CFSR_BFARVALID:
        result = ocd.send(f"mdw {BFAR:#x}")
        words = _parse_mdw(result)
        report.bfar = words[0] if words else 0

    if report.cfsr != 0:
        if report.cfsr & CFSR_NOCP:
            report.add("USAGEFAULT_NOCP", Level.ERROR,
                       "FPU instruction with FPU disabled",
                       f"CFSR={report.cfsr:#010x}")
        if report.cfsr & CFSR_BFARVALID:
            if not _in_range(report.bfar, RAM_START, RAM_END) and \
               not _in_range(report.bfar, FLASH_START, FLASH_END):
                report.add("INVALID_MEMORY_ACCESS", Level.ERROR,
                           "Bus fault at invalid address",
                           f"BFAR={report.bfar:#010x}")

    if report.hfsr & HFSR_FORCED:
        report.add("HARDFAULT_FORCED", Level.ERROR,
                   "Lower fault escalated to HardFault",
                   f"HFSR={report.hfsr:#010x}")


def check_fpu(ocd: OpenOCD, report: DiagnosticReport):
    """Check FPU configuration."""
    result = ocd.send(f"mdw {CPACR:#x}")
    words = _parse_mdw(result)
    report.cpacr = words[0] if words else 0

    fpu_bits = (report.cpacr >> 20) & 0xF
    if fpu_bits != 0xF:
        report.add("FPU_DISABLED", Level.WARN,
                   "FPU not fully enabled",
                   f"CPACR={report.cpacr:#010x} (expected bits 20-23 set)")


def check_vectors(ocd: OpenOCD, report: DiagnosticReport):
    """Check vector table validity."""
    result = ocd.send(f"mdw {FLASH_START:#x} 2")
    words = _parse_mdw(result)

    if len(words) >= 2:
        report.vector_sp = words[0]
        report.vector_reset = words[1]

        if not _in_range(report.vector_sp, RAM_START, RAM_END):
            report.add("INVALID_INITIAL_SP", Level.ERROR,
                       "Vector table SP not in RAM",
                       f"SP={report.vector_sp:#010x}")

        reset_addr = report.vector_reset & ~1
        if not _in_range(reset_addr, FLASH_START, FLASH_END):
            report.add("INVALID_RESET_VECTOR", Level.ERROR,
                       "Reset handler not in Flash",
                       f"Reset={report.vector_reset:#010x}")


def check_usb(ser: SerialDevice, report: DiagnosticReport):
    """Check USB CDC and REPL."""
    devices = ser.list_devices()
    for path, blacklisted in devices:
        if blacklisted:
            continue
        match = re.search(r'usbmodem(\w+)', path)
        if match and len(match.group(1)) > 6:
            report.usb_cdc_present = True
            break

    if not report.usb_cdc_present:
        report.add("USB_OTG_MISSING", Level.WARN,
                   "No USB CDC device (check cable)")
        return

    dev = ser.auto_detect()
    if dev:
        try:
            response = ser.repl_test(dev, timeout=1.0)
            if response and (">>>" in response or "MicroPython" in response):
                report.repl_responsive = True
            else:
                report.add("REPL_UNRESPONSIVE", Level.WARN,
                           "CDC present but no REPL response")
        except Exception:
            report.add("REPL_UNRESPONSIVE", Level.WARN,
                       "CDC present but no REPL response")


def generate_markdown(report: DiagnosticReport) -> str:
    """Generate markdown report."""
    report.end_time = datetime.now()
    duration = (report.end_time - report.start_time).total_seconds()

    lines = [
        "# Board Diagnostic Report",
        f"**Time**: {report.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Duration**: {duration:.1f}s",
        "",
        "## Connection",
    ]

    if report.openocd_running:
        lines.append("- ✓ OpenOCD running")
    else:
        lines.append("- ✗ OpenOCD not running")

    if report.target_responding:
        lines.append(f"- ✓ Target responding (PC={report.pc:#010x})")
    elif report.openocd_running:
        lines.append("- ✗ Target not responding")

    if report.usb_cdc_present:
        if report.repl_responsive:
            lines.append("- ✓ USB CDC + REPL working")
        else:
            lines.append("- ⚠ USB CDC present, REPL unresponsive")
    else:
        lines.append("- ✗ USB OTG not detected")

    if report.target_responding:
        lines.extend(["", "## CPU State"])
        if report.cpu_stuck:
            lines.append(f"- ✗ CPU_STUCK at {report.pc:#010x} (no change in 3 samples)")
        else:
            lines.append(f"- ✓ CPU executing (PC={report.pc:#010x})")
        lines.append(f"- SP: {report.sp:#010x}")
        lines.append(f"- LR: {report.lr:#010x}")

    if report.cfsr or report.hfsr:
        lines.extend(["", "## Faults"])
        if report.cfsr:
            lines.append(f"- CFSR: {report.cfsr:#010x}")
            if report.cfsr & CFSR_NOCP:
                lines.append("  - USAGEFAULT_NOCP: No coprocessor (FPU disabled)")
            if report.cfsr & CFSR_BFARVALID:
                lines.append(f"  - BFAR: {report.bfar:#010x}")
        if report.hfsr:
            lines.append(f"- HFSR: {report.hfsr:#010x}")
            if report.hfsr & HFSR_FORCED:
                lines.append("  - HARDFAULT_FORCED: Escalated from lower fault")
    elif report.target_responding:
        lines.extend(["", "## Faults", "- ✓ No active faults"])

    if report.target_responding:
        lines.extend(["", "## Configuration"])
        fpu_bits = (report.cpacr >> 20) & 0xF
        if fpu_bits == 0xF:
            lines.append(f"- ✓ FPU enabled (CPACR={report.cpacr:#010x})")
        else:
            lines.append(f"- ✗ FPU_DISABLED: CPACR={report.cpacr:#010x}")

        if _in_range(report.vector_sp, RAM_START, RAM_END):
            lines.append(f"- ✓ Vector SP: {report.vector_sp:#010x} (valid RAM)")
        else:
            lines.append(f"- ✗ Vector SP: {report.vector_sp:#010x} (invalid)")

        reset_addr = report.vector_reset & ~1
        if _in_range(reset_addr, FLASH_START, FLASH_END):
            lines.append(f"- ✓ Vector Reset: {report.vector_reset:#010x} (valid Flash)")
        else:
            lines.append(f"- ✗ Vector Reset: {report.vector_reset:#010x} (invalid)")

    lines.extend(["", "## Summary"])
    lines.append(f"**{report.errors} errors, {report.warnings} warnings**")

    errors = [d for d in report.diagnostics if d.level == Level.ERROR]
    if errors:
        lines.append(f"Primary issue: {errors[0].code}")

    return "\n".join(lines)


def save_log(report: DiagnosticReport, content: str) -> Path:
    """Save report to log file."""
    log_dir = Path("/tmp/disco_log")
    log_dir.mkdir(exist_ok=True)

    filename = report.start_time.strftime("%Y-%m-%d_%H-%M-%S.md")
    log_path = log_dir / filename
    log_path.write_text(content)
    return log_path


def print_summary(report: DiagnosticReport, verbose: bool):
    """Print summary to console."""
    def status_icon(ok: bool, warn: bool = False) -> str:
        if ok:
            return click.style("✓", fg="green")
        elif warn:
            return click.style("⚠", fg="yellow")
        return click.style("✗", fg="red")

    click.secho("=== Board Diagnostic Report ===", fg="blue")
    click.echo()

    click.echo("Connection:")
    click.echo(f"  {status_icon(report.openocd_running)} OpenOCD")
    if report.openocd_running:
        click.echo(f"  {status_icon(report.target_responding)} Target")
    click.echo(f"  {status_icon(report.usb_cdc_present, not report.usb_cdc_present)} USB CDC")
    if report.usb_cdc_present:
        click.echo(f"  {status_icon(report.repl_responsive, not report.repl_responsive)} REPL")

    if report.target_responding:
        click.echo()
        click.echo("CPU:")
        if report.cpu_stuck:
            click.echo(f"  {status_icon(False)} STUCK at {report.pc:#010x}")
        else:
            click.echo(f"  {status_icon(True)} PC={report.pc:#010x}")
        if verbose:
            click.echo(f"     SP={report.sp:#010x} LR={report.lr:#010x}")

    if report.cfsr or report.hfsr:
        click.echo()
        click.echo("Faults:")
        if report.cfsr:
            click.echo(f"  CFSR={report.cfsr:#010x}")
        if report.hfsr:
            click.echo(f"  HFSR={report.hfsr:#010x}")

    if report.diagnostics:
        click.echo()
        click.echo("Issues:")
        for d in report.diagnostics:
            color = "red" if d.level == Level.ERROR else "yellow"
            click.secho(f"  [{d.level.value}] {d.code}: {d.message}", fg=color)
            if verbose and d.details:
                click.echo(f"         {d.details}")

    click.echo()
    if report.errors:
        click.secho(f"{report.errors} errors, {report.warnings} warnings", fg="red")
    elif report.warnings:
        click.secho(f"{report.warnings} warnings", fg="yellow")
    else:
        click.secho("All checks passed", fg="green")


def run_diagnostics(ocd: OpenOCD, ser: SerialDevice, verbose: bool, no_log: bool):
    """Run full diagnostic sequence."""
    report = DiagnosticReport()
    needs_resume = False

    if not check_openocd(ocd, report):
        check_usb(ser, report)
        print_summary(report, verbose)
        if not no_log:
            log_path = save_log(report, generate_markdown(report))
            click.echo(f"\nLog: {log_path}")
        return

    if not check_target(ocd, report):
        check_usb(ser, report)
        print_summary(report, verbose)
        if not no_log:
            log_path = save_log(report, generate_markdown(report))
            click.echo(f"\nLog: {log_path}")
        return

    needs_resume = capture_cpu_state(ocd, report)
    check_cpu_stuck(ocd, report)
    check_faults(ocd, report)
    check_fpu(ocd, report)
    check_vectors(ocd, report)

    if needs_resume and not report.cpu_stuck:
        ocd.send("resume")

    check_usb(ser, report)
    print_summary(report, verbose)

    if not no_log:
        log_path = save_log(report, generate_markdown(report))
        click.echo(f"\nLog: {log_path}")
