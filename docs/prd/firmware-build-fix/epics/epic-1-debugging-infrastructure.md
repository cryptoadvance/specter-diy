# Epic 1: Establish Debugging Infrastructure - Brownfield Enhancement

**Project:** Specter-DIY MicroPython Upgrade - Firmware Flash/Boot Fix
**Epic ID:** EPIC-1
**Phase:** Phase 1 (Critical First Step)
**Priority:** CRITICAL
**Status:** Not Started
**Estimated Effort:** 1-2 days (preliminary)

---

## Epic Goal

Establish essential debugging infrastructure (JTAG/SWD, serial console, LED diagnostics) to enable systematic diagnosis of firmware flash/boot failures in the MicroPython v1.25 upgrade.

---

## Epic Description

### Existing System Context

- **Current Project:** Specter-DIY Bitcoin hardware wallet on STM32F469 Discovery board
- **Technology Stack:**
  - MicroPython v1.25+ (upgraded from v1.x)
  - LVGL v9.3.0 (upgraded from v8.x)
  - ARM Cortex-M4 microcontroller (STM32F469)
  - Arm GNU Toolchain v14.3.rel1
  - Custom bootloader with secure boot
- **Current State:** Firmware builds successfully but fails during flashing (breaks mid-process) and board fails to reboot
- **Critical Gap:** No established methods for on-board debugging yet

**References:**
- Problem details: `problem-statement.md`
- Current architecture: `current-architecture-understanding.md`
- Prerequisites: `prerequisites.md`

### Enhancement Details

**What's being added:**
- JTAG/SWD debugging connection using integrated ST-Link/V2-1 debugger
- OpenOCD and GDB debugging workflow
- Serial console access (USB CDC or UART)
- LED diagnostic codes for boot stage visualization
- Memory dump and analysis procedures
- Documentation of debugging procedures for future use

**How it integrates:**
- Non-invasive: Uses existing ST-Link debugger built into Discovery board
- Serial console connects to existing UART/USB CDC capabilities
- LED codes added only to firmware (bootloader remains unmodified for MVP)
- Debugging tools run on host machine, no firmware changes required initially

**Success criteria:**
- Can attach JTAG/SWD debugger and halt/resume MCU
- Can read/write memory via debugger (flash, RAM, registers)
- Serial console accessible and displays output
- LED diagnostic codes show firmware boot stages (entry point, initialization, REPL ready, etc.)
- Team can systematically debug flash and boot failures

---

## Stories

### Story 1: Set Up JTAG/SWD Debugging Connection

**Description:** Connect to STM32F469 Discovery board via integrated ST-Link debugger, establish OpenOCD connection, and verify basic debugging capabilities.

**Tasks:**
- Connect STM32F469 Discovery board via Mini-USB (ST-Link interface)
- Install OpenOCD and arm-none-eabi-gdb via Nix (add to `flake.nix` if not present)
- Verify Nix development environment includes: openocd, gdb-arm-embedded
- Test OpenOCD connection: `openocd -f board/stm32f469discovery.cfg`
- Test GDB connection and verify can attach to target
- Verify can halt CPU, read registers, and resume execution
- Document Nix flake setup in debugging guide

**Acceptance Criteria:**
- OpenOCD and GDB available via `nix develop` or `nix-shell`
- OpenOCD successfully connects to STM32F469 board
- GDB can attach via `target extended-remote :3333`
- Can execute basic GDB commands: `info registers`, `monitor reset halt`, `continue`
- Can read flash memory at 0x08000000
- Can read RAM at 0x20000000
- Nix setup documented for reproducibility

---

### Story 2: Establish Serial Console Access

**Description:** Set up serial console communication to access MicroPython REPL and view debug output.

**Tasks:**
- Identify serial interface on STM32F469 Discovery (USB CDC or UART pins)
- Connect via Micro-USB (USB CDC) or USB-to-UART adapter
- Install serial terminal software (minicom, screen, or putty)
- Configure serial parameters (baud rate: 115200, 8N1)
- Test connection with existing firmware (if available) or bootloader output
- Document serial console setup procedure

**Acceptance Criteria:**
- Serial console connects successfully
- Can see boot messages or REPL prompt (if firmware boots)
- Console remains stable during reset cycles
- Documentation includes connection steps and troubleshooting

---

### Story 3: LED Diagnostic Codes (Firmware Only)

**Description:** Document and verify LED diagnostic codes for boot stages. **MVP Scope: Firmware only - bootloader remains unmodified.**

**Status:** ✅ Mostly complete - upstream MicroPython already implements LED patterns

#### Already Implemented (by MicroPython upstream)

The STM32F469 Discovery board has 4 LEDs configured in `mpconfigboard.h`:
- LED1 (green, PG6) - dirty flash cache indicator
- LED2 (orange, PD4) - boot progress
- LED3 (red, PD5) - error indicator
- LED4 (blue, PK3) - SD card activity

Existing LED patterns in `boardctrl.c`:
| Stage | Pattern | Code Location |
|-------|---------|---------------|
| MicroPython init | Orange ON | boardctrl.c:183 |
| boot.py error | Red/green flash 4x | boardctrl.c:207 |
| main.py error | Red/green flash 3x | boardctrl.c:245 |
| Fatal error | All LEDs ON + toggle | boardctrl.c:38-56 |

Fault handlers (MemManage, BusFault, UsageFault) call `MICROPY_BOARD_FATAL_ERROR()` which triggers the all-LEDs-toggle pattern.

#### Completed Tasks
- [x] Identify available LEDs on STM32F469 Discovery board
- [x] LED pattern for MicroPython initialization started (orange ON)
- [x] LED pattern for error conditions (flash patterns, all-toggle for faults)
- [x] Document LED code meanings in `docs/debugging.md` (LED Diagnostics section)

#### Remaining Tasks (Optional Enhancement)
- [ ] Add very early boot LED (in Reset_Handler or early main, before MicroPython init)
  - Currently no LED feedback if crash occurs before `boardctrl_top_soft_reset_loop()`
  - Would require adding GPIO init + LED write to startup code
- [ ] Measure boot time overhead (expected minimal, <1ms for GPIO writes)

**Acceptance Criteria:**
- [x] LEDs display distinct patterns for firmware boot stages
- [x] Can visually identify where firmware boot process fails (after MicroPython init starts)
- [x] Bootloader code remains unmodified
- [x] LED codes documented in debugging procedures (`docs/debugging.md`)
- [ ] Boot time overhead measured (skipped - overhead is negligible)
- [x] Rationale for firmware-only scope documented

---

### Story 4: Create Memory Dump and Analysis Procedures

**Description:** Develop procedures to dump flash memory, compare with expected binary layout, and analyze memory contents.

**Tasks:**
- Create GDB script to dump entire flash region (0x08000000 - end)
- Create procedure to dump specific regions (bootloader, firmware, etc.)
- Document how to compare memory dump with binary files (hexdump, diff)
- Create checklist for memory verification:
  - Vector table at expected address
  - Stack pointer initialization value
  - Reset vector points to valid code
  - Firmware signature (if applicable)
- Test procedures on current (broken) firmware
- Document findings and create analysis template

**Acceptance Criteria:**
- Can dump flash memory via GDB: `dump memory flash.bin 0x08000000 0x08200000`
- Can compare dumped memory with expected binary files
- Can verify vector table structure and values
- Can identify memory layout issues systematically
- Procedures documented with examples

---

### Story 5: Document Debugging Workflow and Create Quick Reference

**Description:** Create comprehensive debugging documentation and quick reference guide for the team.

**Tasks:**
- Document complete debugging setup procedure (hardware + software)
- Create OpenOCD + GDB command quick reference
- Document memory address quick reference (flash, RAM, bootloader, firmware)
- Create troubleshooting guide for common issues:
  - OpenOCD connection failures
  - GDB attachment problems
  - Serial console not working
  - LED codes not visible
- Add debugging section to build documentation
- Create debugging checklist for systematic investigation

**Acceptance Criteria:**
- Complete debugging setup guide exists (hardware + software installation)
- Quick reference card with essential GDB commands
- Memory map documented with key addresses
- Troubleshooting guide covers common issues
- Documentation validated by another team member following it

---

## Compatibility Requirements

- [ ] **No firmware changes required initially** - Debugging infrastructure should work with existing broken firmware
- [ ] **Non-destructive** - Debugging procedures should not corrupt or modify flash (except when explicitly flashing)
- [ ] **Bootloader preservation** - Ensure debugging doesn't accidentally overwrite or corrupt bootloader
- [ ] **Reproducible** - Another developer can set up debugging following documentation
- [ ] **Cross-platform considerations** - Document any OS-specific steps (Linux/macOS/Windows)

---

## Risk Mitigation

**Primary Risk:** Cannot establish debugger connection due to hardware issues, locked debug interface, or corrupted bootloader

**Mitigation:**
- Test with known-good board first (if available)
- Check ST-Link firmware version and update if needed
- Verify debug interface not locked by reading option bytes
- Have recovery procedure ready (mass erase via ST-Link utility)
- Keep backup bootloader binary for emergency reflash

**Rollback Plan:**
- Debugging infrastructure is additive (no code changes initially)
- Can disconnect debugger and continue with previous workflow
- LED diagnostic codes can be removed if they cause issues
- Documentation can be rolled back to previous version

**Additional risks:** See `risks-mitigation.md` for full project risk assessment

---

## Definition of Done

- [ ] JTAG/SWD connection established with OpenOCD and GDB
- [ ] Can attach debugger and halt/resume MCU reliably
- [ ] Can read/write memory via debugger (verified on flash and RAM)
- [ ] Serial console accessible and displays output
- [ ] LED diagnostic codes implemented and tested
- [ ] Can dump flash memory and compare with expected binary
- [ ] Can read vector table and verify structure
- [ ] Memory dump procedures documented and validated
- [ ] Debugging workflow fully documented with examples
- [ ] Quick reference guide created and reviewed
- [ ] Another team member successfully set up debugging using documentation
- [ ] Debugging infrastructure ready for Phase 2 (debugging flash failure)
- [ ] All items from `success-criteria.md` Phase 1 section completed

---

## Dependencies

**Upstream:**
- None - This is the first phase, no dependencies

**Downstream:**
- Epic 2, 3, 4, 5, 6 all require working debugging tools from this epic

**External:**
- Hardware: STM32F469 Discovery board with integrated ST-Link (see `prerequisites.md`)
- Software: OpenOCD, arm-none-eabi-gdb must be installed on host (see `prerequisites.md`)
- Access: USB port on development machine, physical access to board

---

## Notes

- **CRITICAL FIRST STEP:** Do not proceed to other phases without establishing debugging first
- **Non-negotiable:** Cannot debug flash/boot failures without debugger and serial console
- **Time investment:** Spending 1-2 days on infrastructure will save many days of blind debugging
- **Knowledge building:** This establishes foundational debugging skills for entire team
- **Reusable:** Debugging infrastructure will be used for all future firmware work
- **Training resources:** See `developer-resources-training.md` for ARM/STM32 debugging tutorials

---

## References

- **PRD Index:** `index.md`
- **Implementation Phases:** `implementation-phases.md` - Phase 1
- **Success Criteria:** `success-criteria.md` - Phase 1 section
- **Prerequisites:** `prerequisites.md` - Software/Hardware requirements
- **Developer Resources:** `developer-resources-training.md` - ARM Cortex-M debugging training
- **Known Issues:** `known-issues-investigations-needed.md` - Diagnostic procedures

---

**Epic Status:** ✅ Ready for Story Breakdown and Development
**Next Step:** Assign to developer with ARM/STM32 debugging experience
