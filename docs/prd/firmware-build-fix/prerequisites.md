# Prerequisites

Before starting this project, ensure the following are available:

## Hardware Requirements

- ✅ **STM32F469 Discovery board** (confirmed available)
- ✅ **ST-Link debugger**: The STM32F469 Discovery board has an integrated ST-Link/V2-1 debugger built-in (accessible via USB). No external debugger needed.
- **USB cables**:
  - Mini-USB for ST-Link debugger connection (integrated on board)
  - Micro-USB for USB CDC serial console (optional)
- **Serial adapter** (optional): USB-to-UART if USB CDC doesn't work

## Software Requirements

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

## Knowledge Requirements

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

## Access Requirements

- Repository write access to `micropython-upgrade` branch
- Physical access to STM32F469 Discovery board
- Ability to install debugging software on development machine (OpenOCD, GDB)

---
