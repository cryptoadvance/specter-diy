# Definition of Done

The project is considered complete when ALL of the following criteria are met:

## Technical Completion

- [ ] **Firmware successfully flashes** - Flash process completes without breaking mid-way
- [ ] **Board boots successfully** - Device reaches MicroPython REPL prompt after flash
- [ ] **Basic Python execution works** - Can run simple Python commands from REPL
- [ ] **All user C modules load** - secp256k1, udisplay_f469, uhashlib, scard, uebmit, sdram all function correctly
- [ ] **Memory layout validated** - Vector table, stack pointer, and firmware address correct
- [ ] **Bootloader integration verified** - Bootloader successfully launches firmware after power cycle
- [ ] **No regressions** - All previously working functionality still works

## Documentation

- [ ] **Build process documented** - Updated docs/build.md with any new build steps
- [ ] **Debugging procedures documented** - OpenOCD setup, GDB commands, serial console access
- [ ] **Root cause analysis documented** - What was broken, why, and how it was fixed
- [ ] **Memory layout changes documented** - Any linker script or address changes explained
- [ ] **Lessons learned captured** - Known issues, gotchas, and troubleshooting tips

## Testing & Validation

- [ ] **Clean build from scratch** - Another developer can build firmware following updated docs
- [ ] **Reproducible flash process** - Flashing works consistently, not just once
- [ ] **Basic hardware wallet functions tested** - Display, buttons, and critical operations work
- [ ] **No build warnings** - Clean build output (or documented acceptable warnings)

## Integration

- [ ] **Changes committed** - All fixes committed to `micropython-upgrade` branch
- [ ] **Build system stable** - No breaking changes to build process
- [ ] **Ready for merge** - Branch ready to merge to `master` (pending full QA)

**Final Acceptance:** Project owner confirms firmware works on physical hardware and is ready for further development/testing.

---
