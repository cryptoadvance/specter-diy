# Current Architecture Understanding

## Build System Components (As-Is)

### 1. **Root Makefile** (`./Makefile`)
- Target: `make disco USE_DBOOT=1`
- Passes: `BOARD=STM32F469DISC`, `FLAVOR=SPECTER`, `USE_DBOOT=1`, `CFLAGS_EXTRA='-DMP_CONFIGFILE="<mpconfigport_specter.h>"'`
- Expects: `bin/specter-diy.bin` and `bin/specter-diy.hex` as outputs
- **Status:** ❌ BROKEN with new MicroPython

### 2. **f469-disco/Makefile** (`./f469-disco/Makefile`)
- Target: `make disco`
- Simpler approach: `BOARD=STM32F469DISC`, `USER_C_MODULES`, `FROZEN_MANIFEST`
- Does NOT use: `FLAVOR`, `USE_DBOOT`, or `CFLAGS_EXTRA`
- **Status:** ✅ May work independently

### 3. **Build Script** (`./build_firmware.sh`)
- Calls: `make disco USE_DBOOT=1` from root
- Then builds bootloader: `cd bootloader && make stm32f469disco`
- Assembles binaries with Python tools:
  - `make-initial-firmware.py` - Combines startup + bootloader + firmware
  - `upgrade-generator.py` - Creates signed upgrade binaries

### 4. **MicroPython Port** (`./f469-disco/micropython/ports/stm32/`)
- Board definition: `STM32F469DISC` in `boards/STM32F469DISC/`
- Custom config: `mpconfigport_specter.h` (two copies exist - stm32 and unix ports)
- User C modules: `f469-disco/usermods/` (secp256k1, udisplay_f469, uhashlib, etc.)

### 5. **Bootloader** (`./bootloader/`)
- Independent C project
- Builds: `startup.hex` and `bootloader.hex`
- Expects firmware at specific memory address
- **Dependency:** Final firmware must be built with `USE_DBOOT=1` for correct memory layout

## Key Files

| File | Purpose | Status |
|------|---------|--------|
| `Makefile` | Root build orchestration | ❌ BROKEN |
| `build_firmware.sh` | Full build + bootloader + signing | ❌ BROKEN |
| `f469-disco/Makefile` | MicroPython build wrapper | ⚠️ UNCLEAR |
| `f469-disco/micropython/ports/stm32/Makefile` | MicroPython STM32 port build | ✅ Should work |
| `f469-disco/micropython/ports/stm32/mpconfigport_specter.h` | Specter custom config | ✅ Exists |
| `bootloader/Makefile` | Bootloader build | ✅ Likely works |

## Changed Build Parameters (MicroPython v1.x → v1.25+)

Recent git commits show these key changes:
- `b939993` - "Update Makefile for Micropython v1.25 (Specter adaptation)"
- `3bbbbea` - "Switch f469-disco to fork with upgraded MicroPython"

**Hypothesis:** MicroPython v1.25+ may have:
- Removed or changed `FLAVOR` parameter handling
- Changed how `USE_DBOOT` affects memory layout
- Modified user C module integration mechanism
- Changed frozen manifest handling

---
