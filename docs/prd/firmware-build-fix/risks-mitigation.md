# Risks & Mitigation

## High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cannot establish debugger connection | 🔴 CRITICAL | Test with multiple tools (OpenOCD, STM32CubeIDE); verify hardware connections |
| Flash corruption requires full board reflash | 🔴 CRITICAL | Keep backup bootloader; document recovery procedure |
| Memory layout fundamentally incompatible | 🔴 HIGH | May need custom linker script or bootloader modifications |
| Issue is hardware-specific (bad board) | 🔴 HIGH | Test with multiple STM32F469 Discovery boards if available |

## Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Takes many iterations to find root cause | 🟡 MEDIUM | Systematic debugging approach; document each test |
| Need to modify bootloader (out of scope) | 🟡 MEDIUM | Escalate if bootloader changes required; may need security review |
| Binary size exceeds flash after module additions | 🟡 MEDIUM | Profile size per module; may need to reduce frozen code |
| Debugging requires specialized equipment | 🟡 MEDIUM | Verify ST-Link availability; document DIY alternatives |

## Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Serial console doesn't work | 🟢 LOW | Use JTAG semihosting or LED codes instead |
| Some user modules don't work | 🟢 LOW | Fix incrementally; acceptable for MVP to skip non-critical modules |
| Documentation out of date | 🟢 LOW | Update docs as we fix issues |

---
