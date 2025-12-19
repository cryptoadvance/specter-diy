# Problem Statement

## Current State

The `micropython-upgrade` branch contains:
- ✅ **f469-disco submodule**: Successfully updated with MicroPython v1.25+ and LVGL v9.3.0
- ✅ **Docker container**: Upgraded to Arm GNU Toolchain v14.3.rel1 and Python v3.9.23
- ✅ **Build system**: Firmware compiles successfully and produces binaries
- ✅ **Bootloader**: Compiles successfully
- ❌ **Flashing process**: Breaks halfway through flashing firmware to board
- ❌ **Device boot**: Board fails to reboot successfully after flash attempt
- ❌ **Debugging infrastructure**: No established methods for on-board debugging yet

## Pain Points

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

## Impact

- **Cannot deploy upgraded firmware** to hardware
- **Cannot test** MicroPython v1.25 on actual board
- **Cannot validate** LVGL v9.3.0 display functionality
- **Blocking** entire upgrade branch from being merged
- **No feedback loop** - can't iterate on fixes without working debugging methods

---
