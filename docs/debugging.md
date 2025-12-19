# Debugging Guide for Specter-DIY

This guide covers setting up and using JTAG/SWD debugging for the Specter-DIY firmware on STM32F469 Discovery board.

## Table of Contents

- [Overview](#overview)
- [Quick Start: disco tool](#quick-start-disco-tool)
- [Automated Diagnostics (disco doctor)](#automated-diagnostics-disco-doctor)
- [Hardware Setup](#hardware-setup)
- [Software Setup](#software-setup)
- [Using OpenOCD](#using-openocd)
- [Using GDB](#using-gdb)
- [Serial Console Access](#serial-console-access)
- [LED Diagnostics](#led-diagnostics)
- [Memory Map Reference](#memory-map-reference)
- [Quick Reference](#quick-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

Specter-DIY uses the integrated **ST-Link/V2-1 debugger** on the STM32F469 Discovery board for JTAG/SWD debugging. This provides:

- **Hardware breakpoints**: 6 breakpoints available
- **Hardware watchpoints**: 4 watchpoints available
- **Memory inspection**: Read/write flash, RAM, and peripheral registers
- **Real-time debugging**: Halt, step, and resume CPU execution

**Tools used:**
- **OpenOCD**: Open On-Chip Debugger for embedded systems
- **GDB**: GNU Debugger with ARM support
- **disco**: Python CLI wrapper for common debugging tasks

---

## Quick Start: disco tool

The `disco` tool provides a convenient CLI for common board operations. Install dependencies and use:

```bash
# Setup (one-time)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Check board connection
scripts/disco cables

# Start OpenOCD and run diagnostics
scripts/disco ocd connect
scripts/disco check

# REPL interaction
scripts/disco repl info              # Board info
scripts/disco repl exec "1 + 1"      # Execute Python
scripts/disco repl hello "Hi!"       # Display on screen
scripts/disco repl modules           # List modules

# File operations
scripts/disco repl ls                # List /flash
scripts/disco repl cat /flash/main.py
scripts/disco repl cp local.py :/flash/
scripts/disco repl cp :/flash/file.py ./
scripts/disco repl rm /flash/test.py

# CPU control
scripts/disco cpu halt
scripts/disco cpu resume
scripts/disco cpu reset
scripts/disco cpu pc                 # Show program counter

# Memory inspection
scripts/disco mem vectors            # Show vector table
scripts/disco mem read 0x08000000 8  # Read memory
```

Run `scripts/disco --help` for full command list.

> **Note**: Halting the CPU disconnects USB CDC (REPL). Use `disco cpu resume` to restore.

---

## Automated Diagnostics (disco doctor)

The `disco doctor` command performs non-invasive board diagnostics with markdown logging.

### Usage

```bash
scripts/disco doctor           # Run diagnostics, save log
scripts/disco doctor --verbose # Show all check details
scripts/disco doctor --no-log  # Skip log file
```

Logs are saved to: `/tmp/disco_log/YYYY-MM-DD_HH-MM-SS.md`

### Diagnostic Codes

| Code | Level | Meaning |
|------|-------|---------|
| OPENOCD_NOT_RUNNING | error | OpenOCD server not started |
| TARGET_NOT_RESPONDING | error | JTAG connected but MCU not responding |
| CPU_STUCK | error | PC doesn't change (infinite loop/fault) |
| USAGEFAULT_NOCP | error | FPU instruction with FPU disabled |
| HARDFAULT_FORCED | error | Lower fault escalated to HardFault |
| INVALID_MEMORY_ACCESS | error | BFAR points outside valid memory |
| FPU_DISABLED | warn | CPACR doesn't enable FPU |
| INVALID_INITIAL_SP | error | Vector table SP not in RAM |
| INVALID_RESET_VECTOR | error | Reset handler not in Flash |
| USB_OTG_MISSING | warn | No USB CDC device (check cable) |
| REPL_UNRESPONSIVE | warn | CDC present but no REPL response |

### Fault Registers (Cortex-M4 SCB)

| Register | Address | Purpose |
|----------|---------|---------|
| CFSR | 0xE000ED28 | Configurable Fault Status |
| HFSR | 0xE000ED2C | Hard Fault Status |
| BFAR | 0xE000ED38 | Bus Fault Address |
| CPACR | 0xE000ED88 | Coprocessor Access Control |

### CFSR Bit Fields

**UsageFault (bits 16-25):**
- Bit 19 (NOCP): FPU instruction without FPU enabled

**BusFault (bits 8-15):**
- Bit 9 (PRECISERR): Precise data bus error
- Bit 15 (BFARVALID): BFAR contains fault address

### Memory Validation

| Region | Start | End |
|--------|-------|-----|
| Flash | 0x08000000 | 0x08200000 |
| Firmware | 0x08020000 | - |
| RAM | 0x20000000 | 0x20060000 |

---

## Hardware Setup

### Required Hardware

- **STM32F469 Discovery board** (32F469IDISCOVERY)
- **2x USB cables**:
  - **Mini-USB** for ST-Link debugger (CN1)
  - **Micro-USB** for target board power (CN13)

### Connection Steps

1. **Connect ST-Link debugger:**
   - Plug **Mini-USB cable** into **CN1** port (top of board, labeled "ST-LINK")
   - Connect other end to your PC

2. **Power the target board:**
   - Plug **Micro-USB cable** into **CN13** port (bottom of board, labeled "USB OTG FS")
   - Connect other end to your PC or USB power supply

3. **Verify connection:**
   ```bash
   lsusb | grep STM
   ```
   Expected output:
   ```
   Bus 003 Device 020: ID 0483:374b STMicroelectronics ST-LINK/V2.1
   ```

4. **Verify board power:**
   - **LD2 (PWR)** LED should be lit (red/orange)
   - Target voltage should be ~3.3V

---

## Software Setup

### Nix Flake Environment

Specter-DIY uses **Nix flakes** for reproducible development environments.

**1. Enter development environment:**

```bash
nix develop
```

This automatically provides:
- `gcc-arm-embedded` - ARM cross-compiler toolchain
- `openocd` - On-chip debugger (v0.12.0)
- `gdb` - GNU Debugger (v16.3)
- `python3` - Python for build scripts
- `stlink` - ST-Link utilities (Linux only)
- `SDL2` - Graphics library for simulator

**2. Verify tools are available:**

```bash
openocd --version
# Open On-Chip Debugger 0.12.0

gdb --version
# GNU gdb (GDB) 16.3

arm-none-eabi-gcc --version
# arm-none-eabi-gcc (GCC) 14.2.0
```

### Flake Configuration

The `flake.nix` includes:

```nix
{
  description = "Specter DIY development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          nativeBuildInputs = [
            pkgs.buildPackages.gcc-arm-embedded
            pkgs.buildPackages.python3
            pkgs.openocd
            pkgs.gdb
            pkgs.SDL2
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.stlink
          ];
          hardeningDisable = ["all"];
        };
      });
}
```

---

## Using OpenOCD

### Start OpenOCD

**In one terminal:**

```bash
nix develop
openocd -f board/stm32f469discovery.cfg
```

**Expected output:**

```
Open On-Chip Debugger 0.12.0
...
Info : Listening on port 6666 for tcl connections
Info : Listening on port 4444 for telnet connections
Info : clock speed 2000 kHz
Info : STLINK V2J40M27 (API v2) VID:PID 0483:374B
Info : Target voltage: 3.223082
Info : [stm32f4x.cpu] Cortex-M4 r0p1 processor detected
Info : [stm32f4x.cpu] target has 6 breakpoints, 4 watchpoints
Info : starting gdb server for stm32f4x.cpu on 3333
Info : Listening on port 3333 for gdb connections
```

**OpenOCD ports:**
- **3333**: GDB server (remote debugging protocol)
- **4444**: Telnet (command interface)
- **6666**: TCL (scripting interface)

### OpenOCD Commands (via telnet)

**Connect to OpenOCD:**

```bash
telnet localhost 4444
```

**Useful commands:**

```tcl
> reset halt          # Reset and halt the CPU
> resume              # Resume execution
> halt                # Halt the CPU
> reg                 # Display all registers
> mdw 0x08000000 16   # Read 16 words from flash
> mdw 0x20000000 16   # Read 16 words from RAM
> flash info 0        # Show flash bank info
> exit                # Disconnect
```

---

## Using GDB

### Start GDB Session

**In a second terminal** (while OpenOCD is running):

```bash
nix develop
gdb
```

**Connect to target:**

```gdb
(gdb) target extended-remote :3333
(gdb) monitor reset halt
(gdb) load               # Load program (if ELF file loaded)
(gdb) continue           # Start execution
```

### Essential GDB Commands

**Connection:**
```gdb
target extended-remote :3333     # Connect to OpenOCD
monitor reset halt               # Reset and halt via OpenOCD
monitor reset init               # Reset and init peripherals
detach                           # Disconnect from target
quit                             # Exit GDB
```

**Execution Control:**
```gdb
continue (or c)                  # Continue execution
next (or n)                      # Step over (source level)
step (or s)                      # Step into (source level)
nexti (or ni)                    # Step over (instruction level)
stepi (or si)                    # Step into (instruction level)
finish                           # Run until current function returns
until <location>                 # Run until location
```

**Breakpoints:**
```gdb
break <location>                 # Set breakpoint (e.g., break main)
break *0x08001234                # Set breakpoint at address
info breakpoints                 # List breakpoints
delete <num>                     # Delete breakpoint
disable <num>                    # Disable breakpoint
enable <num>                     # Enable breakpoint
```

**Memory Inspection:**
```gdb
x/16xw 0x08000000                # Examine 16 words (hex) from flash
x/16xb 0x20000000                # Examine 16 bytes (hex) from RAM
x/s 0x08001000                   # Examine string at address
print variable                   # Print variable value
set {int}0x20000000 = 0x1234     # Write to memory
```

**Registers:**
```gdb
info registers                   # Show all registers
info registers <name>            # Show specific register (e.g., info registers pc)
set $pc = 0x08000000            # Set register value
```

**Symbol Information:**
```gdb
info functions                   # List all functions
info variables                   # List all variables
disassemble <function>           # Disassemble function
list                             # Show source code
backtrace (or bt)                # Show call stack
```

### Load and Debug Firmware

**1. Load firmware ELF file:**

```gdb
(gdb) file bin/firmware.elf
(gdb) target extended-remote :3333
(gdb) monitor reset halt
(gdb) load
(gdb) monitor reset init
(gdb) break main
(gdb) continue
```

**2. Debug from specific point:**

```gdb
(gdb) break *0x08050e54
Breakpoint 1 at 0x8050e54
(gdb) continue
```

---

## Serial Console Access

The STM32F469 Discovery board provides a **USB Virtual COM Port (VCP)** for serial console access via the integrated ST-Link/V2-1 debugger. This allows you to:

- Access the **MicroPython REPL** for interactive debugging
- View **boot messages** and firmware startup logs
- Monitor **debug output** in real-time
- Send **commands** to the running firmware

### Hardware Connection

**The serial console uses the same Mini-USB connection as debugging:**

- **Port:** CN1 (top of board, labeled "ST-LINK")
- **Cable:** Mini-USB (same cable used for JTAG/SWD debugging)
- **Device:** Appears as `/dev/ttyACM1` on Linux (or `/dev/ttyACM0` depending on system)

**No additional cables required** - the ST-Link provides three functions over one USB connection:
1. JTAG/SWD debugging
2. Mass storage (drag-and-drop flashing)
3. Virtual COM Port (serial console)

### Identify Serial Device

**On Linux:**

```bash
# List all USB devices from STMicroelectronics
lsusb | grep STM
# Output: Bus 003 Device 020: ID 0483:374b STMicroelectronics ST-LINK/V2.1

# Find the serial device
ls -l /dev/ttyACM*
# Look for device with "STMicroelectronics" in udev info

# Verify which device is the ST-Link VCP
udevadm info /dev/ttyACM1 | grep ID_MODEL
# Output: E: ID_MODEL=STM32_STLink
```

**On macOS:**

```bash
ls -l /dev/cu.usbmodem*
# Example: /dev/cu.usbmodem141301
```

**On Windows:**

- Open **Device Manager** → **Ports (COM & LPT)**
- Look for **STMicroelectronics STLink Virtual COM Port**
- Note the COM port number (e.g., COM3)

### Serial Parameters

**Standard configuration for MicroPython:**

- **Baud rate:** 115200
- **Data bits:** 8
- **Parity:** None
- **Stop bits:** 1
- **Flow control:** None

**Configuration: 8N1 @ 115200**

### Using Serial Terminal Tools

#### Option 1: screen (simplest)

```bash
# Connect to serial console
screen /dev/ttyACM1 115200

# Exit: Ctrl-A, then K (kill), then Y (confirm)
```

#### Option 2: minicom (feature-rich)

```bash
# First-time setup (run once)
minicom -s
# Navigate to "Serial port setup"
# Set: /dev/ttyACM1, 115200 8N1, no flow control
# Save as default

# Connect
minicom -D /dev/ttyACM1 -b 115200

# Exit: Ctrl-A, then X (exit)
```

#### Option 3: picocom (lightweight)

```bash
# Connect
picocom -b 115200 /dev/ttyACM1

# Exit: Ctrl-A, then Ctrl-X
```

### Expected Output

**If firmware boots successfully:**

```
MicroPython v1.25.0 on 2025-12-05; STM32F469DISC with STM32F469
Type "help()" for more information.
>>>
```

**If bootloader is active:**

```
Specter Bootloader v1.0
Checking firmware signature...
Firmware valid. Booting...
```

**If firmware fails to boot:**

- May see partial boot messages
- May see exception traceback
- May see nothing (indicates early boot failure)

### Interactive REPL

**Once connected, you can interact with MicroPython:**

```python
>>> print("Hello from Specter")
Hello from Specter

>>> import sys
>>> sys.version
'3.4.0; MicroPython v1.25.0'

>>> import machine
>>> machine.freq()
180000000

>>> help()
# Shows available modules and commands
```

### Testing Console During Reset

**Verify console stability:**

1. Connect serial terminal
2. Press **RESET button** on Discovery board
3. Observe boot messages
4. Verify console doesn't disconnect

**Expected behavior:**

- Console remains connected (no disconnect)
- Boot messages appear immediately after reset
- REPL prompt appears after successful boot

### Permissions (Linux)

**Add user to dialout group for serial access:**

```bash
# Check current groups
groups

# If not in dialout group, add yourself
sudo usermod -a -G dialout $USER

# Log out and log back in for changes to take effect
```

### Common Issues

**Problem: Permission denied when opening /dev/ttyACM1**

**Solution:**

```bash
# Check device permissions
ls -l /dev/ttyACM1

# Add user to dialout group (see above)
# Or temporarily change permissions (not recommended)
sudo chmod 666 /dev/ttyACM1
```

---

**Problem: No output in serial console**

**Possible causes:**

1. Wrong device selected (try `/dev/ttyACM0` instead)
2. Firmware not configured for serial output
3. Baud rate mismatch (ensure 115200)
4. Firmware hasn't booted yet

**Solution:**

```bash
# Verify device
udevadm info /dev/ttyACM1 | grep ID_MODEL

# Try different baud rates (uncommon)
screen /dev/ttyACM1 9600   # Try 9600
screen /dev/ttyACM1 115200 # Default
```

---

**Problem: Garbled output or random characters**

**Cause:** Baud rate mismatch

**Solution:**

- Ensure terminal is set to **115200 baud**
- Verify firmware is configured for 115200 (standard for MicroPython)

---

**Problem: Console disconnects during reset**

**Cause:** Some terminal programs reconnect automatically, others don't

**Solution:**

- Use `screen` or `picocom` (handle reconnect well)
- Or manually reconnect after reset

---

## LED Diagnostics

The STM32F469 Discovery board has **4 user LEDs** that MicroPython uses to indicate boot status and errors.

### LED Hardware

| LED | Color | GPIO Pin | Purpose |
|-----|-------|----------|---------|
| LED1 | Green | PG6 | Dirty flash cache indicator |
| LED2 | Orange | PD4 | Boot progress |
| LED3 | Red | PD5 | Error indicator |
| LED4 | Blue | PK3 | SD card activity |

**Note:** LEDs are active-low (GPIO low = LED on).

### Boot Sequence Patterns

| Stage | LED Pattern | Meaning |
|-------|-------------|---------|
| MicroPython init | Orange ON | Firmware entry, init starting |
| boot.py running | Orange ON | Executing boot.py |
| Boot complete | All OFF | Ready for REPL |

### Error Patterns

| Pattern | Meaning | Source |
|---------|---------|--------|
| Red/Green flash 4x | boot.py error | boardctrl.c:207 |
| Red/Green flash 3x | main.py error | boardctrl.c:245 |
| All LEDs ON + toggle | Fatal error (MemManage, BusFault, etc.) | boardctrl.c:38-56 |

### Interpreting Boot Failures

**Orange LED stays ON indefinitely:**
- Firmware stuck during initialization
- Use JTAG to halt and check PC register

**No LEDs at all after reset:**
- Very early boot failure (before MicroPython init)
- Possible causes: corrupt vector table, bad Reset_Handler, flash issue
- Use JTAG to read 0x08000000 and verify vector table

**All LEDs toggle continuously:**
- Hard fault or exception occurred
- Check serial console for "FATAL ERROR:" message
- Use JTAG to inspect fault registers

**Red/Green alternating flash:**
- Python script error in boot.py or main.py
- Check serial console for Python traceback
- Flash count indicates which file failed (4x = boot.py, 3x = main.py)

### Quick Diagnostic Steps

1. **Reset board and observe LEDs**
   - Orange ON briefly then OFF = normal boot
   - Orange stays ON = stuck in init
   - All toggle = fatal error
   - Nothing = very early failure

2. **Connect serial console** to see Python errors

3. **Use JTAG** for low-level debugging if LEDs show nothing

---

## Memory Map Reference

### STM32F469 Memory Layout

| Region | Start Address | End Address | Size | Description |
|--------|---------------|-------------|------|-------------|
| **Flash** | `0x08000000` | `0x081FFFFF` | 2 MB | Program memory |
| Bootloader | `0x08000000` | `0x0801FFFF` | 128 KB | Secure bootloader (if enabled) |
| Firmware | `0x08020000` | `0x081FFFFF` | ~1920 KB | Main firmware |
| **SRAM** | `0x20000000` | `0x2005FFFF` | 384 KB | Internal RAM |
| **SDRAM** | `0xC0000000` | `0xC0FFFFFF` | 16 MB | External SDRAM |
| **QSPI Flash** | `0x90000000` | `0x90FFFFFF` | 16 MB | External flash (memory-mapped) |
| **Peripherals** | `0x40000000` | `0x5FFFFFFF` | 512 MB | Peripheral registers |

### Vector Table (0x08000000)

| Offset | Description |
|--------|-------------|
| `0x0000` | Initial Stack Pointer (MSP) |
| `0x0004` | Reset Handler address |
| `0x0008` | NMI Handler |
| `0x000C` | HardFault Handler |
| `0x0010` | MemManage Handler |
| ... | (more exception vectors) |

**Example vector table read:**

```gdb
(gdb) x/16xw 0x08000000
0x8000000: 0x2004fff8  0x08050e55  0x08046dfb  0x08046de9
0x8000010: 0x08046dfd  0x08046e0d  0x08046e1d  0x00000000
```

- `0x2004fff8` = Initial SP (top of RAM)
- `0x08050e55` = Reset vector (entry point, bit 0 set for Thumb mode)

---

## Quick Reference

### Quick Start Debugging Session

**Terminal 1:**
```bash
nix develop
openocd -f board/stm32f469discovery.cfg
```

**Terminal 2:**
```bash
nix develop
gdb bin/firmware.elf
(gdb) target extended-remote :3333
(gdb) monitor reset halt
(gdb) load
(gdb) break main
(gdb) continue
```

### Common Debugging Workflows

**1. Check if firmware is running:**

```gdb
(gdb) target extended-remote :3333
(gdb) monitor halt
(gdb) info registers pc
pc             0x803de1e
(gdb) x/4i $pc
=> 0x803de1e:   ldr     r3, [pc, #24]
   0x803de20:   adds    r0, r0, r3
```

**2. Inspect vector table:**

```gdb
(gdb) x/16xw 0x08000000
(gdb) x/16xw 0x08020000  # Firmware vector table
```

**3. Read flash memory region:**

```gdb
(gdb) dump memory flash.bin 0x08000000 0x08200000
```

**4. Reset and run firmware:**

```gdb
(gdb) monitor reset init
(gdb) continue
```

---

## Troubleshooting

### OpenOCD Connection Issues

**Problem: "Error: couldn't bind to socket on port 4444: Address already in use"**

**Solution:**
```bash
# Check if OpenOCD is already running
ps aux | grep openocd

# Kill existing OpenOCD process
pkill openocd

# Or find and kill by port
lsof -i :4444
kill <PID>
```

---

**Problem: "Error: target voltage may be too low for reliable debugging"**

**Solution:**
- Ensure **Micro-USB cable is connected to CN13** (target power)
- Check **LD2 (PWR) LED** is lit
- Verify target voltage in OpenOCD output: `Target voltage: 3.2V` (should be ~3.3V)

---

**Problem: "Error: init mode failed (unable to connect to the target)"**

**Possible causes:**
1. Board not powered (see above)
2. Debug interface locked (read protection enabled)
3. Faulty USB cable or connection
4. ST-Link firmware outdated

**Solution:**
```bash
# Check ST-Link connection
lsusb | grep STM

# Try updating ST-Link firmware (Windows/Mac: ST-Link Utility)
# Linux: stlink-tools
st-info --probe
```

---

### GDB Connection Issues

**Problem: "Connection refused" when connecting to :3333**

**Solution:**
- Ensure OpenOCD is running first
- Check OpenOCD output for "Listening on port 3333"
- Verify firewall not blocking port 3333

---

**Problem: "Remote 'g' packet reply is too long"**

**Solution:**
```gdb
(gdb) disconnect
(gdb) set architecture arm
(gdb) target extended-remote :3333
```

---

**Problem: Cannot load firmware with `load` command**

**Solution:**
```gdb
# Ensure you loaded an ELF file (not .bin)
(gdb) file bin/firmware.elf

# If using .bin, flash via OpenOCD instead:
# (in OpenOCD telnet)
> program bin/firmware.bin 0x08020000 verify reset
```

---

### Common Debugging Scenarios

**Scenario: Firmware crashes immediately after boot**

**Debug steps:**
1. Check vector table is valid
2. Check stack pointer is in RAM range
3. Set breakpoint at Reset_Handler
4. Single-step through startup code

```gdb
(gdb) x/2xw 0x08000000
0x8000000: 0x2004fff8  0x08050e55

(gdb) break *0x08050e54  # Reset handler (clear Thumb bit)
(gdb) monitor reset init
(gdb) continue
(gdb) stepi
(gdb) info registers
```

---

**Scenario: Need to inspect peripheral registers**

**Example: Read GPIOA registers**

```gdb
# GPIOA base address: 0x40020000
(gdb) x/8xw 0x40020000
0x40020000: 0x00000000  0x00000000  0x00000000  0x00000000
0x40020010: 0x00000000  0x00000000  0x00000000  0x00000000
```

---

## Additional Resources

### Documentation

- [STM32F469 Reference Manual (RM0386)](https://www.st.com/resource/en/reference_manual/rm0386-stm32f469xx-and-stm32f479xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
- [STM32F469 Discovery User Manual (UM1932)](https://www.st.com/resource/en/user_manual/um1932-discovery-kit-with-stm32f469ni-mcu-stmicroelectronics.pdf)
- [OpenOCD User's Guide](http://openocd.org/doc/html/index.html)
- [GDB User Manual](https://sourceware.org/gdb/current/onlinedocs/gdb/)
- [ARM Cortex-M4 Technical Reference Manual](https://developer.arm.com/documentation/100166/0001)

### Related Specter-DIY Documentation

- [Build Instructions](build.md)
- [Development Guide](development.md)
- [Tech Stack](architecture/tech-stack.md)
- [Source Tree](architecture/source-tree.md)

---

**Last Updated:** 2025-12-05
**Verified With:**
- OpenOCD 0.12.0
- GDB 16.3
- STM32F469 Discovery board
- ST-Link/V2-1 firmware

---

**Happy Debugging! 🐛🔍**
