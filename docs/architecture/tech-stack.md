# Technology Stack

This document describes the complete technology stack used in the Specter-DIY Bitcoin hardware wallet project.

## Table of Contents

- [Overview](#overview)
- [Hardware Platform](#hardware-platform)
- [Runtime Environment](#runtime-environment)
- [Core Libraries](#core-libraries)
- [Custom MicroPython Modules](#custom-micropython-modules)
- [Build System](#build-system)
- [Development Tools](#development-tools)
- [Testing Framework](#testing-framework)
- [Version Information](#version-information)

---

## Overview

Specter-DIY is built as a firmware application running on embedded hardware. The stack consists of:

- **Hardware:** STM32F469 Discovery board (ARM Cortex-M4)
- **Runtime:** MicroPython (Python 3.x on embedded systems)
- **GUI:** LVGL (Light and Versatile Graphics Library)
- **Crypto:** secp256k1 (Bitcoin Core's elliptic curve library)
- **Bootloader:** Custom secure bootloader with signature verification

**Architecture:** Mixed Python/C codebase
- Application logic: MicroPython (Python)
- Performance-critical code: C extensions
- Hardware drivers: C
- Bootloader: Pure C

---

## Hardware Platform

### STM32F469 Discovery Board

**Microcontroller:** STM32F469NIH6
- **Architecture:** ARM Cortex-M4 @ 180 MHz
- **Flash:** 2 MB internal flash
- **RAM:** 384 KB SRAM
- **External RAM:** 16 MB SDRAM (IS42S32400F-6BL)
- **FPU:** Single-precision FPU
- **DSP:** DSP instructions

**Display:**
- **Type:** 4" TFT LCD with capacitive touchscreen
- **Resolution:** 800x480 pixels
- **Controller:** OTM8009A

**Storage:**
- **Internal Flash:** Application firmware
- **QSPI Flash:** 16 MB external flash (N25Q128A13EF840E) for secure storage
- **SD Card:** Optional external storage

**Connectivity:**
- **USB:** Mini-USB and Micro-USB ports
- **Debug:** ST-Link/V2-1 debugger integrated
- **JTAG/SWD:** Debugging interface

**Other Features:**
- LEDs: User LEDs (LD1-LD4)
- Buttons: User button, Reset button
- Audio: I2S audio codec
- USB OTG: Full-speed device/host

**Board Documentation:**
- [STM32F469 Discovery Overview](https://www.st.com/en/evaluation-tools/32f469idiscovery.html)
- [Reference Manual RM0386](https://www.st.com/resource/en/reference_manual/rm0386-stm32f469xx-and-stm32f479xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)

---

## Runtime Environment

### MicroPython v1.25+

**What is MicroPython?**
MicroPython is a lean implementation of Python 3 optimized for microcontrollers and embedded systems.

**Key Features:**
- Python 3.x syntax (subset)
- Interactive REPL for debugging
- Bytecode compilation
- Garbage collection
- Hardware abstraction

**Specter Customizations:**
- Custom port configuration (`mpconfigport_specter.h`)
- Frozen modules (compiled into firmware)
- Extended with custom C modules
- Optimized for STM32F469 hardware

**MicroPython Port:**
- Base: `f469-disco/micropython` (submodule)
- Port: STM32 port (`ports/stm32`)
- Board: STM32F469DISC custom configuration
- Version: v1.25+ (recently upgraded from v1.x)

**Memory Management:**
- Heap allocated in SDRAM (16 MB available)
- Stack in internal SRAM
- Code in internal flash + QSPI flash

**Python Standard Library:**
- Core modules: `os`, `sys`, `gc`, `json`, `hashlib`
- MicroPython-specific: `machine`, `pyb`, `micropython`
- Limited subset due to memory constraints

---

## Core Libraries

### LVGL v9.3.0 (GUI Library)

**What is LVGL?**
Light and Versatile Graphics Library - a free, open-source graphics library for embedded systems.

**Features Used:**
- Rich UI components (buttons, labels, screens, keyboards)
- Touch input handling
- Animation and transitions
- Theme customization
- Efficient rendering for embedded displays

**Integration:**
- Custom MicroPython bindings: `f469-disco/usermods/udisplay_f469`
- Hardware-accelerated rendering via DMA2D
- Touchscreen integration (FT6x06 controller)
- Frame buffer in SDRAM

**Upgrade Notes:**
- Recently upgraded from LVGL v8.x to v9.3.0
- API changes require careful migration
- See: [LVGL v9 Migration Guide](https://docs.lvgl.io/master/CHANGELOG.html)

### secp256k1 (Bitcoin Cryptography)

**What is secp256k1?**
Bitcoin Core's highly optimized elliptic curve library for secp256k1 curve operations.

**Features:**
- ECDSA signature generation/verification
- Schnorr signatures
- Public key derivation
- Elliptic curve operations
- Constant-time implementations (side-channel resistant)

**Integration:**
- C library: `f469-disco/usermods/secp256k1/secp256k1`
- MicroPython bindings: `f469-disco/usermods/secp256k1`
- Context: Optimized for embedded ARM

**Security:**
- Constant-time operations
- Secure random number generation
- Memory cleared after use

**Upstream:**
- Source: [bitcoin-core/secp256k1](https://github.com/bitcoin-core/secp256k1)
- Embedded port maintained by project

### embit (Bitcoin Library)

**What is embit?**
A minimal Bitcoin library for embedded devices, written in Python.

**Features:**
- Bitcoin address generation (P2PKH, P2SH, P2WPKH, P2WSH, P2TR)
- Transaction parsing and signing
- PSBT (Partially Signed Bitcoin Transactions)
- BIP32 (HD wallets), BIP39 (mnemonics), BIP85
- Descriptor support
- Miniscript

**Integration:**
- Pure Python implementation
- Optimized for MicroPython
- Uses secp256k1 module for crypto operations

**Usage:**
- Transaction signing
- Address derivation
- Wallet management

---

## Custom MicroPython Modules

Specter-DIY extends MicroPython with custom C modules in `f469-disco/usermods/`:

### `secp256k1` - Elliptic Curve Cryptography

**Purpose:** Bitcoin cryptographic operations
**Language:** C with MicroPython bindings
**Dependencies:** libsecp256k1 from Bitcoin Core

**Functions:**
- Public key derivation
- ECDSA signing/verification
- Schnorr signatures

### `uhashlib` - Hash Functions

**Purpose:** Cryptographic hash functions
**Language:** C
**Dependencies:** MicroPython's hashlib

**Algorithms:**
- SHA-256, SHA-512
- RIPEMD-160
- Double SHA-256 (Bitcoin)

### `udisplay_f469` - Display Driver

**Purpose:** STM32F469 display and touch support
**Language:** C with LVGL integration
**Dependencies:** LVGL v9.3.0, STM32 HAL

**Features:**
- Frame buffer management
- Hardware-accelerated drawing (DMA2D)
- Capacitive touch input (FT6x06)
- Backlight control

### `sdram` - External RAM

**Purpose:** SDRAM memory management
**Language:** C
**Dependencies:** STM32 HAL

**Features:**
- 16 MB SDRAM initialization
- Memory allocation
- Used for heap and frame buffer

### `uebmit` - Bitcoin Transaction Parsing

**Purpose:** Efficient Bitcoin transaction parsing
**Language:** C
**Dependencies:** None

**Features:**
- Transaction deserialization
- PSBT parsing
- Optimized for embedded

### `scard` - Secure Element / Smart Card

**Purpose:** JavaCard / secure element communication
**Language:** C with MicroPython bindings
**Dependencies:** ISO7816 / APDU protocol

**Features:**
- Smart card communication
- JavaCard applet interaction
- Secure key storage (when using external secure element)

---

## Build System

### GNU Make

**Makefile Structure:**
- Root `Makefile`: Top-level build targets
- `f469-disco/micropython/ports/stm32/Makefile`: Firmware build
- `bootloader/Makefile`: Bootloader build

**Key Targets:**
```bash
make disco       # Build firmware for STM32F469 Discovery
make unix        # Build Unix simulator
make simulate    # Run simulator
make test        # Run tests
make clean       # Clean build artifacts
```

**Build Variables:**
- `BOARD`: Target board (default: STM32F469DISC)
- `FLAVOR`: Build flavor (default: SPECTER)
- `DEBUG`: Debug build (0 or 1)
- `USE_DBOOT`: Use secure bootloader (0 or 1)

### Nix Shell (Reproducible Builds)

**Purpose:** Reproducible development environment

**Dependencies Provided:**
- `gcc-arm-embedded-9`: ARM toolchain
- `python39`: Python 3.9
- `openocd`: On-chip debugger
- `stlink`: ST-Link tools
- `SDL2`: Simulator graphics

**Usage:**
```bash
nix-shell          # Enter development shell
make disco         # Build with Nix-provided tools
```

**Benefits:**
- Consistent toolchain versions
- No system dependency conflicts
- Reproducible builds

### Docker (Alternative Build Environment)

**Image:** Custom Dockerfile with all dependencies
**Toolchain:** Arm GNU Toolchain v14.3.rel1

**Usage:**
```bash
docker build -t specter-build .
docker run -v $(pwd):/build specter-build make disco
```

**Benefits:**
- Cross-platform builds (Linux, macOS, Windows)
- Isolated environment
- Matches CI/CD environment

### ARM Toolchain

**Compiler:** arm-none-eabi-gcc
**Version (Docker):** Arm GNU Toolchain v14.3.rel1
**Version (Nix):** gcc-arm-embedded-9

**Target:**
- Architecture: ARM Cortex-M4
- Float ABI: Hard float (hardware FPU)
- Instruction set: Thumb-2

---

## Development Tools

### OpenOCD (On-Chip Debugger)

**Purpose:** JTAG/SWD debugging interface
**Version:** Latest stable

**Configuration:**
- Target: STM32F469 Discovery
- Interface: ST-Link/V2-1
- Config: `board/stm32f469discovery.cfg`

**Usage:**
```bash
openocd -f board/stm32f469discovery.cfg
```

**Features:**
- Flash programming
- Memory read/write
- Breakpoints and watchpoints
- GDB server (port 3333)

### GDB (GNU Debugger)

**Variant:** arm-none-eabi-gdb (or gdb-multiarch)

**Usage:**
```bash
arm-none-eabi-gdb bin/specter-diy.elf
(gdb) target extended-remote :3333
(gdb) monitor reset halt
(gdb) load
(gdb) continue
```

**Features:**
- Source-level debugging
- Breakpoints
- Variable inspection
- Memory dumps

### Serial Console

**Purpose:** MicroPython REPL and debug output
**Interface:** USB CDC ACM (virtual COM port)
**Baud Rate:** 115200, 8N1

**Tools:**
- `screen`: `screen /dev/ttyACM0 115200`
- `minicom`: `minicom -D /dev/ttyACM0 -b 115200`
- `putty`: GUI serial terminal

**Usage:**
- Interactive Python REPL
- Debug prints
- Exception tracebacks

### ST-Link Utility

**Purpose:** Firmware flashing (alternative to OpenOCD)
**Platform:** Windows, macOS, Linux

**Features:**
- Flash erase
- Binary upload
- Option bytes configuration
- Read protection

---

## Testing Framework

### Unit Tests

**Framework:** MicroPython's built-in unittest
**Location:** `test/` directory

**Running Tests:**
```bash
make test    # Runs on Unix simulator
```

**Coverage:**
- Bitcoin address generation
- Transaction signing
- Keystore operations
- Utility functions

### Integration Tests

**Framework:** Custom test harness
**Location:** `test/integration/`

**Features:**
- GUI automation (via TCP simulator)
- End-to-end workflows
- QR code generation/parsing

**Requirements:**
- Unix simulator build
- Python 3.x on host

### Hardware Testing

**Manual Testing:**
- Physical device required
- Test plans in `docs/` directory
- Regression testing before releases

---

## Version Information

### Current Versions (as of 2025-12-05)

**Core Components:**
- **MicroPython:** v1.25+ (upgraded from v1.x)
- **LVGL:** v9.3.0 (upgraded from v8.x)
- **ARM Toolchain:** v14.3.rel1
- **Python (build host):** v3.9.23

**Hardware:**
- **Board:** STM32F469 Discovery
- **MCU:** STM32F469NIH6

**Bootloader:**
- **Version:** Custom secure bootloader
- **Repository:** [specter-bootloader](https://github.com/cryptoadvance/specter-bootloader)

**Upstream Submodules:**
- `f469-disco/micropython`: MicroPython port
- `bootloader/`: Secure bootloader
- `f469-disco/usermods/secp256k1/secp256k1`: Bitcoin Core secp256k1

### Upgrade Notes

**Recent Major Upgrades:**
1. **MicroPython v1.x → v1.25:**
   - API changes in threading, asyncio
   - Updated Python syntax support
   - See: [MicroPython CHANGELOG](https://github.com/micropython/micropython/blob/master/CHANGELOG.md)

2. **LVGL v8.x → v9.3.0:**
   - Breaking API changes (function renames, widget changes)
   - New theme system
   - See: [LVGL v9 Migration](https://docs.lvgl.io/master/CHANGELOG.html)

3. **ARM Toolchain Upgrade:**
   - Updated to v14.3.rel1 for better optimization
   - Smaller binary size
   - Improved debug info

**Compatibility:**
- Firmware is backwards-compatible with existing wallets
- Bootloader protocol unchanged
- Secure boot signatures remain valid

---

## External Dependencies

### Required for Building

**Host Tools:**
- `arm-none-eabi-gcc`: ARM cross-compiler
- `make`: Build system
- `python3`: Build scripts
- `git`: Version control and submodules

**Optional (but recommended):**
- `openocd`: Debugging
- `arm-none-eabi-gdb`: Debugger
- `SDL2`: Unix simulator graphics
- `nix`: Reproducible builds

### Runtime Dependencies (on device)

**None** - Firmware is self-contained:
- MicroPython runtime compiled in
- All libraries statically linked
- No external dependencies at runtime

---

## Security Considerations

### Trusted Components

**Critical for security:**
- **Bootloader:** Verifies firmware signatures
- **secp256k1:** Audited Bitcoin cryptography
- **Random Number Generator:** Hardware RNG (STM32)

**Threat Model:**
- Physical access assumed (hardware wallet)
- Side-channel attacks considered
- Supply chain attacks mitigated by reproducible builds

### Secure Boot Chain

1. **ROM bootloader** (STM32, read-only)
2. **Custom secure bootloader** (verifies firmware signature)
3. **Firmware** (signed by developers)

**Protection:**
- Flash read-out protection (RDP Level 2)
- Firmware signature verification
- Anti-rollback protection

---

## Additional Resources

**Documentation:**
- [MicroPython Documentation](https://docs.micropython.org/)
- [LVGL Documentation](https://docs.lvgl.io/)
- [STM32F469 Reference Manual](https://www.st.com/resource/en/reference_manual/rm0386-stm32f469xx-and-stm32f479xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
- [Bitcoin Core secp256k1](https://github.com/bitcoin-core/secp256k1)

**Development:**
- [Build Instructions](../build.md)
- [Development Guide](../development.md)
- [Reproducible Builds](../reproducible-build.md)

**Hardware:**
- [Shopping List](../shopping.md)
- [Assembly Instructions](../assembly.md)

---

**Last Updated:** 2025-12-05
**Maintainer:** Specter-DIY Core Team
