# Known Issues & Investigations Needed

## Critical Unknowns

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

## Diagnostic Procedures to Develop

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

## Tools & Resources Needed

- **Hardware debugger:** ST-Link V2 or on-board ST-Link
- **OpenOCD config:** For STM32F469 Discovery
- **Serial adapter:** USB-to-UART if USB CDC doesn't work
- **Reference firmware:** Working v1.x build for comparison
- **Hex dump tools:** srec_cat, objdump, arm-none-eabi-readelf

---
