# Brownfield PRD: Fix Firmware Flash/Boot Failure After MicroPython Upgrade

**Project:** Specter-DIY MicroPython Upgrade
**Branch:** `micropython-upgrade`
**Document Version:** 1.2 (PM Review - Added Prerequisites, Definition of Done, Developer Resources)
**Date:** 2025-12-05
**Author:** Mary (Business Analyst AI), John (PM AI)
**Target Audience:** Firmware/Binary Developers, C Developers, Embedded Systems Debuggers

---

## Document Scope

This PRD focuses on diagnosing and fixing the firmware flash/boot failure after the MicroPython upgrade. Scope includes:

**IN SCOPE:**
- Establishing on-board debugging infrastructure (JTAG/SWD, serial, LEDs)
- Creating simple test firmware to isolate issues
- Diagnosing flash failure and boot problems
- Fixing memory layout and bootloader integration issues
- Binary format and assembly verification

**OUT OF SCOPE (for MVP):**
- Complex Python application code in `src/` folder (use simple test code instead)
- Full wallet functionality testing
- LVGL GUI features (beyond basic "hello world" display test)

---

## Executive Summary

Specter-DIY is a Bitcoin hardware wallet built from off-the-shelf components using an STM32F469 Discovery board. The project upgraded its MicroPython foundation from v1.x to v1.25+, along with LVGL from v8.x to v9.3.0.

**Problem:** The firmware build succeeds, but the resulting binary breaks during the flashing process (fails halfway through) and the board fails to reboot successfully. This indicates a runtime or memory layout issue, not a compilation issue.

**Goal:** Debug and fix the firmware so it successfully flashes to the board and boots properly. Develop debugging techniques and methods for on-board firmware debugging. Start with simple Python test code before moving to the complex application in `src/`.

---

## Problem Statement

### Current State

The `micropython-upgrade` branch contains:
- ✅ **f469-disco submodule**: Successfully updated with MicroPython v1.25+ and LVGL v9.3.0
- ✅ **Docker container**: Upgraded to Arm GNU Toolchain v14.3.rel1 and Python v3.9.23
- ✅ **Build system**: Firmware compiles successfully and produces binaries
- ✅ **Bootloader**: Compiles successfully
- ❌ **Flashing process**: Breaks halfway through flashing firmware to board
- ❌ **Device boot**: Board fails to reboot successfully after flash attempt
- ❌ **Debugging infrastructure**: No established methods for on-board debugging yet

### Pain Points

1. **Flash failure mid-process** - Firmware flashing breaks halfway through, suggesting memory layout, bootloader integration, or binary format issue
2. **Boot failure** - Board does not successfully reboot after flash attempt, indicating potential:
   - Memory address mismatch with bootloader expectations
   - Incorrect vector table location
   - Flash memory corruption
   - Bootloader verification failure
3. **No debugging methods established** - Need to develop techniques for on-board debugging:
   - JTAG/SWD debugging setup
   - Serial console output
   - LED diagnostic codes
   - Memory dump analysis
4. **Complex application code** - Current `src/` folder has complex Bitcoin wallet logic that makes debugging harder
5. **Unclear root cause** - Could be bootloader integration, memory layout, MicroPython v1.25 changes, or binary assembly issue

### Impact

- **Cannot deploy upgraded firmware** to hardware
- **Cannot test** MicroPython v1.25 on actual board
- **Cannot validate** LVGL v9.3.0 display functionality
- **Blocking** entire upgrade branch from being merged
- **No feedback loop** - can't iterate on fixes without working debugging methods

---

## Prerequisites

Before starting this project, ensure the following are available:

### Hardware Requirements

- ✅ **STM32F469 Discovery board** (confirmed available)
- ✅ **ST-Link debugger**: The STM32F469 Discovery board has an integrated ST-Link/V2-1 debugger built-in (accessible via USB). No external debugger needed.
- **USB cables**:
  - Mini-USB for ST-Link debugger connection (integrated on board)
  - Micro-USB for USB CDC serial console (optional)
- **Serial adapter** (optional): USB-to-UART if USB CDC doesn't work

### Software Requirements

**Development Environment:**
- [ ] **Docker** with access to project container (Arm GNU Toolchain v14.3.rel1, Python v3.9.23)
- [ ] **Git** with access to repository and `micropython-upgrade` branch

**Debugging Tools:**
- [ ] **OpenOCD** (Open On-Chip Debugger) for STM32F469 - must be installed on host machine
- [ ] **GDB** (arm-none-eabi-gdb) for ARM debugging - must be installed on host machine
- [ ] **ST-Link utilities** (optional): stlink-tools or STM32CubeProgrammer for alternative flashing

**Analysis Tools:**
- [ ] **arm-none-eabi-binutils** (objdump, readelf, nm) - may be in Docker, verify host access
- [ ] **Serial terminal**: minicom, screen, or putty for serial console access
- [ ] **Hex analysis tools**: srec_cat (optional), hexdump

**Build Tools** (should be in Docker, verify):
- [ ] **arm-none-eabi-gcc** toolchain v14.3.rel1
- [ ] **Python 3.9+** with required packages
- [ ] **Make** and build dependencies

**Action Required:** Verify all software tools are installed and accessible before Phase 1 starts.

### Knowledge Requirements

**Required (Essential):**
- ARM Cortex-M architecture and debugging (JTAG/SWD protocols)
- STM32 microcontrollers (flash memory, boot process, vector tables)
- Embedded systems debugging techniques
- Linker scripts and memory layout
- Binary formats (ELF, HEX, BIN)

**Helpful (Accelerates Work):**
- MicroPython internals and build system
- STM32 HAL (Hardware Abstraction Layer)
- Bootloader concepts and secure boot
- LVGL graphics library

**If Knowledge Gaps Exist:** See "Developer Resources & Training" section below for recommended reading and learning materials.

### Access Requirements

- Repository write access to `micropython-upgrade` branch
- Physical access to STM32F469 Discovery board
- Ability to install debugging software on development machine (OpenOCD, GDB)

---

## Current Architecture Understanding

### Build System Components (As-Is)

#### 1. **Root Makefile** (`./Makefile`)
- Target: `make disco USE_DBOOT=1`
- Passes: `BOARD=STM32F469DISC`, `FLAVOR=SPECTER`, `USE_DBOOT=1`, `CFLAGS_EXTRA='-DMP_CONFIGFILE="<mpconfigport_specter.h>"'`
- Expects: `bin/specter-diy.bin` and `bin/specter-diy.hex` as outputs
- **Status:** ❌ BROKEN with new MicroPython

#### 2. **f469-disco/Makefile** (`./f469-disco/Makefile`)
- Target: `make disco`
- Simpler approach: `BOARD=STM32F469DISC`, `USER_C_MODULES`, `FROZEN_MANIFEST`
- Does NOT use: `FLAVOR`, `USE_DBOOT`, or `CFLAGS_EXTRA`
- **Status:** ✅ May work independently

#### 3. **Build Script** (`./build_firmware.sh`)
- Calls: `make disco USE_DBOOT=1` from root
- Then builds bootloader: `cd bootloader && make stm32f469disco`
- Assembles binaries with Python tools:
  - `make-initial-firmware.py` - Combines startup + bootloader + firmware
  - `upgrade-generator.py` - Creates signed upgrade binaries

#### 4. **MicroPython Port** (`./f469-disco/micropython/ports/stm32/`)
- Board definition: `STM32F469DISC` in `boards/STM32F469DISC/`
- Custom config: `mpconfigport_specter.h` (two copies exist - stm32 and unix ports)
- User C modules: `f469-disco/usermods/` (secp256k1, udisplay_f469, uhashlib, etc.)

#### 5. **Bootloader** (`./bootloader/`)
- Independent C project
- Builds: `startup.hex` and `bootloader.hex`
- Expects firmware at specific memory address
- **Dependency:** Final firmware must be built with `USE_DBOOT=1` for correct memory layout

### Key Files

| File | Purpose | Status |
|------|---------|--------|
| `Makefile` | Root build orchestration | ❌ BROKEN |
| `build_firmware.sh` | Full build + bootloader + signing | ❌ BROKEN |
| `f469-disco/Makefile` | MicroPython build wrapper | ⚠️ UNCLEAR |
| `f469-disco/micropython/ports/stm32/Makefile` | MicroPython STM32 port build | ✅ Should work |
| `f469-disco/micropython/ports/stm32/mpconfigport_specter.h` | Specter custom config | ✅ Exists |
| `bootloader/Makefile` | Bootloader build | ✅ Likely works |

### Changed Build Parameters (MicroPython v1.x → v1.25+)

Recent git commits show these key changes:
- `b939993` - "Update Makefile for Micropython v1.25 (Specter adaptation)"
- `3bbbbea` - "Switch f469-disco to fork with upgraded MicroPython"

**Hypothesis:** MicroPython v1.25+ may have:
- Removed or changed `FLAVOR` parameter handling
- Changed how `USE_DBOOT` affects memory layout
- Modified user C module integration mechanism
- Changed frozen manifest handling

---

## Proposed Solution

### High-Level Approach

**Fix the root build system to work with MicroPython v1.25+ while maintaining bootloader compatibility.**

### Core Strategy

1. **Investigate MicroPython v1.25+ build system changes**
   - Identify what replaced `FLAVOR` parameter
   - Understand new board configuration mechanism
   - Document new user C module integration

2. **Align root Makefile with f469-disco/Makefile**
   - Determine if we should use f469-disco/Makefile as primary
   - Or fix root Makefile to properly delegate to f469-disco build
   - Ensure consistent parameter passing

3. **Verify bootloader integration**
   - Confirm `USE_DBOOT` still works or find replacement
   - Verify memory layout matches bootloader expectations
   - Test binary assembly with `make-initial-firmware.py`

4. **Update build documentation**
   - Document new build process
   - Update Docker build instructions
   - Clarify which Makefile does what

---

## Technical Requirements

### Must Have (MVP)

1. **Debugging infrastructure established**
   - JTAG/SWD debugging working with GDB or OpenOCD
   - Serial console output from MicroPython REPL
   - LED diagnostic codes for boot stages
   - Ability to read flash memory and verify contents

2. **Simple test firmware**
   - Minimal MicroPython firmware with "Hello World" Python script
   - No complex user C modules initially (add one by one)
   - No frozen application code from `src/` folder
   - Basic LED blink or serial output to verify execution

3. **Successful flash and boot**
   - Firmware flashes completely without breaking mid-process
   - Board boots successfully and reaches MicroPython REPL
   - Can execute simple Python commands via serial console

4. **Memory layout verified**
   - Bootloader expects firmware at correct address (0x08020000 per `USE_DBOOT=1`)
   - Vector table correctly positioned
   - Linker script matches bootloader expectations
   - No overlap between bootloader and firmware sections

5. **Binary format validated**
   - `initial_firmware.bin` structure correct (startup + bootloader + firmware)
   - Binary signatures valid (if using signed firmware)
   - Hex file addresses correct

6. **Incremental module testing** (after basic boot works)
   - Add user C modules one by one to isolate issues
   - Test order: basic → udisplay → uhashlib → secp256k1 → others

### Out of Scope (For This PRD)

- ❌ Python application code changes in `src/`
- ❌ Bootloader code changes
- ❌ Hardware support for other boards
- ❌ Simulator (`make unix`) fixes (can be Phase 2)
- ❌ Firmware functionality testing (separate testing PRD)

---

## Success Criteria

### Phase 1: Debugging Infrastructure

- [ ] JTAG/SWD connection established with OpenOCD or GDB
- [ ] Can attach debugger and halt/resume MCU
- [ ] Can read/write memory via debugger
- [ ] Serial console accessible (USB CDC or UART)
- [ ] LED diagnostic codes implemented for boot stages

### Phase 2: Minimal Firmware Boot

- [ ] Simple test firmware (no complex modules) compiles successfully
- [ ] Firmware flashes completely without breaking
- [ ] Board boots and reaches MicroPython REPL prompt
- [ ] Can execute Python commands via serial: `print("Hello")`
- [ ] LED blink test works from Python REPL

### Phase 3: Memory Layout Validation

- [ ] Vector table at correct address (verified via debugger)
- [ ] Firmware starts at 0x08020000 (bootloader integration)
- [ ] Stack pointer initialized correctly
- [ ] No memory overlap between bootloader and firmware
- [ ] Flash read-back matches what was written

### Phase 4: Bootloader Integration

- [ ] `initial_firmware.bin` structure validated (startup + bootloader + firmware)
- [ ] Bootloader successfully launches firmware
- [ ] Upgrade process works (if using signed firmware)
- [ ] Device survives power cycle and reboots correctly

### Phase 5: User Module Integration

- [ ] Add user C modules incrementally without breaking boot
- [ ] Each module tested: basic, uhashlib, udisplay, secp256k1, scard
- [ ] All modules load and function correctly
- [ ] Memory usage within acceptable limits

---

## Technical Constraints

### Hard Constraints

- **MicroPython version:** v1.25+ (already upgraded in f469-disco submodule)
- **Toolchain:** Arm GNU Toolchain v14.3.rel1 (already in Docker)
- **Board:** STM32F469 Discovery only (no other boards)
- **Bootloader:** Existing bootloader code should not be modified if possible. The bootloader is part of the security model and changing it requires careful review. However, if the bootloader is definitively proven to be the root cause AND firmware changes cannot fix the issue, then bootloader modifications may be considered as a last resort with appropriate security review.
- **Memory layout:** Must match bootloader expectations (firmware starts at specific address, typically 0x08020000 for `USE_DBOOT=1`)

### Soft Constraints

- **Build time:** Keep under 5 minutes in Docker
- **Binary size:** Keep under flash size limits (~2MB)
- **No Python 2:** Only Python 3.9+ for build tools
- **No breaking changes:** Don't break reproducible build process

---

## Known Issues & Investigations Needed

### Critical Unknowns

1. **WHY does flash break halfway?**
   - Symptoms: Flash process starts, fails mid-write, device unresponsive
   - Possible causes:
     - Write protection enabled on flash regions
     - Binary too large for available flash space
     - Incorrect DFU file format
     - Bootloader protection preventing overwrite
   - Investigation: Monitor flash with debugger, check protection bits

2. **WHY does boot fail?**
   - Symptoms: Device doesn't reach REPL after flash attempt
   - Possible causes:
     - Vector table at wrong address (not 0x08020000)
     - Stack pointer not initialized
     - Bootloader verification failure (signature mismatch)
     - Hard fault during MicroPython initialization
   - Investigation: Attach debugger, step through reset vector

3. **Is memory layout correct?**
   - Bootloader expects firmware at: 0x08020000
   - Current linker script: `stm32f469xi_dboot.ld` should set `TEXT0_ADDR = 0x08020000`
   - Question: Does MicroPython v1.25 respect this? Or did something change?
   - Investigation: Dump ELF file headers, verify load addresses

4. **Is binary assembly correct?**
   - `make-initial-firmware.py` combines: startup.hex + bootloader.hex + firmware.hex
   - Question: Does tool handle MicroPython v1.25 binaries correctly?
   - Investigation: Hexdump output, verify structure

5. **Is bootloader intact?**
   - Bootloader may be corrupted during failed flash
   - Question: Can we re-flash bootloader independently?
   - Investigation: Read bootloader flash region via debugger

### Diagnostic Procedures to Develop

1. **Flash memory dump and compare**
   - Read entire flash contents before/after flash attempt
   - Compare with expected binary layout
   - Identify what's actually written vs what should be written

2. **Boot stage tracing**
   - Add LED codes: bootloader start, firmware entry, MicroPython init, REPL ready
   - Identify exactly where boot fails

3. **Debugger-assisted flash**
   - Use GDB to write flash manually
   - Verify write-back after each chunk
   - Bypass normal flash tools to isolate issue

4. **Minimal bootloader test**
   - Flash known-good v1.x firmware as reference
   - Verify bootloader still works
   - Then attempt v1.25 firmware to isolate regression

### Tools & Resources Needed

- **Hardware debugger:** ST-Link V2 or on-board ST-Link
- **OpenOCD config:** For STM32F469 Discovery
- **Serial adapter:** USB-to-UART if USB CDC doesn't work
- **Reference firmware:** Working v1.x build for comparison
- **Hex dump tools:** srec_cat, objdump, arm-none-eabi-readelf

---

## Risks & Mitigation

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cannot establish debugger connection | 🔴 CRITICAL | Test with multiple tools (OpenOCD, STM32CubeIDE); verify hardware connections |
| Flash corruption requires full board reflash | 🔴 CRITICAL | Keep backup bootloader; document recovery procedure |
| Memory layout fundamentally incompatible | 🔴 HIGH | May need custom linker script or bootloader modifications |
| Issue is hardware-specific (bad board) | 🔴 HIGH | Test with multiple STM32F469 Discovery boards if available |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Takes many iterations to find root cause | 🟡 MEDIUM | Systematic debugging approach; document each test |
| Need to modify bootloader (out of scope) | 🟡 MEDIUM | Escalate if bootloader changes required; may need security review |
| Binary size exceeds flash after module additions | 🟡 MEDIUM | Profile size per module; may need to reduce frozen code |
| Debugging requires specialized equipment | 🟡 MEDIUM | Verify ST-Link availability; document DIY alternatives |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Serial console doesn't work | 🟢 LOW | Use JTAG semihosting or LED codes instead |
| Some user modules don't work | 🟢 LOW | Fix incrementally; acceptable for MVP to skip non-critical modules |
| Documentation out of date | 🟢 LOW | Update docs as we fix issues |

---

## Implementation Phases

**Note on Effort Estimates:** The effort estimates provided below are preliminary and should be validated by the development team during planning. Actual time may vary based on developer experience with ARM/STM32 debugging and the complexity of issues discovered.

---

### Phase 1: Establish Debugging Infrastructure (Critical First Step)

**Goal:** Set up tools and methods to diagnose flash/boot failures

**Tasks:**
1. Connect JTAG/SWD debugger (ST-Link integrated on Discovery board)
2. Test OpenOCD connection: `openocd -f board/stm32f469discovery.cfg`
3. Test GDB connection and basic commands (halt, info registers, x/32xw)
4. Set up serial console access (USB CDC or UART pins)
5. Implement LED diagnostic codes in bootloader/firmware
6. Document debugging procedures

**Success:** Can attach debugger, read memory, and see serial output

**Estimated Effort:** 1-2 days (preliminary estimate)

---

### Phase 2: Create Minimal Test Firmware (MVP Core)

**Goal:** Build simplest possible MicroPython firmware to isolate issues

**Tasks:**
1. Create minimal frozen manifest with single "hello.py" file
2. Disable ALL user C modules in build
3. Use stock MicroPython configuration (minimal mpconfigport changes)
4. Build with `USE_DBOOT=1` for bootloader compatibility
5. Verify binary size and structure

**Success:** Minimal firmware binary created (~500KB instead of 2MB)

**Estimated Effort:** 1 day (preliminary estimate)

---

### Phase 3: Debug Flash Failure (MVP Core)

**Goal:** Diagnose WHY flash breaks halfway and FIX it

**Tasks:**
1. Attempt flash with debugger attached, monitor progress
2. Check flash tool output for errors (dfu-util, st-flash, etc.)
3. Verify bootloader is intact after failed flash
4. Test different flashing methods (DFU, SWD, UART)
5. Compare memory layout with working v1.x firmware
6. Check vector table address, stack pointer initialization
7. Verify linker script `stm32f469xi_dboot.ld` matches bootloader expectations

**Success:** Identify root cause of flash failure

**Estimated Effort:** 2-3 days (preliminary estimate, investigation heavy)

---

### Phase 4: Fix and Validate Boot (MVP Core)

**Goal:** Get minimal firmware to boot and reach REPL

**Tasks:**
1. Apply fix from Phase 3 (memory layout, linker script, binary format, etc.)
2. Flash corrected firmware
3. Monitor boot process via debugger (step through reset vector)
4. Verify MicroPython initialization completes
5. Test serial console access to REPL
6. Execute simple Python: `print("Hello")`, LED blink

**Success:** Board boots, REPL accessible, Python executes

**Estimated Effort:** 1-2 days (preliminary estimate)

---

### Phase 5: Incremental Module Testing (MVP Completion)

**Goal:** Add user C modules one by one without breaking boot

**Tasks:**
1. Add basic modules first (uhashlib)
2. Test boot after each module addition
3. Add display module (udisplay_f469) - test basic LVGL
4. Add crypto module (secp256k1) - test basic operations
5. Add remaining modules (scard, uebmit, sdram)
6. Document any module-specific issues and fixes

**Success:** All user C modules working without boot failures

**Estimated Effort:** 2-3 days (preliminary estimate)

---

### Phase 6: Complex Application Testing (Post-MVP)

**Goal:** Integrate actual Specter application from `src/` folder

**Tasks:**
1. Create manifest with `src/` application frozen
2. Test boot with full application
3. Debug any application-specific issues
4. Test wallet functionality
5. Test GUI with LVGL v9.3.0

**Success:** Full Specter-DIY application runs on upgraded firmware

**Estimated Effort:** 3-5 days (preliminary estimate)

---

## Architecture Decisions

### Decision 1: Makefile Structure

**Options:**
- A) Keep two Makefiles (root and f469-disco), root delegates to f469-disco
- B) Merge into single Makefile at root
- C) Use f469-disco/Makefile as primary, deprecate root Makefile

**Recommendation:** Option A (delegate) - Maintains separation of concerns

---

### Decision 2: Custom MicroPython Config

**Options:**
- A) Keep `CFLAGS_EXTRA='-DMP_CONFIGFILE="<mpconfigport_specter.h>"'` if it works
- B) Move config into board-specific mpconfigboard.h
- C) Create custom board variant in MicroPython boards/ directory

**Recommendation:** Option A if it still works, otherwise Option C

---

### Decision 3: Bootloader Memory Layout

**Options:**
- A) Keep `USE_DBOOT=1` if parameter still exists
- B) Create custom linker script in board definition
- C) Modify board mpconfigboard.mk to set linker script

**Recommendation:** Investigate first, then choose B or C

---

## Appendices

### A. Recent Commits Analysis

Key commits on `micropython-upgrade` branch:

```
705e962 Update f469-disco
64860ca Upgrade Docker container to Arm GNU Toolchain v14.3.rel1 and Python v3.9.23
b9f3813 Update build instructions: avoid conflicts with Homebrew's includes
b939993 Update Makefile for Micropython v1.25 (Specter adaptation)
3bbbbea Switch f469-disco to fork with upgraded MicroPython
```

**Analysis:**
- Docker toolchain upgraded ✅
- Build instructions updated for macOS ✅
- Root Makefile updated for v1.25 but apparently still broken
- f469-disco submodule switched to fork with MicroPython upgrade

---

### B. Build System File Tree

```
specter-diy/
├── Makefile                    # Root build orchestrator (BROKEN)
├── build_firmware.sh           # Full build script (BROKEN)
├── Dockerfile                  # Build container (UPDATED)
├── bin/                        # Build outputs
│   ├── specter-diy.bin        # Main firmware binary
│   └── specter-diy.hex        # Main firmware hex
├── bootloader/                # Secure bootloader
│   ├── Makefile               # Bootloader build (WORKS)
│   └── tools/
│       ├── make-initial-firmware.py
│       └── upgrade-generator.py
├── f469-disco/                # MicroPython port submodule
│   ├── Makefile               # Simplified build (UNKNOWN)
│   ├── micropython/           # MicroPython v1.25+
│   │   └── ports/
│   │       ├── stm32/         # STM32 port
│   │       │   ├── Makefile   # Main MicroPython build
│   │       │   ├── boards/STM32F469DISC/
│   │       │   └── mpconfigport_specter.h
│   │       └── unix/          # Simulator port
│   │           └── mpconfigport_specter.h
│   └── usermods/              # Custom C modules
│       ├── secp256k1/micropython.mk
│       ├── udisplay_f469/micropython.mk
│       ├── uhashlib/micropython.mk
│       ├── scard/micropython.mk
│       └── uebmit/micropython.mk
├── manifests/
│   ├── disco.py               # Frozen Python modules for disco
│   ├── unix.py                # Frozen Python modules for simulator
│   └── debug.py               # Debug manifest
└── src/                       # Python application (OUT OF SCOPE)
    └── apps/
```

---

### C. User C Modules

Critical modules that must compile:

1. **secp256k1** - Bitcoin elliptic curve crypto (from Bitcoin Core)
2. **udisplay_f469** - LVGL v9.3.0 display driver for STM32F469
3. **uhashlib** - Hash functions (SHA256, RIPEMD160, etc.)
4. **scard** - Smartcard/JavaCard integration
5. **uebmit** - Bitcoin miniscript support
6. **sdram** - External SDRAM support

---

### D. References

- **MicroPython v1.25 Release Notes:** [Check upstream MicroPython repo]
- **STM32 Port Documentation:** `f469-disco/micropython/ports/stm32/README.md`
- **Specter Bootloader:** `bootloader/doc/bootloader-spec.md`
- **Build Instructions:** `docs/build.md`
- **Existing Build Issues:** [Link to GitHub issues if any]

---

## Definition of Done

The project is considered complete when ALL of the following criteria are met:

### Technical Completion

- [ ] **Firmware successfully flashes** - Flash process completes without breaking mid-way
- [ ] **Board boots successfully** - Device reaches MicroPython REPL prompt after flash
- [ ] **Basic Python execution works** - Can run simple Python commands from REPL
- [ ] **All user C modules load** - secp256k1, udisplay_f469, uhashlib, scard, uebmit, sdram all function correctly
- [ ] **Memory layout validated** - Vector table, stack pointer, and firmware address correct
- [ ] **Bootloader integration verified** - Bootloader successfully launches firmware after power cycle
- [ ] **No regressions** - All previously working functionality still works

### Documentation

- [ ] **Build process documented** - Updated docs/build.md with any new build steps
- [ ] **Debugging procedures documented** - OpenOCD setup, GDB commands, serial console access
- [ ] **Root cause analysis documented** - What was broken, why, and how it was fixed
- [ ] **Memory layout changes documented** - Any linker script or address changes explained
- [ ] **Lessons learned captured** - Known issues, gotchas, and troubleshooting tips

### Testing & Validation

- [ ] **Clean build from scratch** - Another developer can build firmware following updated docs
- [ ] **Reproducible flash process** - Flashing works consistently, not just once
- [ ] **Basic hardware wallet functions tested** - Display, buttons, and critical operations work
- [ ] **No build warnings** - Clean build output (or documented acceptable warnings)

### Integration

- [ ] **Changes committed** - All fixes committed to `micropython-upgrade` branch
- [ ] **Build system stable** - No breaking changes to build process
- [ ] **Ready for merge** - Branch ready to merge to `master` (pending full QA)

**Final Acceptance:** Project owner confirms firmware works on physical hardware and is ready for further development/testing.

---

## Next Steps

### Immediate Actions (Priority Order)

1. **Set up debugging hardware**
   - Connect STM32F469 Discovery board via USB (built-in ST-Link debugger)
   - Verify software prerequisites installed: OpenOCD, GDB (see Prerequisites section)
   - Test OpenOCD connection: `openocd -f board/stm32f469discovery.cfg`
   - Verify GDB can attach and read registers

2. **Attempt minimal firmware build**
   - Create simple frozen manifest: `manifests/minimal.py` with hello world
   - Build with: `make disco USE_DBOOT=1 FROZEN_MANIFEST=manifests/minimal.py`
   - Check binary size (should be much smaller without modules)

3. **Reproduce flash failure with monitoring**
   - Attempt flash while debugger attached
   - Document exact point of failure
   - Check for error messages or status codes

4. **Verify memory layout**
   - Use `arm-none-eabi-readelf -h bin/specter-diy.elf` to check entry point
   - Use `arm-none-eabi-objdump -h bin/specter-diy.elf` to check section addresses
   - Verify firmware TEXT0_ADDR = 0x08020000

5. **Test known-good v1.x firmware (if available)**
   - Flash working v1.x firmware as baseline
   - Verify bootloader still functions correctly
   - Document differences in behavior

---

## Developer Resources & Training

If the assigned developer lacks experience with ARM Cortex-M debugging or STM32 development, the following resources will help build the necessary knowledge.

### Critical Reading (Start Here)

**ARM Cortex-M Fundamentals:**
1. **ARM Cortex-M4 Technical Reference Manual** - Understanding the CPU architecture
   - Focus on: Exception model, vector table, memory map, debugging architecture
   - Available: ARM official documentation website

2. **STM32F469 Reference Manual (RM0386)** - Microcontroller specifics
   - Focus on: Memory organization, Flash interface, boot modes, debug access
   - Available: STMicroelectronics website

3. **The Definitive Guide to ARM Cortex-M3 and Cortex-M4 Processors** by Joseph Yiu
   - Comprehensive book covering architecture, debugging, and development
   - Chapters 1-5, 13-14 are most relevant

**Debugging Tools:**
4. **OpenOCD User's Guide** - Understanding JTAG/SWD debugging
   - Focus on: STM32 target configuration, GDB integration, flash programming
   - Available: openocd.org/doc

5. **GDB Debugging Cheat Sheet** - Essential GDB commands for embedded systems
   - Commands: info registers, x/memory, break, step, continue, monitor commands
   - Available: Many online tutorials and quick references

**Linker Scripts & Memory Layout:**
6. **GNU LD Linker Script Guide** - Understanding linker scripts
   - Focus on: MEMORY regions, SECTIONS, symbol definitions, load vs runtime addresses
   - Available: GNU binutils documentation

### STM32-Specific Resources

**STM32F469 Discovery Board:**
- **User Manual (UM1932)** - Board documentation including ST-Link debugger pins
- **STM32CubeMX** - Tool for configuration and code generation (useful for reference)
- **STM32 community forums** - support.st.com for troubleshooting

**MicroPython on STM32:**
- **MicroPython STM32 Port Documentation** - f469-disco/micropython/ports/stm32/README.md
- **MicroPython Build System Changes v1.25** - Check release notes for breaking changes
- **User C Modules Documentation** - How to integrate C modules into MicroPython

### Hands-On Practice (Before Starting)

**Recommended Exercises:**

1. **Basic OpenOCD + GDB Workflow**
   - Connect to STM32F469 Discovery board
   - Halt CPU, read registers, read/write memory
   - Practice: `openocd -f board/stm32f469discovery.cfg` then `arm-none-eabi-gdb`

2. **Flash Memory Inspection**
   - Use GDB to dump flash memory: `x/256xw 0x08000000`
   - Compare with binary file contents: `xxd firmware.bin`
   - Understand flash organization and sectors

3. **Simple Blinky Program**
   - Write minimal ARM assembly or C program to blink LED
   - Build with arm-none-eabi-gcc, create custom linker script
   - Flash manually with OpenOCD, debug with GDB
   - This builds intuition for memory layout and boot process

4. **Vector Table Analysis**
   - Examine vector table in working firmware: first 64 bytes of flash
   - Verify: Initial SP (stack pointer), Reset vector, exception handlers
   - Compare with datasheet expectations

### Time Investment Estimate

- **Minimal functional knowledge:** 8-16 hours of reading + 4-8 hours hands-on practice
- **Comfortable working knowledge:** 20-30 hours total
- **Expert level:** 40+ hours (not necessary for this project)

**Recommendation:** If developer is completely new to ARM/STM32, allocate 2-3 days for training before starting Phase 1. This investment will significantly accelerate debugging and reduce trial-and-error time.

### Quick Reference Checklists

**OpenOCD + GDB Essential Commands:**
```bash
# Terminal 1: Start OpenOCD
openocd -f board/stm32f469discovery.cfg

# Terminal 2: Connect GDB
arm-none-eabi-gdb bin/firmware.elf
(gdb) target extended-remote :3333
(gdb) monitor reset halt
(gdb) load
(gdb) continue

# Useful GDB commands
info registers              # Show all registers
info reg sp pc              # Stack pointer and program counter
x/32xw 0x08000000          # Dump 32 words from flash start
x/32xw $sp                 # Dump stack
disassemble $pc            # Disassemble current location
break main                 # Set breakpoint
monitor reset init         # Reset via OpenOCD
```

**Memory Address Quick Reference (STM32F469):**
- Flash start: 0x08000000
- SRAM1 start: 0x20000000
- Bootloader end / Firmware start (USE_DBOOT=1): 0x08020000
- Vector table offset (if using bootloader): 0x20000 (128KB)

---

## Handoff to Development

This PRD provides complete context for diagnosing and fixing the Specter-DIY firmware flash/boot failure after the MicroPython v1.25 upgrade.

**Key Focus Areas:**
- Establishing debugging infrastructure (CRITICAL FIRST STEP)
- Creating minimal test firmware to isolate issues
- Diagnosing flash failure and boot problems
- Memory layout and bootloader integration
- Incremental testing approach

**Expected Outcome:**
- Phase 1: Working debugger connection and monitoring
- Phase 2: Minimal firmware successfully flashes and boots
- Phase 3: Root cause identified and documented
- Phase 4: Fix applied, firmware boots to REPL
- Phase 5: User modules added incrementally

**Target Developer Profile:**
Embedded systems debugger/firmware engineer with experience in:
- ARM Cortex-M debugging (GDB, OpenOCD, JTAG/SWD)
- STM32 flash memory and boot process
- Linker scripts and memory layout
- MicroPython internals helpful but not required

**If developer lacks this experience:** See "Developer Resources & Training" section above for learning materials and recommended preparation (2-3 days of training recommended).

**Before Starting:**
- Review "Prerequisites" section - verify all software tools are installed
- Check "Definition of Done" section - understand project completion criteria
- Read "Developer Resources & Training" if ARM/STM32 experience is limited

**Critical Success Factor:**
DO NOT attempt to fix blindly. Establish debugging first, then diagnose systematically.

---

**Document Status:** ✅ Ready for Development (v1.2 - PM Reviewed)
**Next Agent:** Developer/Engineer to implement fixes
