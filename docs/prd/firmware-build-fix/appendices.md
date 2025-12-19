# Appendices

## A. Recent Commits Analysis

Key commits on `micropython-upgrade` branch:

```
705e962 Update f469-disco
64860ca Upgrade Docker container to Arm GNU Toolchain v14.3.rel1 and Python v3.9.23
b9f3813 Update build instructions: avoid conflicts with Homebrew's includes
b939993 Update Makefile for Micropython v1.25 (Specter adaptation)
3bbbbea Switch f469-disco to fork with upgraded MicroPython
```

**Analysis:**
- Docker toolchain upgraded ✅
- Build instructions updated for macOS ✅
- Root Makefile updated for v1.25 but apparently still broken
- f469-disco submodule switched to fork with MicroPython upgrade

---

## B. Build System File Tree

```
specter-diy/
├── Makefile                    # Root build orchestrator (BROKEN)
├── build_firmware.sh           # Full build script (BROKEN)
├── Dockerfile                  # Build container (UPDATED)
├── bin/                        # Build outputs
│   ├── specter-diy.bin        # Main firmware binary
│   └── specter-diy.hex        # Main firmware hex
├── bootloader/                # Secure bootloader
│   ├── Makefile               # Bootloader build (WORKS)
│   └── tools/
│       ├── make-initial-firmware.py
│       └── upgrade-generator.py
├── f469-disco/                # MicroPython port submodule
│   ├── Makefile               # Simplified build (UNKNOWN)
│   ├── micropython/           # MicroPython v1.25+
│   │   └── ports/
│   │       ├── stm32/         # STM32 port
│   │       │   ├── Makefile   # Main MicroPython build
│   │       │   ├── boards/STM32F469DISC/
│   │       │   └── mpconfigport_specter.h
│   │       └── unix/          # Simulator port
│   │           └── mpconfigport_specter.h
│   └── usermods/              # Custom C modules
│       ├── secp256k1/micropython.mk
│       ├── udisplay_f469/micropython.mk
│       ├── uhashlib/micropython.mk
│       ├── scard/micropython.mk
│       └── uebmit/micropython.mk
├── manifests/
│   ├── disco.py               # Frozen Python modules for disco
│   ├── unix.py                # Frozen Python modules for simulator
│   └── debug.py               # Debug manifest
└── src/                       # Python application (OUT OF SCOPE)
    └── apps/
```

---

## C. User C Modules

Critical modules that must compile:

1. **secp256k1** - Bitcoin elliptic curve crypto (from Bitcoin Core)
2. **udisplay_f469** - LVGL v9.3.0 display driver for STM32F469
3. **uhashlib** - Hash functions (SHA256, RIPEMD160, etc.)
4. **scard** - Smartcard/JavaCard integration
5. **uebmit** - Bitcoin miniscript support
6. **sdram** - External SDRAM support

---

## D. References

- **MicroPython v1.25 Release Notes:** [Check upstream MicroPython repo]
- **STM32 Port Documentation:** `f469-disco/micropython/ports/stm32/README.md`
- **Specter Bootloader:** `bootloader/doc/bootloader-spec.md`
- **Build Instructions:** `docs/build.md`
- **Existing Build Issues:** [Link to GitHub issues if any]

---
