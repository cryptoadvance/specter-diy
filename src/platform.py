# detect if it's a hardware device or linuxport
import sys
import os
import pyb

simulator = (sys.platform in ["linux", "darwin"])


# Build metadata injected at boot time. Defaults represent the minimum
# information we can know without platform-specific boot scripts.
bootloader_locked = None
build_type = "unknown"

if simulator:
    build_type = "unix"
    bootloader_locked = False

try:
    import config
except:
    import config_default as config

if not simulator:
    import sdram
    import stm

    sdram.init()
else:
    _PREALLOCATED = bytes(0x100000)
    stm = None

# injected by the boot.py
i2c = None # I2C to talk to the battery


class CriticalErrorWipeImmediately(Exception):
    """
    This exception should be raised when device needs to be wiped
    because something terrible happened
    """

    pass


def maybe_mkdir(path):
    try:
        os.mkdir(path)
    except:
        pass
    if not simulator:
        os.sync()


class SDCard:
    _mounted = False

    def __init__(self, sd = None, led = None):
        self._sd = sd
        self._led = led
        if led is not None:
            led.off()

    @property
    def is_present(self):
        """
        Checks if SD card is inserted
        """
        # simulator
        if self._sd is None:
            return True
        return self._sd.present()

    def mount(self):
        """Mounts SD card"""
        if not self.is_present:
            raise RuntimeError("SD card is not present")
        if self._sd is None:
            return
        if self._led is not None:
            self._led.on()
        self._sd.power(True)
        os.mount(self._sd, "/sd")
        self._mounted = True

    def open(self, filename, *args, **kwargs):
        return open(
            fpath("/sd/" + filename.lstrip("/")),
            *args, **kwargs
        )

    def file_exists(self, filename) -> bool:
        return file_exists(fpath("/sd/" + filename.lstrip("/")))

    def unmount(self):
        """Unmounts SD card"""
        # sync file system before unmounting
        if not self._mounted:
            return
        self._mounted = False
        if self._sd is None:
            return
        os.sync()
        os.umount("/sd")
        self._sd.power(False)
        if self._led is not None:
            self._led.off()

    def __enter__(self):
        self.mount()
        return self

    def __exit__(self, *args, **kwargs):
        self.unmount()


def fpath(fname):
    """A small function to avoid % storage_root everywhere"""
    return "%s%s" % (config.storage_root, fname)


if simulator:
    # create folders for simulator
    maybe_mkdir(config.storage_root)
    maybe_mkdir(fpath("/flash"))
    maybe_mkdir(fpath("/qspi"))
    maybe_mkdir(fpath("/sd"))
    sdcard = SDCard(None, None)
else:
    storage_root = ""
    sdcard = SDCard(pyb.SDCard(), pyb.LED(4))

def get_git_info():
    """Return repository metadata embedded into the firmware build."""

    repo = "unknown"
    branch = "unknown"
    commit = "unknown"

    try:
        from git_info import REPOSITORY, BRANCH, COMMIT

        if REPOSITORY:
            repo = REPOSITORY
        if BRANCH:
            branch = BRANCH
        if COMMIT:
            commit = COMMIT
    except:
        pass

    return repo, branch, commit


def get_version() -> str:
    # version is coming from boot.py if running on the hardware
    try:
        ver = version.split(">")[1].split("</")[0]
        major = int(ver[:2])
        minor = int(ver[2:5])
        patch = int(ver[5:8])
        rc = int(ver[8:])
        ver = "%d.%d.%d" % (major, minor, patch)
        if rc != 99:
            ver += "-rc%d" % rc
        return ver
    except:
        return "unknown"


def get_bootloader_lock_status() -> str:
    if bootloader_locked is True:
        return "locked"
    if bootloader_locked is False:
        return "unlocked"
    return "unknown"


def get_build_type() -> str:
    return build_type


def get_firmware_boot_mode() -> str:
    """Return boot mode based on the current vector table address."""

    if simulator:
        return "simulator"

    try:
        vtor = stm.mem32[0xE000ED08]
    except Exception:
        return "unknown"

    if vtor >= 0x08020000:
        return "bootloader"
    if vtor >= 0x08000000:
        return "open"
    return "unknown"


def get_flash_read_protection_status() -> str:
    """Return human readable read protection status."""

    if simulator:
        return "not applicable"

    try:
        option_control = stm.mem32[0x40023C14]
    except Exception:
        return "unknown"

    read_level = (option_control >> 8) & 0xFF

    if read_level == 0xAA:
        return "disabled"
    if read_level == 0xCC:
        return "enabled (level 2)"
    return "enabled (level 1)"


def get_flash_write_protection_status() -> str:
    """Return human readable write protection status."""

    if simulator:
        return "not applicable"

    try:
        option_control = stm.mem32[0x40023C14]
    except Exception:
        return "unknown"

    lower = (option_control >> 16) & 0xFFFF
    upper = 0xFFFF

    if stm is not None:
        try:
            option_control_1 = stm.mem32[0x40023C18]
            upper = option_control_1 & 0xFFFF
        except Exception:
            pass

    if lower == 0xFFFF and upper == 0xFFFF:
        return "disabled"
    return "enabled"

def mount_sdram():
    path = fpath("/ramdisk")
    if simulator:
        # not a real RAM on simulator
        maybe_mkdir(path)
        # cleanup
        delete_recursively(path)
    else:
        bdev = sdram.RAMDevice(512)
        os.VfsFat.mkfs(bdev)
        os.mount(bdev, path)
    return path

def get_preallocated_ram():
    """Returns pointer and size of preallocated memory"""
    if simulator:
        import ctypes
        return ctypes.addressof(_PREALLOCATED), len(_PREALLOCATED)
    else:
        return sdram.preallocated_ptr(), sdram.preallocated_size()

def sync():
    try:
        os.sync()
    except:
        pass


def file_exists(fname: str) -> bool:
    try:
        with open(fname, "rb"):
            pass
        return True
    except:
        return False


def delete_recursively(path, include_self=False):
    # remove trailing slash
    if path is None:
        raise RuntimeError("Path is not specified")
    path = path.rstrip("/")
    files = os.ilistdir(path)
    for _file in files:
        if _file[0] in [".", ".."]:
            continue
        f = "%s/%s" % (path, _file[0])
        # regular file
        if _file[1] == 0x8000:
            os.remove(f)
        # directory
        elif _file[1] == 0x4000:
            delete_recursively(f)
            os.rmdir(f)

    files = os.ilistdir(path)
    num_of_files = sum(1 for _ in files)
    if (num_of_files == 2 and simulator) or num_of_files == 0:
        """
        Directory is empty - it contains exactly 2 directories -
        current directory and parent directory (unix) or
        0 directories (stm32)
        """
        if include_self:
            os.rmdir(path)
        return True
    raise RuntimeError("Failed to delete folder %s" % path)


if not simulator:
    stlk = pyb.UART("YB", 9600)

def enable_usb():
    pyb.usb_mode("VCP")

def disable_usb():
    pyb.usb_mode(None)

def set_usb_mode(dev=False, usb=False):
    if simulator:
        print("dev:", dev, ", usb:", usb)
    # now get correct mode
    if usb: # and not dev:
        pyb.usb_mode("VCP")
        if not simulator:
            os.dupterm(None, 0)
            os.dupterm(None, 1)
    # elif usb and dev:
    #     pyb.usb_mode("VCP+MSC")
    #     if not simulator:
    #         # duplicate repl to stlink
    #         # as usb is busy for communication
    #         os.dupterm(stlk, 0)
    #         os.dupterm(None, 1)
    # elif not usb and dev:
    #     pyb.usb_mode("VCP+MSC")
    #     usb = pyb.USB_VCP()
    #     if not simulator:
    #         os.dupterm(None, 0)
    #         os.dupterm(usb, 1)
    else:
        pyb.usb_mode(None)
        if not simulator:
            os.dupterm(None, 0)
            os.dupterm(None, 1)


def reboot():
    if simulator:
        sys.exit()
    else:
        pyb.hard_reset()


# Verified block map of pyb.Flash() on the STM32F469 Discovery board
# (make disco USE_DBOOT=1). Absolute block numbers:
#   block 0            emulated MBR, not backed by real flash
#   blocks 1   - 255    unmapped (bootloader/reserved sectors), never
#                       reachable through this API
#   blocks 256 - 447    internal flash, the "/flash" filesystem (96 KiB)
#   blocks 448 - 33215  external QSPI flash, the "/qspi" filesystem (16 MiB)
# Full derivation, source files checked and submodule pins:
# see docs/flash-block-map.md
# The boundary between the two filesystems is the only part of the map
# below that no ioctl() exposes: it comes from the linker script and
# storage.h inside the pinned submodule, so it has to be stated here.
# Block size and the end of the QSPI region are *not* restated - wipe()
# reads both from the block device at run time (see
# diybitcoinhardware/f469-disco#44 for making the boundary queryable too).
INTERNAL_FLASH_START_BLOCK = 0x100                             # FLASH_PART1_START_BLOCK
INTERNAL_FLASH_END_BLOCK = INTERNAL_FLASH_START_BLOCK + 192     # + FLASH_MEM_SEG1_NUM_BLOCKS

QSPI_START_BLOCK = INTERNAL_FLASH_END_BLOCK                     # FLASH_PART2_START_BLOCK

# How many blocks get overwritten per writeblocks() call. Kept small, and
# a multiple of the QSPI erase-sector size (8 blocks == 4096 bytes), so
# the wipe never needs a whole region's worth of RAM (up to 16MiB for
# QSPI) at once.
WIPE_CHUNK_BLOCKS = 16

# extmod/vfs.h: MP_BLOCKDEV_IOCTL_SYNC / _BLOCK_COUNT / _BLOCK_SIZE.
MP_BLOCKDEV_IOCTL_SYNC = 3
MP_BLOCKDEV_IOCTL_BLOCK_COUNT = 4
MP_BLOCKDEV_IOCTL_BLOCK_SIZE = 5
# Both the internal-flash driver (flashbdev.c) and the QSPI driver
# (drivers/memory/spiflash.c, built with USE_WR_DELAY) keep a
# *write-behind* RAM cache: writeblocks() only guarantees the data
# reaches that RAM cache, not the physical chip. The cache is flushed to
# physical storage on a sector-boundary crossing, on this ioctl, or -
# eventually - by a periodic background IRQ. Nothing forces the very
# last sector each overwrite loop below touches to be flushed before
# reboot() other than calling this ioctl explicitly, so wipe() must do
# that itself: a hard reset with a still-dirty cache would lose our
# overwrite of that sector from RAM and leave the original, pre-wipe
# bytes physically in place on the chip.
#
# Known limitation: the pinned MicroPython storage drivers do not
# reliably propagate every underlying physical erase/program failure up
# to this Python-level API - and this affects both flash regions, not
# just QSPI:
#   - QSPI (drivers/memory/spiflash.c): a genuine erase/program failure
#     during a cache flush (mp_spiflash_cache_flush_internal()) is not
#     propagated through mp_spiflash_cache_flush() -> the SYNC ioctl, nor
#     through a sector-boundary flush triggered mid-loop by a
#     writeblocks() call - the C driver clears its dirty flag and
#     returns before checking the erase/write result.
#   - Internal flash (ports/stm32/flash.c): flash_erase() and
#     flash_write() are themselves declared void - a HAL_FLASHEx_Erase()
#     or HAL_FLASH_Program() failure inside them is checked but has
#     nowhere to go, and flash_bdev's cache (flashbdev.c) is marked clean
#     again regardless.
# So a hardware write failure at that level can go undetected here, even
# though every check wipe() below actually has access to (writeblocks()'s
# own return code, the SYNC ioctl's return code, and the geometry check
# below) is applied. This means "not (internal_ok and qspi_ok and ...)"
# below is not a complete guarantee that every possible physical write
# failure was caught - only that every failure the pinned MicroPython
# fork's block-device API actually surfaces was caught. Fixing the gap
# itself requires propagating real error codes through both of those
# drivers - out of scope here.


def _sync_flash(f):
    """
    Forces the write-behind cache (see MP_BLOCKDEV_IOCTL_SYNC above) out
    to physical flash, checking both an exception and a nonzero/failure
    return code - not just whether the call raised. See the "Known
    limitation" note above for what this can and can't actually catch.
    """
    try:
        ret = f.ioctl(MP_BLOCKDEV_IOCTL_SYNC, None)
    except Exception:
        return False
    return ret in (0, None)


def _secure_overwrite_blocks(f, start_block, end_block, block_size,
                              chunk_blocks=WIPE_CHUNK_BLOCKS):
    """
    Overwrites blocks [start_block, end_block) of the raw flash block
    device `f` with a fixed zero pattern, `chunk_blocks` blocks at a
    time, so the whole region never needs to fit in RAM at once.

    Uses zeros rather than os.urandom(): the QSPI/internal-flash drivers
    already erase (and thus fully overwrite) every sector they touch, so
    randomness buys nothing against this threat model (a chip pulled off
    the board and read directly) beyond what any fixed pattern gives -
    while os.urandom() on this port draws one hardware RNG sample per
    *byte* (ports/stm32/rng.c: ~10us each, 10ms timeout), which would
    cost minutes just generating bytes for the 16 MiB QSPI region alone,
    on top of the actual erase/program time. A single pre-built buffer is
    reused (sliced for the final, possibly shorter chunk) instead of
    allocating fresh memory every iteration.

    A failed chunk does not stop the wipe: we keep going so as much of
    the remaining sensitive data as possible still gets destroyed. But
    the return value reflects whether *every* chunk succeeded - callers
    must not treat a False result as if the region were fully wiped.
    """
    zeros = bytes(chunk_blocks * block_size)
    ok = True
    block = start_block
    while block < end_block:
        n = min(chunk_blocks, end_block - block)
        buf = zeros if n == chunk_blocks else zeros[:n * block_size]
        try:
            ret = f.writeblocks(block, buf)
            if ret:
                ok = False
        except Exception:
            ok = False
        block += n
    return ok


def wipe():
    """
    Securely wipes user data.

    Deletes the "/flash" and "/qspi" filesystems, and on real hardware
    also physically overwrites the underlying internal-flash and QSPI
    block ranges (see the verified block map above) with a fixed
    pattern. Logical file deletion alone is not enough: an attacker with
    physical access to the external QSPI flash chip could still recover
    "deleted" files straight from it, since deleting a file only drops
    its filesystem entry - the QSPI chip itself is unaffected. Firmware,
    bootloader and reserved blocks are never touched.
    """
    f = None
    block_size = None
    qspi_end_block = None
    if not simulator:
        # Read the actual flash geometry, before deleting anything.
        # Block size and the end of the QSPI region are taken from the
        # device rather than assumed, so a larger or differently sized
        # chip gets wiped in full instead of only up to a hardcoded
        # bound. QSPI runs to the last block of the device: the two
        # filesystems together cover everything above the split point.
        f = pyb.Flash()
        block_size = f.ioctl(MP_BLOCKDEV_IOCTL_BLOCK_SIZE, None)
        block_count = f.ioctl(MP_BLOCKDEV_IOCTL_BLOCK_COUNT, None)
        qspi_end_block = block_count

        # What cannot be read back is the internal/QSPI split point, so
        # that assumption still has to be sanity-checked: if the device
        # does not even extend past it, the layout this code was
        # verified against no longer holds and the block numbers below
        # are meaningless. Fail closed rather than overwrite a range
        # picked by guesswork - a wipe that silently hits the wrong
        # blocks would report success while leaving the seed in place.
        if not block_size or not block_count or block_count <= QSPI_START_BLOCK:
            raise RuntimeError(
                "Unexpected flash geometry (block_size=%r, block_count=%r); "
                "refusing to wipe" % (block_size, block_count)
            )

    # delete files normally in simulator (best-effort on hardware too,
    # though the block overwrite below is what actually destroys data there)
    try:
        delete_recursively(fpath("/flash"))
        delete_recursively(fpath("/qspi"))
    except:
        pass
    # on real hardware overwrite flash with a fixed pattern
    if not simulator:
        # /flash and /qspi are unmounted independently, and a failure on
        # either is tracked rather than swallowed: a clean unmount is what
        # flushes any write-behind cache left over from delete_recursively()
        # above (see flashbdev.c/spiflash.c), and losing that guarantee is
        # itself a reason not to trust the wipe. It does not, however, stop
        # us from attempting the raw overwrite below - that's still the
        # best available defense even if the unmount failed.
        flash_unmount_ok = True
        try:
            os.umount("/flash")
        except Exception:
            flash_unmount_ok = False

        qspi_unmount_ok = True
        try:
            os.umount("/qspi")
        except Exception:
            qspi_unmount_ok = False

        internal_ok = _secure_overwrite_blocks(
            f, INTERNAL_FLASH_START_BLOCK, INTERNAL_FLASH_END_BLOCK, block_size
        )
        # Flush now, before starting the much longer QSPI loop: if power
        # is lost partway through overwriting 16 MiB of QSPI, the internal
        # flash's last touched sector should already be durably written
        # rather than still waiting in the write-behind cache.
        internal_sync_ok = _sync_flash(f)

        qspi_ok = _secure_overwrite_blocks(
            f, QSPI_START_BLOCK, qspi_end_block, block_size
        )
        # Final flush - see MP_BLOCKDEV_IOCTL_SYNC above for why this
        # can't be skipped.
        qspi_sync_ok = _sync_flash(f)

        if not (flash_unmount_ok and qspi_unmount_ok and internal_ok and qspi_ok
                and internal_sync_ok and qspi_sync_ok):
            # Whatever could be destroyed already has been (see
            # _secure_overwrite_blocks), but a partial wipe must never be
            # allowed to look like a successful one. Raise instead of
            # rebooting so the caller (specter.py's Specter.wipe_or_halt())
            # surfaces the failure instead of silently trusting the device
            # is clean.
            raise RuntimeError(
                "Secure wipe failed to overwrite all flash blocks; "
                "device may still contain recoverable data"
            )
    # mpy will reformat fs on reboot
    reboot()


def usb_connected():
    if simulator:
        return True
    return bool(pyb.Pin.board.USB_VBUS.value())

BATTERY_TABLE = [
    (4.2,  100),
    (4.0,  75),
    (3.85, 50),
    (3.75, 35),
    (3.6,  0),
]

def get_battery_status():
    # simulator or no i2c
    if i2c is None:
        return None, None
    try:
        # check if battery monitor exists
        if 112 not in i2c.scan():
            return None, None
        voltage = int.from_bytes(i2c.mem_read(2, 112, 8),'little')*2.44e-3
        level = 0
        for i, (v, lvl) in enumerate(BATTERY_TABLE):
            if voltage > v:
                # max voltage
                if i == 0:
                    level = lvl
                    break
                # linear interpolation
                prevV, prevLvl = BATTERY_TABLE[i-1]
                level = int(lvl + (prevLvl-lvl)*(voltage-v)/(prevV-v))
                break
        charging = (int.from_bytes(i2c.mem_read(2, 112, 6),'little') < 8192)
        return level, charging
    except Exception as e:
        print(e)
        return None, None
