# Story: Implement LED Diagnostic Codes (Firmware Only)

**Story ID:** EPIC1-STORY-3
**Epic:** Epic 1 - Establish Debugging Infrastructure
**Priority:** HIGH
**Estimated Effort:** 6-8 hours
**Status:** Draft

---

## Story

Add LED diagnostic codes to firmware to visualize boot stages and identify where boot process fails. **MVP Scope: Firmware only - bootloader remains unmodified to preserve security model.**

This is a **brownfield enhancement** that adds visual diagnostics to the existing firmware without modifying the bootloader.

---

## Acceptance Criteria

- [ ] LEDs display distinct patterns for firmware boot stages
- [ ] Can visually identify where firmware boot process fails
- [ ] Bootloader code remains unmodified (preserves security model per `technical-constraints.md`)
- [ ] LED codes documented in debugging procedures
- [ ] Boot time overhead measured and verified <10ms
- [ ] Rationale for firmware-only scope documented
- [ ] LED diagnostic code can be disabled via compile flag for production builds

---

## Tasks

- [ ] Identify available LEDs on STM32F469 Discovery board (LD1-LD4)
- [ ] Review existing LED usage in firmware (if any)
- [ ] Design LED code scheme for firmware boot stages
  - [ ] LED pattern for firmware entry point reached
  - [ ] LED pattern for MicroPython initialization started
  - [ ] LED pattern for heap initialization
  - [ ] LED pattern for REPL ready
  - [ ] LED pattern for error conditions (hard fault, stack overflow)
- [ ] Implement LED control functions (set_led, blink_pattern, error_pattern)
- [ ] Add LED diagnostic calls to firmware boot sequence (`main.c` or equivalent)
- [ ] Add compile-time flag to enable/disable LED diagnostics (DEBUG_LEDS)
- [ ] Test LED codes by forcing different firmware boot stages
- [ ] Measure boot time before/after LED codes to verify performance impact <10ms
- [ ] Document LED code meanings in debugging guide
- [ ] Document bootloader scope decision and rationale

---

## Dev Notes

**Hardware - STM32F469 Discovery LEDs:**
- LD1 (Green): GPIO
- LD2 (Orange): GPIO
- LD3 (Red): GPIO
- LD4 (Blue): GPIO
- Location: Board documentation or schematic needed for exact GPIO pins

**LED Code Design Principles:**
- Simple patterns: Single LED, blink count, or LED combinations
- Non-blocking: LED code should not significantly delay boot
- Clear: Visually distinguishable patterns
- Minimal: Use only what's needed for debugging

**Proposed LED Code Scheme:**
```
LD1 (Green): Firmware entry point reached (solid on)
LD2 (Orange): MicroPython init started (blink 2x fast)
LD3 (Red): Error condition (rapid blink or SOS pattern)
LD4 (Blue): REPL ready (solid on)
```

**Firmware Boot Sequence (MicroPython STM32 port):**
1. Reset vector → `Reset_Handler` (startup.s)
2. `SystemInit()` - Clock, memory init
3. `main()` - MicroPython entry point
4. `mp_init()` - Initialize MicroPython runtime
5. `pyexec_friendly_repl()` - Start REPL

**LED Insertion Points:**
- After firmware entry: Top of `main()` in `ports/stm32/main.c`
- After MicroPython init: After `mp_init()` call
- Before REPL: Before `pyexec_friendly_repl()`
- Error handler: In `HardFault_Handler` or exception handlers

**Performance Considerations:**
- LED operations should be <1ms each
- Total overhead budget: <10ms for all LED diagnostics
- Use simple GPIO writes, no delays unless necessary
- Measure with timer or logic analyzer

**Bootloader Scope Decision:**
- **Not modifying bootloader** in MVP to preserve security model
- Bootloader signature verification is security-critical
- Any changes require re-signing and validation
- Future enhancement: Add bootloader LED codes after firmware is stable

**Compile Flag:**
```c
#ifndef DEBUG_LEDS
#define DEBUG_LEDS 1  // Enable by default for debugging builds
#endif

#if DEBUG_LEDS
    diagnostic_led_firmware_entry();
#endif
```

**References:**
- STM32F469 Discovery User Manual: UM1932
- MicroPython STM32 port: `f469-disco/micropython/ports/stm32/`
- Tech stack: `docs/architecture/tech-stack.md`
- Coding standards: `docs/architecture/coding-standards.md`

---

## Testing

### Manual Testing Steps

1. **LED Hardware Test:**
   ```bash
   # Verify all LEDs work
   # Build test firmware that cycles through all LEDs
   make disco DEBUG_LEDS=1
   # Flash and observe LED sequence
   ```

2. **Boot Stage Visualization Test:**
   - Flash firmware with LED diagnostics enabled
   - Power on board, observe LED sequence
   - Compare against documented LED code scheme
   - Note where sequence stops if firmware fails to boot

3. **Error Condition Test:**
   - Intentionally corrupt firmware (e.g., modify vector table)
   - Flash and power on
   - Verify error LED pattern appears
   - Document which LED pattern indicates failure mode

4. **Performance Test:**
   ```c
   // Add timing code
   uint32_t start = DWT->CYCCNT;
   diagnostic_led_firmware_entry();
   uint32_t end = DWT->CYCCNT;
   uint32_t cycles = end - start;
   uint32_t microseconds = cycles / (SystemCoreClock / 1000000);
   // Verify microseconds < 10000 (10ms)
   ```

5. **Production Build Test:**
   ```bash
   make disco DEBUG_LEDS=0
   # Verify LED diagnostic code is excluded from build
   # Check binary size difference
   ```

### Success Indicators

- All 4 LEDs controllable independently
- LED patterns clearly visible and distinguishable
- Boot sequence visualization helps identify failure point
- Boot time overhead measured <10ms
- Can disable LED diagnostics for production
- Documentation clearly explains each LED pattern meaning

---

## Dev Agent Record

### Agent Model Used
<!-- Dev agent will fill this in -->

### Debug Log
<!-- Dev agent will add references to debug log entries here -->

### Completion Notes
<!-- Dev agent will add completion notes here -->

### File List
<!-- Dev agent will list all new or modified files here -->

### Change Log
<!-- Dev agent will track changes here -->

---

**Story Status:** Draft
**Created:** 2025-12-05
**Last Updated:** 2025-12-05
