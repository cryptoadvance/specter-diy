# Architecture Decisions

## Decision 1: Makefile Structure

**Options:**
- A) Keep two Makefiles (root and f469-disco), root delegates to f469-disco
- B) Merge into single Makefile at root
- C) Use f469-disco/Makefile as primary, deprecate root Makefile

**Recommendation:** Option A (delegate) - Maintains separation of concerns

---

## Decision 2: Custom MicroPython Config

**Options:**
- A) Keep `CFLAGS_EXTRA='-DMP_CONFIGFILE="<mpconfigport_specter.h>"'` if it works
- B) Move config into board-specific mpconfigboard.h
- C) Create custom board variant in MicroPython boards/ directory

**Recommendation:** Option A if it still works, otherwise Option C

---

## Decision 3: Bootloader Memory Layout

**Options:**
- A) Keep `USE_DBOOT=1` if parameter still exists
- B) Create custom linker script in board definition
- C) Modify board mpconfigboard.mk to set linker script

**Recommendation:** Investigate first, then choose B or C

---
