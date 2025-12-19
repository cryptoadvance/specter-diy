# Serial Console Testing Checklist

This checklist guides you through manual testing of serial console access for the STM32F469 Discovery board.

**Story:** EPIC1-STORY-2 - Establish Serial Console Access
**Purpose:** Verify serial console connectivity and MicroPython REPL access
**Prerequisites:** Hardware connected, Nix development environment available

---

## Pre-Test Setup

### Hardware Verification

- [ ] **Mini-USB cable** connected to **CN1 port** (ST-Link debugger)
- [ ] **Micro-USB cable** connected to **CN13 port** (Target power)
- [ ] **LD2 (PWR) LED** is lit (red/orange)

### Software Verification

```bash
# Enter development environment
nix develop

# Verify tools are available
which screen minicom picocom
```

---

## Test 1: Device Detection

**Objective:** Verify serial device appears in system

### Steps:

```bash
# List USB devices from STMicroelectronics
lsusb | grep -i "ST\|STM"
```

**Expected result:**
```
Bus 003 Device XXX: ID 0483:374b STMicroelectronics ST-LINK/V2.1
```

```bash
# Find serial device
ls -l /dev/ttyACM*
```

**Expected result:**
```
crw-rw---- 1 root dialout 166, 0 Dec  5 10:30 /dev/ttyACM0
crw-rw---- 1 root dialout 166, 1 Dec  5 10:30 /dev/ttyACM1
```

```bash
# Verify which is ST-Link VCP
udevadm info /dev/ttyACM0 | grep ID_MODEL
udevadm info /dev/ttyACM1 | grep ID_MODEL
```

**Look for:** `E: ID_MODEL=STM32_STLink`

### Test Result:

- [ ] **PASS** - Serial device detected
- [ ] **FAIL** - No device detected (see troubleshooting)

**Notes:**
```
Device path used: /dev/ttyACM___
```

---

## Test 2: Serial Connection

**Objective:** Connect to serial console and verify communication

### Option A: Using screen (recommended)

```bash
# Connect to serial console
screen /dev/ttyACM1 115200

# Exit: Ctrl-A, then K (kill), then Y (confirm)
```

### Option B: Using minicom

```bash
# Connect
minicom -D /dev/ttyACM1 -b 115200

# Exit: Ctrl-A, then X (exit)
```

### Option C: Using picocom

```bash
# Connect
picocom -b 115200 /dev/ttyACM1

# Exit: Ctrl-A, then Ctrl-X
```

### Test Result:

- [ ] **PASS** - Terminal connects without errors
- [ ] **FAIL** - Connection errors (see troubleshooting)

**Output observed:**
```
[Paste or describe what you see here]




```

---

## Test 3: Boot Messages / REPL Access

**Objective:** Verify we can see firmware output

### Steps:

1. With serial terminal connected, press **RESET button** on Discovery board
2. Observe output in terminal

### Expected Outputs:

**Scenario A: Firmware boots successfully**
```
MicroPython v1.25.0 on 2025-12-05; STM32F469DISC with STM32F469
Type "help()" for more information.
>>>
```

**Scenario B: Bootloader output**
```
Specter Bootloader v1.0
Checking firmware signature...
Firmware valid. Booting...
```

**Scenario C: Firmware fails to boot**
- Partial boot messages
- Exception traceback
- Nothing (early boot failure)

### Test Result:

- [ ] **PASS** - Saw output (describe below)
- [ ] **FAIL** - No output (see troubleshooting)

**What I observed:**
```
[Paste boot messages here]




```

**Scenario that occurred:** _________________

---

## Test 4: Console Stability During Reset

**Objective:** Verify console remains connected through reset cycles

### Steps:

1. Connect serial terminal
2. Press **RESET button** 3 times
3. Observe if:
   - Terminal disconnects/reconnects
   - Output appears consistently
   - No connection errors

### Test Result:

- [ ] **PASS** - Console remains stable through resets
- [ ] **PARTIAL** - Console reconnects automatically
- [ ] **FAIL** - Must manually reconnect after reset

**Notes:**
```
[Describe behavior during resets]


```

---

## Test 5: Interactive REPL Commands

**Objective:** Send commands to MicroPython REPL (if firmware boots)

### Steps:

**If REPL prompt (`>>>`) is visible:**

```python
>>> print("Hello from Specter")
# Expected: Hello from Specter

>>> import sys
>>> sys.version
# Expected: '3.4.0; MicroPython v1.25.0'

>>> import machine
>>> machine.freq()
# Expected: 180000000

>>> help()
# Expected: Shows available modules
```

### Test Result:

- [ ] **PASS** - All commands executed successfully
- [ ] **PARTIAL** - Some commands worked
- [ ] **N/A** - Firmware doesn't boot to REPL
- [ ] **FAIL** - Cannot send commands

**Commands tested and results:**
```
[Paste your REPL session here]




```

---

## Test 6: Serial Output Capture

**Objective:** Verify we can reliably capture serial output for analysis

### Steps:

**Using script command:**

```bash
# Start capture
script -f serial_capture.log

# Connect to serial console
screen /dev/ttyACM1 115200

# Press RESET, interact with REPL
# Exit screen: Ctrl-A, K, Y
# Exit script: Ctrl-D

# View captured log
cat serial_capture.log
```

**Using screen's built-in logging:**

```bash
# Start screen with logging
screen -L -Logfile serial_output.log /dev/ttyACM1 115200
```

### Test Result:

- [ ] **PASS** - Output captured successfully
- [ ] **FAIL** - Capture incomplete or failed

**Log file location:** _________________

---

## Permission Issues (Linux only)

**If you get "Permission denied" errors:**

```bash
# Check current groups
groups

# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and log back in for changes to take effect
# Then retest
```

- [ ] **DONE** - Added to dialout group (if needed)
- [ ] **N/A** - Already had permissions

---

## Overall Test Summary

### Acceptance Criteria Status:

- [ ] Serial console connects successfully
- [ ] Can see boot messages or REPL prompt (if firmware boots)
- [ ] Console remains stable during reset cycles
- [ ] Documentation includes connection steps and troubleshooting (✅ Already complete)
- [ ] Can send commands to REPL (if accessible)
- [ ] Serial output captured reliably for analysis

### Story Tasks Status:

- [x] Identify serial interface on STM32F469 Discovery
- [x] Document physical connection method
- [x] Install serial terminal software via Nix
- [x] Configure serial parameters (115200, 8N1)
- [ ] Test connection with existing firmware or bootloader output
- [ ] Verify console stability during board reset cycles
- [ ] Test sending commands to REPL (if firmware boots to REPL)
- [x] Document serial console setup procedure in debugging guide
- [x] Add troubleshooting section for common serial issues

---

## Troubleshooting Reference

### Issue: Permission denied opening /dev/ttyACM1

**Solution:** Add user to dialout group (see Permission Issues section above)

---

### Issue: No output in serial console

**Possible causes:**
1. Wrong device selected (try `/dev/ttyACM0` instead of `/dev/ttyACM1`)
2. Firmware not configured for serial output
3. Baud rate mismatch (ensure 115200)
4. Firmware hasn't booted yet

**Debug steps:**
```bash
# Verify device
udevadm info /dev/ttyACM1 | grep ID_MODEL

# Try different device
screen /dev/ttyACM0 115200
```

---

### Issue: Garbled output or random characters

**Cause:** Baud rate mismatch

**Solution:**
- Ensure terminal is set to **115200 baud**
- Verify firmware is configured for 115200 (standard for MicroPython)

---

### Issue: Console disconnects during reset

**Cause:** Some terminal programs handle reconnection differently

**Solution:**
- Use `screen` or `picocom` (handle reconnect well)
- Or manually reconnect after reset

---

## Test Completion

**Date tested:** _________________
**Tested by:** _________________
**Hardware:** STM32F469 Discovery
**Serial device:** _________________
**Tool used:** _________________

**Overall result:**
- [ ] All tests passed - Serial console fully functional
- [ ] Partial success - Some tests passed (describe below)
- [ ] Failed - Serial console not working (see notes below)

**Notes and observations:**
```
[Add any additional notes, observations, or issues encountered]






```

---

## Next Steps

**If all tests passed:**
1. Update story status to "Ready for Review"
2. Proceed to next debugging infrastructure story

**If tests partially passed:**
1. Document specific failures
2. Investigate root cause
3. Consult troubleshooting in `docs/debugging.md`

**If tests failed:**
1. Verify hardware connections (both USB cables)
2. Check LD2 PWR LED is lit
3. Review `docs/debugging.md` troubleshooting section
4. Consider testing with different USB cables

---

## Documentation Reference

- **Comprehensive guide:** [docs/debugging.md](../debugging.md) - Section "Serial Console Access"
- **JTAG/SWD setup:** [docs/firmware-dev/jtag-swd-debugging.md](jtag-swd-debugging.md)
- **Tech stack:** [docs/architecture/tech-stack.md](../architecture/tech-stack.md)

---

**Created:** 2025-12-05
**Story:** EPIC1-STORY-2
**Purpose:** Manual testing checklist for serial console access verification
