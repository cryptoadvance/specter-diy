# Source Tree Structure

This document provides a comprehensive overview of the Specter-DIY source code organization.

## Table of Contents

- [Overview](#overview)
- [Root Directory](#root-directory)
- [Application Source (`src/`)](#application-source-src)
- [STM32F469 Port (`f469-disco/`)](#stm32f469-port-f469-disco)
- [Bootloader (`bootloader/`)](#bootloader-bootloader)
- [Documentation (`docs/`)](#documentation-docs)
- [Build Artifacts (`bin/`)](#build-artifacts-bin)
- [Configuration Files](#configuration-files)
- [Navigation Guide](#navigation-guide)

---

## Overview

Specter-DIY follows a modular architecture with clear separation of concerns:

```
specter-diy/
├── src/              # MicroPython application code (main wallet logic)
├── f469-disco/       # STM32F469 port (MicroPython + custom modules)
├── bootloader/       # Secure bootloader (C code)
├── docs/             # Documentation
├── test/             # Test suite
├── boot/             # Boot scripts
├── shield/           # Hardware shield designs
└── [build files]     # Makefile, Dockerfile, etc.
```

**Key Principles:**
- **Separation:** Application logic (`src/`) separate from hardware (`f469-disco/`)
- **Modularity:** Apps, GUI, keystore, hosts are separate modules
- **Portability:** Application code is hardware-agnostic (uses `platform.py` abstraction)

---

## Root Directory

```
specter-diy/
├── Makefile              # Main build system
├── Dockerfile            # Docker build environment
├── shell.nix             # Nix shell for reproducible builds
├── README.md             # Project overview
├── LICENSE               # MIT license
├── requirements.txt      # Python dependencies (for host tools)
├── .gitignore            # Git ignore patterns
├── .gitmodules           # Git submodules configuration
├── mkdocs.yml            # Documentation site configuration
├── build_firmware.sh     # Build script (Docker-based)
├── simulate.py           # Simulator entry point
├── hwidevice.py          # HWI (Hardware Wallet Interface) integration
└── [directories...]      # See sections below
```

### Key Files

**`Makefile`**
- Top-level build orchestration
- Targets: `disco` (firmware), `unix` (simulator), `test`, `clean`
- Delegates to MicroPython Makefiles

**`simulate.py`**
- Simulator entry point for Unix build
- Runs wallet application in desktop environment
- Used for development and testing

**`hwidevice.py`**
- Integration with Bitcoin HWI (Hardware Wallet Interface)
- Allows Specter-DIY to work with Bitcoin Core and other software

**`shell.nix`**
- Nix development environment
- Provides: gcc-arm-embedded, python, openocd, SDL2

**`Dockerfile`**
- Reproducible build environment
- ARM GNU Toolchain v14.3.rel1
- All dependencies included

---

## Application Source (`src/`)

**Purpose:** Core wallet application logic (MicroPython/Python)

```
src/
├── main.py                 # Application entry point
├── specter.py              # Main Specter class (wallet controller)
├── platform.py             # Hardware abstraction layer
├── app.py                  # Base application class
├── helpers.py              # Utility functions
├── errors.py               # Custom exceptions
├── rng.py                  # Random number generation
├── qrencoder.py            # QR code encoding
├── config_default.py       # Default configuration
├── apps/                   # Wallet applications
├── gui/                    # GUI components and screens
├── hosts/                  # Communication protocols
└── keystore/               # Key storage backends
```

### Entry Point: `main.py`

**What it does:**
1. Initializes display (and SDRAM)
2. Mounts SDRAM as virtual filesystem
3. Sets up hosts (USB, QR, SD card)
4. Initializes GUI
5. Detects keystore (MemoryCard, SD card, etc.)
6. Loads apps
7. Starts Specter instance

**Key function:**
```python
def main(apps=None, network="main", keystore_cls=None):
    # Initialize hardware
    display.init(False)
    rampath = platform.mount_sdram()

    # Create hosts
    hosts = [USBHost(...), QRHost(...), SDHost(...)]

    # Create GUI
    gui = SpecterGUI()

    # Start wallet
    specter = Specter(gui, keystores, hosts, apps, ...)
    specter.start()
```

### Core Modules

**`specter.py`** - Main wallet controller
- Manages application lifecycle
- Coordinates between GUI, keystore, hosts
- Handles network configuration (mainnet, testnet, etc.)
- Settings persistence

**`platform.py`** - Hardware abstraction
- Provides platform-independent file paths
- Handles differences between real hardware and simulator
- Memory management (SDRAM, QSPI flash)
- Example: `platform.fpath("/flash/keystore")` → actual path

**`app.py`** - Base application class
- All wallet apps inherit from `BaseApp`
- Defines app lifecycle (init, process_request, show)
- Manages temporary storage

### Applications (`src/apps/`)

```
src/apps/
├── __init__.py             # App loader
├── wallets/                # Wallet management
│   ├── app.py              # WalletApp (main wallet app)
│   ├── wallet.py           # Wallet class
│   ├── manager.py          # WalletManager
│   ├── commands.py         # Wallet commands
│   ├── screens.py          # Wallet UI screens
│   └── liquid/             # Liquid network support
├── xpubs/                  # Master public key export
│   ├── xpubs.py            # XpubApp
│   └── screens.py          # Xpub UI screens
├── signmessage/            # Bitcoin message signing
│   ├── signmessage.py      # SignMessageApp
│   └── __init__.py
├── blindingkeys/           # Liquid blinding keys
│   ├── app.py              # BlindingKeysApp
│   └── __init__.py
├── backup.py               # Wallet backup
├── bip85.py                # BIP85 derived entropy
├── compatibility.py        # Legacy wallet compatibility
├── getrandom.py            # Random number generator app
└── label.py                # Wallet labeling
```

**App Structure:**
Each app is a self-contained module that:
- Inherits from `BaseApp`
- Implements `process_request()` for host commands
- Provides UI screens
- Manages its own state

**Example: WalletApp**
- Manages Bitcoin wallets (single-sig and multisig)
- Creates/imports wallets
- Signs PSBTs (Partially Signed Bitcoin Transactions)
- Exports wallet descriptors

### GUI (`src/gui/`)

```
src/gui/
├── __init__.py             # GUI module initialization
├── core.py                 # Core GUI classes
├── specter.py              # SpecterGUI (main GUI controller)
├── async_gui.py            # Async GUI helpers
├── tcp_gui.py              # TCP-based GUI (for simulator testing)
├── decorators.py           # GUI decorators (e.g., @on_release)
├── common.py               # Common GUI utilities
├── components/             # Reusable GUI components
│   ├── __init__.py
│   ├── theme.py            # LVGL theme customization
│   ├── keyboard.py         # On-screen keyboard
│   ├── qrcode.py           # QR code display component
│   ├── modal.py            # Modal dialogs
│   ├── mnemonic.py         # BIP39 mnemonic input
│   └── battery.py          # Battery indicator (if applicable)
└── screens/                # GUI screens
    ├── __init__.py
    ├── screen.py           # Base Screen class
    ├── menu.py             # Menu screen
    ├── alert.py            # Alert/notification screen
    ├── qralert.py          # QR code alert
    ├── prompt.py           # User prompt screen
    ├── input.py            # Text input screen
    ├── progress.py         # Progress indicator
    ├── mnemonic.py         # Mnemonic display/input
    ├── transaction.py      # Transaction display
    └── settings.py         # Settings screen
```

**GUI Architecture:**
- **LVGL-based:** Uses LVGL v9.3.0 for rendering
- **Component model:** Reusable components (keyboard, QR code, etc.)
- **Screen stack:** Screens pushed/popped like a navigation stack
- **Event-driven:** Touch events, button callbacks

**Key Classes:**
- `SpecterGUI`: Main GUI controller
- `Screen`: Base class for all screens
- `HorizontalMenu`: Menu navigation

### Hosts (`src/hosts/`)

```
src/hosts/
├── __init__.py             # Host module exports
├── core.py                 # BaseHost class
├── qr.py                   # QRHost (QR code communication)
├── usb.py                  # USBHost (USB communication)
└── sd.py                   # SDHost (SD card communication)
```

**Host Protocol:**
Hosts provide communication channels between Specter and external software:
- **QRHost:** Airgapped communication via QR codes
- **USBHost:** USB connection (HWI protocol)
- **SDHost:** SD card file exchange

**Flow:**
1. Host receives request (QR scan, USB message, SD file)
2. Request routed to appropriate app
3. App processes and returns response
4. Host sends response (QR display, USB reply, SD file write)

### Keystore (`src/keystore/`)

```
src/keystore/
├── __init__.py             # Keystore exports
├── core.py                 # KeyStore base class
├── ram.py                  # RAMKeyStore (agnostic mode - keys in RAM)
├── flash.py                # FlashKeyStore (reckless mode - keys in flash)
├── sdcard.py               # SDKeyStore (keys on SD card)
├── memorycard.py           # MemoryCard (smartcard storage)
└── javacard/               # JavaCard applet support
    ├── __init__.py
    ├── util.py             # JavaCard utilities
    └── applets/            # JavaCard applet implementations
        ├── __init__.py
        ├── applet.py       # Base applet class
        ├── memorycard.py   # Memory card applet
        ├── secureapplet.py # Secure applet
        ├── securechannel.py # Secure channel protocol
        └── blindoracle.py  # Blind oracle applet
```

**Keystore Backends:**
- **RAMKeyStore:** Keys stored in RAM (forgotten on power-off) - agnostic mode
- **FlashKeyStore:** Keys in internal flash (persistent) - reckless mode
- **SDKeyStore:** Keys on SD card (removable)
- **MemoryCard:** JavaCard/smartcard (secure element)

**Security Model:**
- Agnostic mode (RAM): Max security, inconvenient
- Reckless mode (Flash): Convenient, less secure
- SD card: Removable, moderate security
- Secure element: Best security, requires hardware

---

## STM32F469 Port (`f469-disco/`)

**Purpose:** MicroPython port and hardware-specific code

```
f469-disco/
├── micropython/            # MicroPython submodule (v1.25+)
├── usermods/               # Custom MicroPython C modules
├── libs/                   # Additional libraries (LVGL, etc.)
├── docs/                   # Hardware-specific documentation
├── examples/               # Example code
├── tests/                  # Hardware tests
├── debug/                  # Debugging configurations
├── manifests/              # Frozen module manifests
├── Makefile                # Build configuration
└── shell.nix               # Nix shell
```

### MicroPython Submodule (`micropython/`)

```
f469-disco/micropython/
├── py/                     # Python runtime core
├── lib/                    # Third-party libraries
├── extmod/                 # Extended modules
├── ports/                  # Platform ports
│   ├── stm32/              # STM32 port (our target)
│   │   ├── boards/         # Board definitions
│   │   │   └── STM32F469DISC/  # Our board config
│   │   ├── Makefile
│   │   └── [STM32 HAL, drivers, etc.]
│   └── unix/               # Unix simulator port
├── mpy-cross/              # MicroPython cross-compiler
├── tools/                  # Build tools (codeformat.py, etc.)
└── [documentation, tests, etc.]
```

**Key Files for STM32F469DISC:**
- `ports/stm32/boards/STM32F469DISC/`: Board configuration
  - `mpconfigboard.h`: Board-specific config
  - `mpconfigboard.mk`: Build variables
  - `pins.csv`: GPIO pin definitions
  - `stm32f4xx_hal_conf.h`: STM32 HAL configuration

**Custom Config:**
- `mpconfigport_specter.h`: Specter-specific MicroPython config
- Enables custom modules
- Memory limits
- Feature flags

### Custom Modules (`usermods/`)

```
f469-disco/usermods/
├── secp256k1/              # Bitcoin cryptography
│   ├── secp256k1/          # libsecp256k1 (submodule)
│   ├── modsecp256k1.c      # MicroPython bindings
│   └── micropython.mk      # Build config
├── uhashlib/               # Hash functions (SHA256, RIPEMD160)
│   ├── modhashlib.c
│   └── micropython.mk
├── udisplay_f469/          # Display and touch driver
│   ├── moddisplay.c        # Display module
│   ├── lvgl/               # LVGL library (v9.3.0)
│   ├── ft6x06/             # Touch controller driver
│   └── micropython.mk
├── sdram/                  # SDRAM driver
│   ├── modsdram.c
│   └── micropython.mk
├── uebmit/                 # Efficient Bitcoin transaction parsing
│   ├── modebmit.c
│   └── micropython.mk
└── scard/                  # Smart card / JavaCard communication
    ├── modscard.c
    └── micropython.mk
```

**Module Structure:**
Each module contains:
- C source files (`mod*.c`)
- `micropython.mk`: Build configuration
- Optional: External libraries (submodules)

**Integration:**
- Modules specified via `USER_C_MODULES` in Makefile
- Compiled into firmware
- Accessible from Python: `import secp256k1`

### LVGL Integration (`udisplay_f469/lvgl/`)

```
udisplay_f469/lvgl/
├── lvgl/                   # LVGL library (v9.3.0 submodule)
├── lv_conf.h               # LVGL configuration
├── lv_drivers/             # Display drivers
└── [MicroPython bindings]
```

**LVGL Configuration:**
- Hardware acceleration via DMA2D
- Frame buffer in SDRAM
- Touchscreen support (FT6x06)
- Custom theme for Specter

---

## Bootloader (`bootloader/`)

**Purpose:** Secure bootloader with firmware signature verification

```
bootloader/
├── core/                   # Bootloader core logic
│   ├── main.c              # Bootloader entry point
│   ├── verify.c            # Signature verification
│   ├── flash.c             # Flash memory operations
│   └── [other core files]
├── platforms/              # Platform-specific code
│   └── stm32f469disco/     # STM32F469 platform
│       ├── startup.s       # Startup assembly
│       ├── system.c        # System initialization
│       ├── drivers/        # HAL drivers
│       └── linker.ld       # Linker script
├── lib/                    # Libraries
│   ├── secp256k1/          # Signature verification
│   └── fatfs/              # FAT filesystem (for SD card updates)
├── keys/                   # Public keys for signature verification
├── tools/                  # Signing tools
├── doc/                    # Bootloader documentation
├── Makefile
└── README.md
```

**Bootloader Flow:**
1. Power-on / Reset
2. Bootloader starts (first in flash)
3. Check for firmware update (SD card)
4. Verify firmware signature
5. If valid: Flash new firmware
6. Boot into firmware

**Security:**
- Firmware must be signed with developer key
- Public key embedded in bootloader
- Signature verification before flash
- Anti-rollback protection
- Read-out protection (RDP Level 2)

**Documentation:**
- `doc/bootloader-spec.md`: Specification
- `doc/selfsigned.md`: How to sign your own firmware
- `doc/remove_protection.md`: Remove flash protection

---

## Documentation (`docs/`)

```
docs/
├── README.md               # Documentation index
├── shopping.md             # Hardware shopping list
├── assembly.md             # Hardware assembly guide
├── quickstart.md           # Quick start guide
├── build.md                # Build instructions
├── reproducible-build.md   # Reproducible builds
├── development.md          # Development guide
├── simulator.md            # Simulator usage
├── security.md             # Security model
├── communication.md        # Communication protocols
├── roadmap.md              # Project roadmap
├── faq.md                  # Frequently asked questions
├── architecture/           # Architecture documentation
│   ├── coding-standards.md # This project's coding standards
│   ├── tech-stack.md       # Technology stack
│   └── source-tree.md      # This document
├── prd/                    # Product Requirements Documents
│   └── firmware-build-fix/ # Current firmware fix project
│       ├── epics/          # Epic-level documentation
│       └── [other PRD files]
├── pictures/               # Screenshots and images
└── enclosures/             # 3D printable enclosures
```

**Key Documents:**
- **For Users:**
  - `quickstart.md`: Get started quickly
  - `shopping.md`: What to buy
  - `assembly.md`: How to build
  - `security.md`: Security model

- **For Developers:**
  - `build.md`: How to compile
  - `development.md`: Development workflow
  - `simulator.md`: Using the simulator
  - `architecture/`: Architecture documentation

---

## Build Artifacts (`bin/`)

**Not in git** (generated by build process)

```
bin/
├── specter-diy.bin         # Firmware binary (for flashing)
├── specter-diy.hex         # Firmware hex file
├── debug.bin               # Debug build
├── micropython_unix        # Unix simulator executable
└── mpy-cross               # MicroPython cross-compiler
```

**Generated by:**
- `make disco`: Creates `specter-diy.bin`
- `make unix`: Creates `micropython_unix`
- `make mpy-cross`: Creates `mpy-cross`

---

## Configuration Files

### Root Level

**`Makefile`**
- Build orchestration
- Targets: disco, unix, simulate, test, clean

**`Dockerfile`**
- Docker build environment
- ARM GNU Toolchain v14.3.rel1

**`shell.nix`**
- Nix development shell
- Reproducible dependencies

**`.gitignore`**
- Ignores: `bin/`, `build/`, `*.pyc`, etc.

**`.gitmodules`**
- Submodules: `f469-disco/micropython`, `bootloader`, etc.

**`mkdocs.yml`**
- Documentation site configuration
- Uses MkDocs for docs rendering

### MicroPython Config

**`f469-disco/micropython/ports/stm32/boards/STM32F469DISC/mpconfigboard.h`**
- Board-level MicroPython configuration
- Memory layout
- Peripheral configuration

**Custom: `mpconfigport_specter.h`**
- Specter-specific overrides
- Feature flags
- Module enables

### Build Config

**`f469-disco/manifests/disco.py`**
- Frozen modules manifest
- Specifies which Python modules to compile into firmware
- Reduces RAM usage (code in flash, not RAM)

---

## Navigation Guide

### "I want to..."

**...understand the wallet logic**
→ Start: `src/main.py`, `src/specter.py`, `src/apps/wallets/`

**...modify the GUI**
→ Start: `src/gui/`, especially `src/gui/screens/` and `src/gui/components/`

**...add a new communication method**
→ Start: `src/hosts/`, look at `qr.py` or `usb.py` as examples

**...change how keys are stored**
→ Start: `src/keystore/`, look at existing keystores

**...add Bitcoin functionality**
→ Start: `src/apps/wallets/wallet.py`, uses `embit` library

**...work on the bootloader**
→ Start: `bootloader/README.md`, `bootloader/core/`

**...add a custom C module**
→ Start: `f469-disco/usermods/`, look at `secp256k1/` as example

**...modify display or touch handling**
→ Start: `f469-disco/usermods/udisplay_f469/`

**...debug the firmware**
→ Start: `f469-disco/debug/vscode.md` (VS Code config)

**...run tests**
→ Start: `test/` directory, run `make test`

**...build the firmware**
→ Start: `docs/build.md`, then run `make disco`

**...run the simulator**
→ Start: `docs/simulator.md`, then run `make simulate`

### File Naming Patterns

**Python:**
- `*.py`: Python source files
- `__init__.py`: Module initialization (makes directory a Python package)

**C:**
- `mod*.c`: MicroPython C modules (e.g., `modsecp256k1.c`)
- `*.h`: C header files
- `micropython.mk`: MicroPython module build config

**Build:**
- `Makefile`: Build configuration
- `*.ld`: Linker scripts (memory layout)
- `*.cfg`: OpenOCD configuration

**Documentation:**
- `*.md`: Markdown documentation
- `README.md`: Directory/project overview

---

## Import Paths

### Python Imports in Application Code

```python
# Absolute imports from src/
from keystore import KeyStore           # src/keystore/__init__.py
from gui.specter import SpecterGUI     # src/gui/specter.py
from apps.wallets import WalletApp     # src/apps/wallets/__init__.py

# Platform modules (C extensions)
import display                          # f469-disco/usermods/udisplay_f469
import secp256k1                        # f469-disco/usermods/secp256k1

# MicroPython builtins
import sys, os, gc                      # MicroPython standard library
```

### Frozen Modules

Modules specified in manifests are "frozen" (compiled into firmware):
- Located: `manifests/disco.py`
- All of `src/` is frozen for performance and memory
- Benefits: No RAM used for bytecode, faster startup

---

## Memory Layout

### Flash Memory

```
0x08000000 ┌─────────────────────┐
           │ Bootloader          │ (if secure boot enabled)
0x08020000 ├─────────────────────┤
           │ Firmware            │ (MicroPython + frozen modules)
           │                     │
0x08200000 └─────────────────────┘

QSPI Flash ┌─────────────────────┐
           │ Persistent Storage  │ (keystores, settings)
           │ (16 MB)             │
           └─────────────────────┘
```

### RAM Layout

```
0x20000000 ┌─────────────────────┐
           │ Internal SRAM       │ (384 KB)
           │ - Stack             │
           │ - Globals           │
           │ - Static alloc      │
0xC0000000 ├─────────────────────┤
           │ SDRAM               │ (16 MB)
           │ - Python heap       │
           │ - Frame buffer      │
           │ - Temp storage      │
           └─────────────────────┘
```

---

## Dependency Graph

**High-Level Dependencies:**

```
Applications (src/apps/)
    ↓
GUI (src/gui/) ← → Platform (src/platform.py)
    ↓                    ↓
LVGL (C module)    Keystore (src/keystore/)
    ↓                    ↓
MicroPython        secp256k1 (C module)
    ↓                    ↓
STM32 HAL          Bitcoin libraries (embit)
    ↓
Hardware (STM32F469)
```

**Build Dependencies:**

```
Source Code (src/, f469-disco/)
    ↓
MicroPython Cross-Compiler (mpy-cross)
    ↓
ARM GCC Toolchain (arm-none-eabi-gcc)
    ↓
Firmware Binary (specter-diy.bin)
    ↓
Bootloader (optional, for secure boot)
    ↓
Flash to Device
```

---

## Additional Notes

### Submodules

**Git submodules in this project:**
- `f469-disco/micropython`: MicroPython upstream
- `bootloader/`: Secure bootloader (separate repo)
- `f469-disco/usermods/secp256k1/secp256k1`: Bitcoin Core secp256k1
- Various LVGL, CMSIS, HAL libraries

**Update submodules:**
```bash
git submodule update --init --recursive
```

### Platform Abstraction

**Key insight:** Application code (`src/`) should never directly access hardware.

**Instead:**
- Use `platform.py` for filesystem paths
- Use `display` module for screen/touch
- Use `machine` / `pyb` modules sparingly

**Benefits:**
- Same code runs on hardware and simulator
- Easy to port to different hardware
- Testable on desktop

### Frozen Modules

**Why freeze modules?**
- MicroPython compiles Python to bytecode at runtime
- Bytecode consumes RAM
- Freezing: Pre-compile bytecode, store in flash
- Result: More RAM available, faster startup

**How to freeze:**
- Add to manifest: `manifests/disco.py`
- Run `make disco` (automatically freezes)

---

## Quick Reference

### Common Paths

| Purpose | Path |
|---------|------|
| Main entry point | `src/main.py` |
| Wallet logic | `src/apps/wallets/` |
| GUI screens | `src/gui/screens/` |
| Keystore backends | `src/keystore/` |
| MicroPython port | `f469-disco/micropython/ports/stm32/` |
| Custom C modules | `f469-disco/usermods/` |
| Bootloader | `bootloader/core/` |
| Build output | `bin/` |
| Documentation | `docs/` |

### File Extensions

| Extension | Meaning |
|-----------|---------|
| `.py` | Python source |
| `.c`, `.h` | C source/header |
| `.s`, `.S` | Assembly |
| `.ld` | Linker script |
| `.mk` | Makefile include |
| `.md` | Markdown documentation |
| `.bin` | Binary firmware image |
| `.hex` | Intel HEX firmware image |
| `.elf` | ELF executable (debug symbols) |

---

## For New Developers

**Recommended Reading Order:**
1. This document (source-tree.md) - Overview of codebase
2. `docs/build.md` - How to build
3. `docs/development.md` - Development workflow
4. `docs/simulator.md` - Run simulator for testing
5. `src/main.py` - Understand application startup
6. `src/apps/wallets/` - Wallet logic
7. Architecture documents - Deep dives

**First Contribution:**
1. Fork repository
2. Set up development environment (`nix-shell` or Docker)
3. Build simulator: `make unix`
4. Run simulator: `make simulate`
5. Make small change (fix typo, add comment)
6. Test: `make test`
7. Commit with proper message (see `docs/architecture/coding-standards.md`)
8. Submit PR

---

**Last Updated:** 2025-12-05
**Maintainer:** Specter-DIY Core Team
