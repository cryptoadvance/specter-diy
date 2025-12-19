# Implementation Phases

**Note on Effort Estimates:** The effort estimates provided below are preliminary and should be validated by the development team during planning. Actual time may vary based on developer experience with ARM/STM32 debugging and the complexity of issues discovered.

---

## Phase 1: Establish Debugging Infrastructure (Critical First Step)

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

## Phase 2: Create Minimal Test Firmware (MVP Core)

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

## Phase 3: Debug Flash Failure (MVP Core)

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

## Phase 4: Fix and Validate Boot (MVP Core)

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

## Phase 5: Incremental Module Testing (MVP Completion)

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

## Phase 6: Complex Application Testing (Post-MVP)

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
