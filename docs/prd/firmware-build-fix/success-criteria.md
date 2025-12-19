# Success Criteria

## Phase 1: Debugging Infrastructure

- [ ] JTAG/SWD connection established with OpenOCD or GDB
- [ ] Can attach debugger and halt/resume MCU
- [ ] Can read/write memory via debugger
- [ ] Serial console accessible (USB CDC or UART)
- [ ] LED diagnostic codes implemented for boot stages

## Phase 2: Minimal Firmware Boot

- [ ] Simple test firmware (no complex modules) compiles successfully
- [ ] Firmware flashes completely without breaking
- [ ] Board boots and reaches MicroPython REPL prompt
- [ ] Can execute Python commands via serial: `print("Hello")`
- [ ] LED blink test works from Python REPL

## Phase 3: Memory Layout Validation

- [ ] Vector table at correct address (verified via debugger)
- [ ] Firmware starts at 0x08020000 (bootloader integration)
- [ ] Stack pointer initialized correctly
- [ ] No memory overlap between bootloader and firmware
- [ ] Flash read-back matches what was written

## Phase 4: Bootloader Integration

- [ ] `initial_firmware.bin` structure validated (startup + bootloader + firmware)
- [ ] Bootloader successfully launches firmware
- [ ] Upgrade process works (if using signed firmware)
- [ ] Device survives power cycle and reboots correctly

## Phase 5: User Module Integration

- [ ] Add user C modules incrementally without breaking boot
- [ ] Each module tested: basic, uhashlib, udisplay, secp256k1, scard
- [ ] All modules load and function correctly
- [ ] Memory usage within acceptable limits

---
