# detect if it's a hardware device or linuxport
import sys
import os
import pyb
import gc
import asyncio

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

    async def erase_and_format(self, progress_cb=None):
        """
        Securely erases the SD card - overwrites every block with random
        data, the same approach platform.wipe() uses for the internal
        flash - and then creates a fresh, empty FAT filesystem on it.

        This is irreversible and destroys EVERYTHING on the card, not
        just files Specter-DIY created. There is no cancelling partway
        through: like platform.wipe(), once started it must run to
        completion or the card is left in a half-overwritten, unusable
        state.

        progress_cb(fraction), if given, is awaited after every chunk
        with the fraction (0..1) of blocks written so far, so a caller
        can drive a progress screen without blocking the event loop for
        the whole operation. The event loop is allowed to run after every
        chunk either way (asyncio.sleep_ms(0)) - also when a progress_cb
        is given, since a callback that never awaits anything itself
        (like a simple screen redraw) would otherwise starve the GUI's
        update loop for the entire operation.
        """
        if not self.is_present:
            raise RuntimeError("SD card is not present")
        self.unmount()
        if self._sd is None:
            # simulator: no real block device to overwrite - just clear
            # out the directory that stands in for the card.
            delete_recursively(fpath("/sd"))
            if progress_cb is not None:
                await progress_cb(1.0)
            return
        if self._led is not None:
            self._led.on()
        self._sd.power(True)
        try:
            block_size = self._sd.ioctl(5, None)
            block_count = self._sd.ioctl(4, None)
            if (
                not isinstance(block_size, int)
                or not isinstance(block_count, int)
                or block_size <= 0
                or block_count <= 0
            ):
                raise RuntimeError(
                    "SD card reported invalid geometry "
                    "(block size %r, block count %r) - cannot erase."
                    % (block_size, block_count)
                )
            # 1 MB per write call: a full-card wipe can be tens of
            # thousands of chunks even at this size, so this balances
            # write/gc.collect() overhead against keeping a single
            # os.urandom() buffer (and GUI-tick latency) reasonable.
            chunk_blocks = max(1, (1024 * 1024) // block_size)
            for start in range(0, block_count, chunk_blocks):
                n = min(chunk_blocks, block_count - start)
                try:
                    self._sd.writeblocks(start, os.urandom(block_size * n))
                except OSError as e:
                    raise RuntimeError(
                        "Could not write to the SD card during secure erase "
                        "(card may have been removed):\n\n%s\n\n"
                        "The card is now in a half-overwritten, unusable "
                        "state and must be reformatted before it can be "
                        "used again." % e
                    ) from e
                gc.collect()
                if progress_cb is not None:
                    await progress_cb((start + n) / block_count)
                # Always yield to the event loop, even with a progress_cb:
                # a callback that never awaits (e.g. one that only redraws
                # a progress bar) runs synchronously and would otherwise
                # keep every other task - including the GUI update loop -
                # from running until the whole card is overwritten.
                await asyncio.sleep_ms(0)
            try:
                os.VfsFat.mkfs(self._sd)
            except OSError as e:
                raise RuntimeError(
                    "Overwrite completed, but creating a fresh filesystem "
                    "failed:\n\n%s\n\nThe card's old data has been wiped, "
                    "but it has no valid filesystem and must be reformatted "
                    "on a computer before it can be used." % e
                ) from e
        finally:
            self._sd.power(False)
            if self._led is not None:
                self._led.off()


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


def secure_delete_file(path, passes=3):
    """
    Overwrites a file's contents with fresh random data `passes` times,
    syncing after each pass, before deleting it - the same
    overwrite-then-unlink principle BitBox02's firmware uses when it
    replaces a backup file (_delete_file() / sd_erase_file_in_subdir() in
    bitbox02-firmware/src/sd.c), except that overwrites once with a fixed
    byte (0xAC); this uses fresh random data on every one of several
    passes instead.

    A plain os.remove() only unlinks the directory entry - the file's
    old bytes are still physically on the card until that space happens
    to be reused, and can often be recovered with an undelete tool in
    the meantime. This closes that gap for individual files (see
    SDCard.erase_and_format() for the equivalent whole-card operation).

    The file is opened once and kept open across all passes, rather than
    stat-then-open per pass: a stat/open gap would let an attacker with
    write access swap the path (e.g. via a hardlink on FAT variants that
    support them) between the size check and the overwrite, causing us
    to wipe the wrong file. The size is read from the same handle via
    seek(0, 2)/tell(), and that handle is used for every overwrite pass.
    """
    with open(path, "r+b") as f:
        f.seek(0, 2)  # seek to end
        size = f.tell()
        for _ in range(passes):
            f.seek(0)
            remaining = size
            while remaining > 0:
                chunk = min(remaining, 4096)
                f.write(os.urandom(chunk))
                remaining -= chunk
            sync()
    os.remove(path)


# Same cap as bitbox_sd.MAX_LIST_ENTRIES / Specter._SDCARD_LIST_MAX_ENTRIES:
# an adversarial directory with thousands of entries would otherwise make
# secure_delete_tree() overwrite-and-sync for minutes (DoS). 200 is far
# above any legitimate tree this is called on (a BitBox backup directory
# has exactly 3 files), and matches the cap used elsewhere for SD listing.
SECURE_DELETE_MAX_FILES = 200


def secure_delete_tree(path, passes=3):
    """
    Recursively secure_delete_file()s every regular file under `path`
    (see its docstring), then removes the now-empty directories,
    including `path` itself. Used for multi-file items such as a BitBox
    backup directory, where each of the redundant copies must be
    overwritten, not just unlinked.

    Enumerates and counts every file under the tree BEFORE overwriting
    anything: a tree with more than SECURE_DELETE_MAX_FILES files is
    rejected up front so a partial overwrite is never left behind, and
    so an adversarial directory cannot force unbounded overwrite+sync
    work. The caller can offer "Format entire SD card" as the fallback
    for wiping a tree that exceeds the cap.
    """
    files = []
    _collect_files(path, files)
    if len(files) > SECURE_DELETE_MAX_FILES:
        raise RuntimeError(
            "directory contains %d files (maximum %d) - use 'Format "
            "entire SD card' instead" % (len(files), SECURE_DELETE_MAX_FILES)
        )
    for full in files:
        secure_delete_file(full, passes=passes)
    _remove_empty_dirs(path)


def _collect_files(path, out):
    """Recursively appends the full paths of all regular files under
    `path` to `out` (a list). Does not modify or delete anything."""
    for name, entry_type, *_rest in os.ilistdir(path):
        if name in (".", ".."):
            continue
        full = "%s/%s" % (path, name)
        if entry_type == 0x8000:
            out.append(full)
        elif entry_type == 0x4000:
            _collect_files(full, out)


def _remove_empty_dirs(path):
    """Recursively removes every empty directory under `path`, then
    `path` itself. Must be called after secure_delete_file() has already
    unlinked every regular file, so each directory is in fact empty."""
    for name, entry_type, *_rest in os.ilistdir(path):
        if name in (".", ".."):
            continue
        if entry_type == 0x4000:
            _remove_empty_dirs("%s/%s" % (path, name))
    os.rmdir(path)


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


def wipe():
    """
    Blocks map in disco board
    0: MBR
    1   - 255:   reserved
    256 - 447:   internal flash
    448 - 33215: QSPI
    """
    # delete files normally in simulator
    try:
        delete_recursively(fpath("/flash"))
        delete_recursively(fpath("/qspi"))
    except:
        pass
    # on real hardware overwrite flash with random data
    if not simulator:
        os.umount("/flash")
        os.umount("/qspi")
        f = pyb.Flash()
        block_size = f.ioctl(5, None)
        # wipe internal flash with random bytes
        for i in range(256, 450):
            b = os.urandom(block_size)
            f.writeblocks(i, b)
            del b
            gc.collect()
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
