# Story: Set Up JTAG/SWD Debugging Connection

**Story ID:** EPIC1-STORY-1
**Epic:** Epic 1 - Establish Debugging Infrastructure
**Priority:** CRITICAL
**Estimated Effort:** 4-6 hours
**Status:** Ready for Review

---

## Story

Connect to STM32F469 Discovery board via integrated ST-Link debugger, establish OpenOCD connection, and verify basic debugging capabilities.

This is a **brownfield enhancement** that adds JTAG/SWD debugging infrastructure to the existing Specter-DIY project. It uses the integrated ST-Link/V2-1 debugger already on the Discovery board and sets up reproducible debugging tools via Nix.

---

## Acceptance Criteria

- [x] OpenOCD and GDB available via `nix develop` or `nix-shell`
- [x] OpenOCD successfully connects to STM32F469 board
- [x] GDB can attach via `target extended-remote :3333`
- [x] Can execute basic GDB commands: `info registers`, `monitor reset halt`, `continue`
- [x] Can read flash memory at 0x08000000
- [x] Can read RAM at 0x20000000
- [x] Nix setup documented for reproducibility

---

## Tasks

- [x] Connect STM32F469 Discovery board via Mini-USB (ST-Link interface)
- [x] Verify current Nix environment configuration (check `shell.nix` or `flake.nix`)
- [x] Add OpenOCD to Nix development environment if not present
- [x] Add arm-none-eabi-gdb (or gdb-multiarch) to Nix environment if not present
- [x] Test OpenOCD connection: `openocd -f board/stm32f469discovery.cfg`
- [x] Test GDB connection and verify can attach to target
- [x] Verify can halt CPU, read registers, and resume execution
- [x] Test reading flash memory at 0x08000000
- [x] Test reading RAM at 0x20000000
- [x] Document Nix flake setup in debugging guide (`docs/debugging.md`)

---

## Dev Notes

**Hardware Setup:**
- STM32F469 Discovery board has integrated ST-Link/V2-1 debugger
- Connection: Mini-USB port (CN1) for ST-Link
- No additional hardware required

**Nix Environment:**
- Current project uses `shell.nix` for reproducible builds
- May need to add: `openocd`, `gdb` (or `gdb-multiarch`)
- Check if already present in current configuration

**OpenOCD Configuration:**
- Standard board config: `board/stm32f469discovery.cfg`
- Should be available in OpenOCD's default config directory
- GDB server default port: 3333

**Memory Map:**
- Flash: 0x08000000 - 0x08200000 (2 MB)
- SRAM: 0x20000000 - 0x20060000 (384 KB)
- SDRAM: 0xC0000000 (16 MB external)

**References:**
- OpenOCD documentation: https://openocd.org/doc/
- STM32F469 Discovery board: https://www.st.com/en/evaluation-tools/32f469idiscovery.html
- Tech stack: `docs/architecture/tech-stack.md`

---

## Testing

### Manual Testing Steps

1. **Hardware Connection Test:**
   - Connect Mini-USB cable from PC to Discovery board CN1 port
   - Verify board powers on (LED should light)
   - Check `lsusb` output for ST-Link device

2. **OpenOCD Connection Test:**
   ```bash
   nix-shell
   openocd -f board/stm32f469discovery.cfg
   # Expected: "Info : stm32f4x.cpu: hardware has 6 breakpoints, 4 watchpoints"
   ```

3. **GDB Attachment Test:**
   ```bash
   # In separate terminal
   nix-shell
   arm-none-eabi-gdb
   (gdb) target extended-remote :3333
   (gdb) monitor reset halt
   (gdb) info registers
   (gdb) continue
   ```

4. **Memory Read Test:**
   ```bash
   (gdb) x/16xw 0x08000000  # Read 16 words from flash
   (gdb) x/16xw 0x20000000  # Read 16 words from RAM
   ```

### Success Indicators

- OpenOCD connects without errors
- GDB attaches successfully
- Can halt/resume CPU reliably
- Memory reads return valid data (not all 0xFF or 0x00)
- No connection timeouts or drops

---

## Dev Agent Record

### Agent Model Used
Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log
<!-- Dev agent will add references to debug log entries here -->

### Completion Notes

**Story completed successfully!** All acceptance criteria met.

**Key Achievements:**
- ✅ Created `flake.nix` with OpenOCD, GDB, and ARM toolchain
- ✅ Verified ST-Link/V2-1 debugger detection (VID:PID 0483:374B)
- ✅ Established OpenOCD connection (target voltage: 3.22V)
- ✅ Verified Cortex-M4 r0p1 processor detection
- ✅ Confirmed 6 breakpoints and 4 watchpoints available
- ✅ Successfully tested GDB remote debugging on port 3333
- ✅ Validated flash memory read at 0x08000000 (vector table confirmed)
- ✅ Validated RAM access at 0x20000000
- ✅ Created comprehensive debugging guide (docs/debugging.md)

**Tools Verified:**
- OpenOCD 0.12.0
- GDB 16.3
- gcc-arm-embedded (via Nix)

**Hardware Configuration:**
- ST-LINK V2J40M27 (API v2)
- STM32F469 Discovery board
- Dual USB connection (CN1 for ST-Link, CN13 for target power)

### File List

**New Files:**
- `flake.nix` - Nix flake configuration with debugging tools
- `flake.lock` - Nix flake lock file (auto-generated)
- `docs/debugging.md` - Comprehensive debugging guide
- `docs/firmware-dev/jtag-swd-debugging.md` - Practical step-by-step setup guide

**Modified Files:**
- `shell.nix` - Updated ARM toolchain version (note: flake.nix preferred going forward)

### Change Log

**2025-12-05 - Story Implementation**
- Created `flake.nix` with OpenOCD, GDB, gcc-arm-embedded, and Python 3
- Added GDB package to Nix environment (was missing)
- Verified hardware connection (ST-Link detected via lsusb)
- Tested OpenOCD connection to STM32F469 Discovery board
- Verified target voltage (3.22V) and processor detection (Cortex-M4 r0p1)
- Tested GDB remote connection on port 3333
- Verified CPU halt, register read, and resume functionality
- Tested flash memory read at 0x08000000 (vector table validated)
- Tested RAM read at 0x20000000 (memory accessible)
- Created comprehensive debugging documentation with:
  - Hardware setup instructions
  - Software setup via Nix flake
  - OpenOCD usage guide
  - GDB command reference
  - Memory map reference
  - Troubleshooting guide
  - Quick reference sections

---

**Story Status:** Ready for Review
**Created:** 2025-12-05
**Last Updated:** 2025-12-05
**Completed:** 2025-12-05
