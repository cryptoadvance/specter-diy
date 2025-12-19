# Technical Requirements

## Must Have (MVP)

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

## Out of Scope (For This PRD)

- ❌ Python application code changes in `src/`
- ❌ Bootloader code changes
- ❌ Hardware support for other boards
- ❌ Simulator (`make unix`) fixes (can be Phase 2)
- ❌ Firmware functionality testing (separate testing PRD)

---
