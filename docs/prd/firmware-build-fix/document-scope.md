# Document Scope

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
