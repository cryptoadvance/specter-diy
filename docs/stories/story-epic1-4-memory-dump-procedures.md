# Story: Create Memory Dump and Analysis Procedures

**Story ID:** EPIC1-STORY-4
**Epic:** Epic 1 - Establish Debugging Infrastructure
**Priority:** HIGH
**Estimated Effort:** 4-6 hours
**Status:** Draft

---

## Story

Develop procedures to dump flash memory, compare with expected binary layout, and analyze memory contents. This enables systematic verification of firmware flashing and identification of memory corruption issues.

This is a **brownfield enhancement** that adds memory analysis tools and procedures to the debugging workflow.

---

## Acceptance Criteria

- [ ] Can dump flash memory via GDB: `dump memory flash.bin 0x08000000 0x08200000`
- [ ] Can compare dumped memory with expected binary files
- [ ] Can verify vector table structure and values
- [ ] Can identify memory layout issues systematically
- [ ] Procedures documented with examples
- [ ] GDB scripts created for common memory dump operations
- [ ] Analysis checklist created for memory verification

---

## Tasks

- [ ] Create GDB script to dump entire flash region (0x08000000 - 0x08200000)
- [ ] Create GDB script to dump specific regions (bootloader, firmware, etc.)
- [ ] Create script to dump vector table and decode entries
- [ ] Document how to compare memory dump with binary files (hexdump, diff, cmp)
- [ ] Create checklist for memory verification:
  - [ ] Vector table at expected address
  - [ ] Stack pointer initialization value valid
  - [ ] Reset vector points to valid code
  - [ ] Firmware signature present (if applicable)
  - [ ] No unexpected 0x00 or 0xFF regions (partial flash)
- [ ] Create script to analyze vector table entries (validate addresses)
- [ ] Test procedures on current (broken) firmware
- [ ] Document findings and create analysis template
- [ ] Add memory map reference to debugging documentation

---

## Dev Notes

**STM32F469 Memory Map:**
```
Flash Memory:
  0x08000000 - 0x0801FFFF : Bootloader (128 KB, if secure boot enabled)
  0x08020000 - 0x081FFFFF : Firmware (~2 MB)

Internal SRAM:
  0x20000000 - 0x2005FFFF : SRAM (384 KB)

External SDRAM:
  0xC0000000 - 0xC0FFFFFF : SDRAM (16 MB)

Peripherals:
  0x40000000 - 0x5FFFFFFF : Peripheral registers
```

**Vector Table Structure (ARM Cortex-M4):**
```
Offset  | Content
--------|---------
0x0000  | Initial SP (stack pointer) - should point to RAM end
0x0004  | Reset vector - address of Reset_Handler
0x0008  | NMI_Handler
0x000C  | HardFault_Handler
...     | (more exception vectors)
```

**Memory Dump Procedures:**

1. **Full Flash Dump:**
```gdb
dump binary memory flash_full.bin 0x08000000 0x08200000
```

2. **Bootloader Region:**
```gdb
dump binary memory bootloader.bin 0x08000000 0x08020000
```

3. **Firmware Region:**
```gdb
dump binary memory firmware.bin 0x08020000 0x08200000
```

4. **Vector Table:**
```gdb
x/64xw 0x08000000  # Bootloader vector table
x/64xw 0x08020000  # Firmware vector table
```

**Comparison Methods:**

1. **Binary comparison:**
```bash
cmp flash_full.bin expected_firmware.bin
```

2. **Hexdump comparison:**
```bash
hexdump -C flash_full.bin > flash_dump.hex
hexdump -C expected_firmware.bin > expected.hex
diff flash_dump.hex expected.hex
```

3. **Vector table validation:**
```bash
# Extract first 64 bytes (16 vector entries)
xxd -l 64 flash_full.bin
# Verify:
# - SP value is in RAM range (0x2xxxxxxx or 0xCxxxxxxx)
# - Reset vector is in flash range (0x08xxxxxx)
# - Reset vector is odd (Thumb mode bit set)
```

**Common Issues to Check:**
- Partial flash: Sections of 0xFF (erased) or 0x00
- Wrong vector table: Reset vector not pointing to valid code
- Address misalignment: Firmware at wrong offset
- Bootloader corruption: Bootloader region modified unexpectedly

**GDB Script Example (`dump_flash.gdb`):**
```gdb
# Connect to target
target extended-remote :3333
monitor reset halt

# Dump flash regions
dump binary memory flash_full.bin 0x08000000 0x08200000
dump binary memory bootloader.bin 0x08000000 0x08020000
dump binary memory firmware.bin 0x08020000 0x08200000

# Display vector tables
echo \nBootloader Vector Table:\n
x/16xw 0x08000000

echo \nFirmware Vector Table:\n
x/16xw 0x08020000

# Display key addresses
echo \nBootloader SP:\n
x/xw 0x08000000

echo \nBootloader Reset Vector:\n
x/xw 0x08000004

echo \nFirmware SP:\n
x/xw 0x08020000

echo \nFirmware Reset Vector:\n
x/xw 0x08020004

quit
```

**Analysis Checklist Template:**
```markdown
## Memory Analysis Checklist

Date: ___________
Firmware Version: ___________
Board: STM32F469 Discovery

### Vector Table Analysis
- [ ] Bootloader SP (0x08000000): 0x________ (valid RAM address?)
- [ ] Bootloader Reset (0x08000004): 0x________ (valid flash address + 1?)
- [ ] Firmware SP (0x08020000): 0x________ (valid RAM address?)
- [ ] Firmware Reset (0x08020004): 0x________ (valid flash address + 1?)

### Flash Content Analysis
- [ ] Bootloader region (0x08000000-0x0801FFFF): No unexpected 0xFF or 0x00 regions
- [ ] Firmware region (0x08020000-0x081FFFFF): No unexpected 0xFF or 0x00 regions
- [ ] Binary comparison: Dumped firmware matches expected binary (Y/N)

### Findings
- Issue 1: ___________
- Issue 2: ___________

### Next Steps
- Action 1: ___________
- Action 2: ___________
```

**References:**
- ARM Cortex-M4 Technical Reference Manual
- STM32F469 Reference Manual (RM0386)
- GDB documentation: https://sourceware.org/gdb/documentation/
- Tech stack: `docs/architecture/tech-stack.md`

---

## Testing

### Manual Testing Steps

1. **GDB Script Test:**
   ```bash
   nix-shell
   # In one terminal: start OpenOCD
   openocd -f board/stm32f469discovery.cfg

   # In another terminal: run GDB script
   arm-none-eabi-gdb -x dump_flash.gdb
   ```

2. **Memory Dump Verification:**
   ```bash
   ls -lh *.bin  # Verify files created
   xxd -l 64 flash_full.bin  # Check vector table
   ```

3. **Vector Table Validation:**
   ```bash
   # Extract and validate SP
   xxd -l 4 -g 4 flash_full.bin
   # Should be 0x2xxxxxxx or 0xCxxxxxxx (RAM address)

   # Extract and validate Reset vector
   xxd -s 4 -l 4 -g 4 flash_full.bin
   # Should be 0x08xxxxxx and LSB = 1 (Thumb mode)
   ```

4. **Binary Comparison Test:**
   ```bash
   # Compare dumped firmware with expected binary
   cmp -l firmware.bin expected_firmware.bin
   # Or use hexdump diff for detailed comparison
   ```

5. **Analysis Checklist Test:**
   - Fill out checklist with real data
   - Verify checklist catches known issues
   - Refine checklist based on findings

### Success Indicators

- GDB scripts run without errors
- Memory dumps contain valid data
- Vector table entries are in valid ranges
- Can identify discrepancies between dumped and expected memory
- Analysis checklist is comprehensive and easy to follow
- Procedures work on both working and broken firmware

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
