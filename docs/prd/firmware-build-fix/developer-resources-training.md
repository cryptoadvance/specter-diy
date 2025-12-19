# Developer Resources & Training

If the assigned developer lacks experience with ARM Cortex-M debugging or STM32 development, the following resources will help build the necessary knowledge.

## Critical Reading (Start Here)

**ARM Cortex-M Fundamentals:**
1. **ARM Cortex-M4 Technical Reference Manual** - Understanding the CPU architecture
   - Focus on: Exception model, vector table, memory map, debugging architecture
   - Available: ARM official documentation website

2. **STM32F469 Reference Manual (RM0386)** - Microcontroller specifics
   - Focus on: Memory organization, Flash interface, boot modes, debug access
   - Available: STMicroelectronics website

3. **The Definitive Guide to ARM Cortex-M3 and Cortex-M4 Processors** by Joseph Yiu
   - Comprehensive book covering architecture, debugging, and development
   - Chapters 1-5, 13-14 are most relevant

**Debugging Tools:**
4. **OpenOCD User's Guide** - Understanding JTAG/SWD debugging
   - Focus on: STM32 target configuration, GDB integration, flash programming
   - Available: openocd.org/doc

5. **GDB Debugging Cheat Sheet** - Essential GDB commands for embedded systems
   - Commands: info registers, x/memory, break, step, continue, monitor commands
   - Available: Many online tutorials and quick references

**Linker Scripts & Memory Layout:**
6. **GNU LD Linker Script Guide** - Understanding linker scripts
   - Focus on: MEMORY regions, SECTIONS, symbol definitions, load vs runtime addresses
   - Available: GNU binutils documentation

## STM32-Specific Resources

**STM32F469 Discovery Board:**
- **User Manual (UM1932)** - Board documentation including ST-Link debugger pins
- **STM32CubeMX** - Tool for configuration and code generation (useful for reference)
- **STM32 community forums** - support.st.com for troubleshooting

**MicroPython on STM32:**
- **MicroPython STM32 Port Documentation** - f469-disco/micropython/ports/stm32/README.md
- **MicroPython Build System Changes v1.25** - Check release notes for breaking changes
- **User C Modules Documentation** - How to integrate C modules into MicroPython

## Hands-On Practice (Before Starting)

**Recommended Exercises:**

1. **Basic OpenOCD + GDB Workflow**
   - Connect to STM32F469 Discovery board
   - Halt CPU, read registers, read/write memory
   - Practice: `openocd -f board/stm32f469discovery.cfg` then `arm-none-eabi-gdb`

2. **Flash Memory Inspection**
   - Use GDB to dump flash memory: `x/256xw 0x08000000`
   - Compare with binary file contents: `xxd firmware.bin`
   - Understand flash organization and sectors

3. **Simple Blinky Program**
   - Write minimal ARM assembly or C program to blink LED
   - Build with arm-none-eabi-gcc, create custom linker script
   - Flash manually with OpenOCD, debug with GDB
   - This builds intuition for memory layout and boot process

4. **Vector Table Analysis**
   - Examine vector table in working firmware: first 64 bytes of flash
   - Verify: Initial SP (stack pointer), Reset vector, exception handlers
   - Compare with datasheet expectations

## Time Investment Estimate

- **Minimal functional knowledge:** 8-16 hours of reading + 4-8 hours hands-on practice
- **Comfortable working knowledge:** 20-30 hours total
- **Expert level:** 40+ hours (not necessary for this project)

**Recommendation:** If developer is completely new to ARM/STM32, allocate 2-3 days for training before starting Phase 1. This investment will significantly accelerate debugging and reduce trial-and-error time.

## Quick Reference Checklists

**OpenOCD + GDB Essential Commands:**
```bash
# Terminal 1: Start OpenOCD
openocd -f board/stm32f469discovery.cfg

# Terminal 2: Connect GDB
arm-none-eabi-gdb bin/firmware.elf
(gdb) target extended-remote :3333
(gdb) monitor reset halt
(gdb) load
(gdb) continue

# Useful GDB commands
info registers              # Show all registers
info reg sp pc              # Stack pointer and program counter
x/32xw 0x08000000          # Dump 32 words from flash start
x/32xw $sp                 # Dump stack
disassemble $pc            # Disassemble current location
break main                 # Set breakpoint
monitor reset init         # Reset via OpenOCD
```

**Memory Address Quick Reference (STM32F469):**
- Flash start: 0x08000000
- SRAM1 start: 0x20000000
- Bootloader end / Firmware start (USE_DBOOT=1): 0x08020000
- Vector table offset (if using bootloader): 0x20000 (128KB)

---
