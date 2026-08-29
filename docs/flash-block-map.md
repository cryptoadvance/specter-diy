# Flash Block Map (STM32F469 Discovery)

Verified block map of `pyb.Flash()` on the STM32F469 Discovery board, as built by
Specter's firmware (`make disco USE_DBOOT=1`). `pyb.Flash()` (no args) exposes the
whole board's storage as one block device addressed with these **absolute** block
numbers. This is the ground truth behind the `*_BLOCK` constants in `src/platform.py`
(`INTERNAL_FLASH_START_BLOCK`, `INTERNAL_FLASH_END_BLOCK`, `QSPI_START_BLOCK`) and
behind what `platform.wipe()` overwrites. Note that the block size and the end of the
QSPI region are deliberately **not** constants: `wipe()` reads both back from the block
device with `ioctl()`, so only the split point between the two filesystems is stated in
the code.

| Blocks        | Region                                   | Notes |
|---------------|-------------------------------------------|-------|
| 0             | software-emulated MBR (`storage.c:storage_read/write_block`) | not backed by real flash - writes to it are silently discarded by the block device |
| 1 – 255       | unmapped                                   | not part of any partition; `writeblocks()` on these fails (`storage_write_block()` returns false -> `-EIO`). Physically these blocks fall in the bootloader/ISR sector (`0x08000000`, 16K) and the reserved sector (`FLASH_RSV`, `0x08004000`, 16K) of `ports/stm32/boards/stm32f469xi_dboot.ld` - never reachable through this API regardless |
| 256 – 447     | internal flash, the `/flash` filesystem    | `FLASH_PART1_START_BLOCK = 0x100` (`storage.h`); 192 blocks = 96 KiB, matching `FLASH_MEM_SEG1` (`flashbdev.c`, STM32F469xx: sectors 2-4, `0x08008000`), which is exactly the `FLASH_FS` region of `stm32f469xi_dboot.ld` - disjoint from `FLASH_TEXT` (the application firmware, sectors 5-21 starting at `0x08020000`) and from `FLASH_BOOT1`/`FLASH_BOOT2` (the bootloader slots, sectors 22-23) |
| 448 – 33215   | external QSPI flash, the `/qspi` filesystem | `FLASH_PART2_START_BLOCK = FLASH_PART1_START_BLOCK + 192` (`storage.h`); 32768 blocks = 16 MiB, the full size of the on-board QSPI NOR flash chip (`MICROPY_HW_SPIFLASH_SIZE_BITS = 128 Mbit`, `boards/STM32F469DISC/mpconfigboard.h`) |

## Why a raw overwrite actually destroys the data

The QSPI chip is addressed as plain NOR flash - no wear-leveling, remapping or
translation layer sits between the block numbers above and the physical sectors
(see `spi_bdev_writeblocks()` / `mp_spiflash_cached_write()` in
`ports/stm32/spibdev.c` and `drivers/memory/spiflash.c`), so overwriting every
block in a range overwrites all addressable QSPI sectors, which prevents recovery
through normal digital reads of the flash contents. (This says nothing about
charge-remanence / decapping-level analog recovery, which is out of scope for this
threat model.) Required sector-erase-before-write is handled transparently by that
driver.

## Sources checked

- `diybitcoinhardware/f469-disco` (submodule pin `db3ce3e`)
- `diybitcoinhardware/micropython` (submodule pin `6bdf1b6`)
- `ports/stm32/{storage.h,storage.c,flashbdev.c,spibdev.c}`
- `ports/stm32/boards/STM32F469DISC/{mpconfigboard.h,mpconfigboard.mk}`
- `ports/stm32/boards/stm32f469xi_dboot.ld`
- `drivers/memory/spiflash.c`

## Keeping this current

These submodule pins can move independently of this file. If `f469-disco` or the
MicroPython fork is updated, re-check the sources above before trusting this table.
Block size and total block count drift is handled automatically, because `wipe()` takes
both from the device. The split point is the part that cannot be read back: `wipe()`
only sanity-checks that the device extends past it and refuses to touch anything if it
does not, which will not catch a shifted split point that still leaves the total block
count plausible. See the tracking issue to expose the partition boundary as a proper
runtime API instead of a hard-coded constant:
[diybitcoinhardware/f469-disco#44](https://github.com/diybitcoinhardware/f469-disco/issues/44).
