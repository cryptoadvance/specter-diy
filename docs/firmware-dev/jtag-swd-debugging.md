# JTAG/SWD Debugging Setup - Step by Step

This guide shows you exactly how to set up JTAG/SWD debugging for the STM32F469 Discovery board.

## Hardware Connection

**You need TWO USB cables:**

1. **Mini-USB cable** → **CN1 port** (ST-Link debugger interface)
2. **Micro-USB cable** → **CN13 port** (Powers the target MCU)

⚠️ **Both cables must be connected!** The board won't work with just one.

**Verify connection:**
```bash
lsusb | grep STM
```

You should see:
```
Bus 003 Device 020: ID 0483:374b STMicroelectronics ST-LINK/V2.1
```

---

## Software Setup

### 1. Enter Nix Development Environment

```bash
cd /path/to/specter-diy
nix develop
```

This gives you:
- OpenOCD 0.12.0
- GDB 16.3
- ARM toolchain

### 2. Verify Tools

```bash
openocd --version
# Open On-Chip Debugger 0.12.0

gdb --version
# GNU gdb (GDB) 16.3
```

---

## Basic Debugging Session

### Step 1: Start OpenOCD

**Terminal 1:**
```bash
nix develop
openocd -f board/stm32f469discovery.cfg
```

**Expected output:**
```
Info : Target voltage: 3.223082
Info : [stm32f4x.cpu] Cortex-M4 r0p1 processor detected
Info : [stm32f4x.cpu] target has 6 breakpoints, 4 watchpoints
Info : Listening on port 3333 for gdb connections
```

✅ If you see "Target voltage: 3.2xxxx" - you're good!
❌ If you see "Target voltage: 0.000000" - check your **Micro-USB cable on CN13**

Leave this terminal running.

### Step 2: Connect with GDB

**Terminal 2:**
```bash
nix develop
gdb
```

**Inside GDB:**
```gdb
(gdb) target extended-remote :3333
Remote debugging using :3333
0x0803de1e in ?? ()

(gdb) monitor reset halt
[stm32f4x.cpu] halted due to debug-request
```

✅ You're now connected to the MCU!

### Step 3: Basic Commands

**Read registers:**
```gdb
(gdb) info registers
r0             0x1385a
r1             0x0
...
pc             0x803de1e
```

**Read flash memory (vector table):**
```gdb
(gdb) x/16xw 0x08000000
0x8000000: 0x2004fff8  0x08050e55  0x08046dfb  0x08046de9
0x8000010: 0x08046dfd  0x08046e0d  0x08046e1d  0x00000000
```

The first value (`0x2004fff8`) is your initial stack pointer.
The second value (`0x08050e55`) is your reset vector (firmware entry point).

**Read RAM:**
```gdb
(gdb) x/16xw 0x20000000
0x20000000: 0x000000e9  0x00000045  0xeda4baba  0x00000001
```

**Halt and resume:**
```gdb
(gdb) monitor halt
(gdb) continue
```

---

## Memory Map Quick Reference

| Region | Address | Size | Description |
|--------|---------|------|-------------|
| Flash | `0x08000000` | 2 MB | Firmware code |
| SRAM | `0x20000000` | 384 KB | Internal RAM |
| SDRAM | `0xC0000000` | 16 MB | External RAM |

---

## Common Issues

### "Target voltage: 0.000000"

**Problem:** Board is not powered.

**Solution:** Connect **Micro-USB to CN13** port.

---

### "Address already in use" on port 4444

**Problem:** Another OpenOCD instance is running.

**Solution:**
```bash
pkill openocd
# Then try again
```

---

### "Connection refused" when connecting GDB

**Problem:** OpenOCD is not running.

**Solution:** Start OpenOCD first (see Step 1 above).

---

## What We Verified

During setup, we confirmed:

✅ ST-Link debugger detected (VID:PID 0483:374B)
✅ Target voltage: 3.22V (board powered correctly)
✅ Cortex-M4 processor detected
✅ 6 hardware breakpoints available
✅ 4 hardware watchpoints available
✅ GDB can attach and control CPU
✅ Can read flash memory (vector table)
✅ Can read RAM
✅ Can halt/resume CPU

---

## Next Steps

Once debugging is working, you can:

1. Set up serial console access for MicroPython REPL
2. Add LED diagnostic codes to visualize firmware boot stages
3. Create memory dump and analysis procedures
4. Learn advanced debugging techniques

---

## Full Documentation

For comprehensive documentation, see:
- **Detailed guide:** [docs/debugging.md](../debugging.md)
- **Tech stack:** [docs/architecture/tech-stack.md](../architecture/tech-stack.md)

---

**Last Updated:** 2025-12-05
**Tested With:** OpenOCD 0.12.0, GDB 16.3, STM32F469 Discovery
