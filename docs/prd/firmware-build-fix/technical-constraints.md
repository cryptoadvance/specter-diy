# Technical Constraints

## Hard Constraints

- **MicroPython version:** v1.25+ (already upgraded in f469-disco submodule)
- **Toolchain:** Arm GNU Toolchain v14.3.rel1 (already in Docker)
- **Board:** STM32F469 Discovery only (no other boards)
- **Bootloader:** Existing bootloader code should not be modified if possible. The bootloader is part of the security model and changing it requires careful review. However, if the bootloader is definitively proven to be the root cause AND firmware changes cannot fix the issue, then bootloader modifications may be considered as a last resort with appropriate security review.
- **Memory layout:** Must match bootloader expectations (firmware starts at specific address, typically 0x08020000 for `USE_DBOOT=1`)

## Soft Constraints

- **Build time:** Keep under 5 minutes in Docker
- **Binary size:** Keep under flash size limits (~2MB)
- **No Python 2:** Only Python 3.9+ for build tools
- **No breaking changes:** Don't break reproducible build process

---
