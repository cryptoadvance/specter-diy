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


def is_valid_count(value, allow_zero=False):
    """
    True if `value` is a plain non-negative integer usable as a block or
    byte count. Rejects bools (which are ints in Python) and, unless
    `allow_zero`, zero. Shared by every geometry/size sanity check below
    so they all reject the same set of bogus driver/stat values.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return value >= 0 if allow_zero else value > 0


# A block device reporting a larger block size than this is not something we
# can wipe in bounded memory: the erase buffer can never be smaller than one
# block. Real SD cards and the internal flash report 512 bytes; 64 KiB leaves
# room for anything plausible while keeping the buffer cap meaningful.
MAX_SANE_BLOCK_SIZE = 64 * 1024


def is_block_op_success(result):
    """
    True if a block-device call reported success.

    The conventions differ between the drivers used here: pyb.SDCard's
    writeblocks() returns True/False (sdcard.c ends in
    mp_obj_new_bool(ret == 0)), pyb.Flash's returns the integer status
    directly - 0, or a negative errno (storage.c) - and generic MicroPython
    block devices return None. Accept only those known success values, so an
    unrecognised result fails closed: a block that was never written must
    never be reported as a successful wipe.
    """
    if result is None or result is True:
        return True
    return (
        isinstance(result, int)
        and not isinstance(result, bool)
        and result == 0
    )


def validate_block_geometry(block_size, block_count, device="storage device",
                            min_blocks=1):
    """
    Sanity-checks the geometry a block device reports before any
    destructive, geometry-driven operation runs against it.

    A driver reporting a bogus size would make an erase loop write the wrong
    amount of data, and a non-positive count would make it skip every block
    while still reporting success. `min_blocks` additionally rejects a device
    too small for the fixed block range its caller is about to write, so a
    hardcoded range can never run past the end of the reported geometry.
    Kept as a shared helper so every destructive path rejects the same cases
    identically.
    """
    if not is_valid_count(block_size) or not is_valid_count(block_count):
        raise RuntimeError(
            "%s reported invalid geometry (block size %r, block count %r) "
            "- cannot erase." % (device, block_size, block_count)
        )
    if block_size > MAX_SANE_BLOCK_SIZE:
        raise RuntimeError(
            "%s reported invalid geometry (block size %d exceeds the %d byte "
            "maximum) - cannot erase." % (device, block_size,
                                          MAX_SANE_BLOCK_SIZE)
        )
    if block_count < min_blocks:
        raise RuntimeError(
            "%s reports only %d blocks, but %d are required - cannot erase."
            % (device, block_count, min_blocks)
        )



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
        if self._sd is None:
            self._mounted = False
            return
        error = None
        unmounted = False
        try:
            # A failed sync must not prevent us from trying to remove the
            # VFS mount. Keep the first error for the caller, but always run
            # both cleanup operations.
            try:
                os.sync()
            except Exception as e:
                error = e
            try:
                os.umount("/sd")
                unmounted = True
            except Exception as e:
                if error is None:
                    error = e
        finally:
            # Only clear this flag after a successful VFS unmount. If the
            # result is unknown, a later cleanup attempt must not be skipped.
            if unmounted:
                self._mounted = False
            # Cut power only once the VFS mount is really gone - or once the
            # card is positively known to be absent, so there is nothing left
            # to retry against. Powering the interface down while /sd is
            # still mounted would leave the VFS pointing at a dead block
            # device, and the retry this method leaves open syncs before it
            # umounts, so that retry would run against hardware that can no
            # longer answer.
            if unmounted or self._card_is_absent():
                try:
                    self._sd.power(False)
                except Exception as e:
                    if error is None:
                        error = e
            try:
                if self._led is not None:
                    self._led.off()
            except Exception as e:
                if error is None:
                    error = e
        if error is not None:
            raise error

    def _card_is_absent(self):
        """
        True only when the card is POSITIVELY known to be gone.

        A presence probe that raises proves nothing - the bus may simply
        have glitched - so an unknown answer must count as "still there".
        Treating a failed probe as proof of absence would let a double fault
        (umount fails AND the probe fails) cut power while /sd is still
        mounted, which is exactly the inconsistent state the caller above
        exists to avoid. Erring the other way at worst leaves the interface
        powered until a retry succeeds.

        Never raises: a failing probe must not mask the error already being
        reported.
        """
        try:
            return not self.is_present
        except Exception as e:
            print(e)
            return False

    def __enter__(self):
        self.mount()
        return self

    def __exit__(self, *args, **kwargs):
        self.unmount()

    @property
    def has_block_device(self):
        """
        True when a real block device backs this card, so raw block
        operations are possible. False in the simulator build (see the
        module-level `simulator` flag), where SDCard is constructed
        without a block device and /sd is an ordinary host directory.
        """
        return self._sd is not None

    async def erase_and_format(self, progress_cb=None):
        """
        Overwrites every block of the card with zeros and then creates a
        fresh, empty FAT filesystem on it.

        Irreversible: this destroys the whole card, not only the files
        Specter-DIY created. Best-effort, not forensic sanitization - see
        secure_delete_file() for why a logical overwrite cannot reach every
        historic copy on flash media. Cancelling the task at an await point leaves
        the card half-overwritten; that is reported as a RuntimeError
        rather than silently returning. The user-facing confirmation and
        the "do not remove the card" warning belong to the caller.

        progress_cb(fraction), if given, is awaited after every chunk with
        the fraction (0..1) of blocks written so far. The event loop is
        yielded to after every chunk either way - a progress_cb that never
        awaits anything itself (e.g. one that only redraws a progress bar)
        would otherwise starve the GUI update task for the whole erase - so
        a failing progress_cb is handled separately from that yield.
        """
        if not self.is_present:
            raise RuntimeError("SD card is not present")
        self.unmount()
        if not self.has_block_device:
            # Nothing to overwrite at block level - clear the directory
            # that stands in for the card instead.
            delete_recursively(fpath("/sd"))
            if progress_cb is not None:
                await progress_cb(1.0)
            return
        interrupted = (
            "Secure erase was interrupted before completion. The SD card "
            "is now in a half-overwritten, unusable state and must be "
            "reformatted before it can be used again."
        )
        completed = False
        if self._led is not None:
            self._led.on()
        try:
            try:
                powered = self._sd.power(True)
                if powered is False:
                    # pyb.SDCard.power() reports a failed power-on by
                    # returning False, not by raising: sd_power() in
                    # ports/stm32/sdcard.c is
                    # mp_obj_new_bool(sdcard_power_on()). Ignoring that
                    # return value would let an ordinary init failure fall
                    # through to ioctl(4), which reports 0 blocks for an
                    # inactive card - so a routine "card would not come up"
                    # would be reported as bogus geometry instead of what it
                    # is. Fail-safe either way (nothing is overwritten), but
                    # the wrong message for a destructive operation.
                    # Only an explicit False counts as failure; block
                    # devices that report no status return None.
                    raise RuntimeError(
                        "Could not access the SD card before secure erase "
                        "(the card could not be initialized)."
                    )
                block_size = self._sd.ioctl(5, None)
                block_count = self._sd.ioctl(4, None)
            except OSError as e:
                raise RuntimeError(
                    "Could not access the SD card before secure erase "
                    "(card may have been removed):\n\n%s" % e
                ) from e
            validate_block_geometry(block_size, block_count, "SD card")
            # Keep the temporary wipe buffer bounded. A 1 MB
            # allocation is needlessly risky on a fragmented MicroPython
            # heap; 128 KiB is still large enough to amortize SD writes
            # while keeping the wipe usable on the target hardware. The
            # geometry check above caps block_size, so this really is
            # bounded even for a device reporting unusually large blocks.
            chunk_blocks = max(1, (128 * 1024) // block_size)
            # Allocate the write buffer ONCE, before the first destructive
            # write, and reuse it for every chunk. Allocating per chunk
            # meant a fragmented heap could fail the allocation partway
            # through - after some blocks were already overwritten - and a
            # MemoryError is not an OSError, so it would have escaped past
            # the handler below as a raw traceback instead of the
            # "half-overwritten card" message. Failing here instead costs
            # nothing: not a single block has been touched yet.
            #
            # The buffer stays zero-filled and is never modified. Zeros are
            # a complete overwrite for sanitization purposes - NIST SP
            # 800-88 asks for user-addressable data to be replaced with
            # non-sensitive data, not for that data to be random - and on
            # this hardware random is not a viable option at card scale:
            # os.urandom() calls rng_get() once per byte (moduos.c), and
            # rng_get() busy-waits for RNG_SR_DRDY, "on the order of 10us"
            # by its own comment. That is hours per gigabyte of pure RNG
            # wait before a single SD write, so a full-card wipe would
            # never finish in a usable time. Whole-card erase therefore
            # writes zeros; see secure_delete_file() for the small-file
            # path, where the same cost is irrelevant.
            try:
                buf = bytearray(chunk_blocks * block_size)
            except MemoryError as e:
                raise RuntimeError(
                    "Not enough memory to start the secure erase. No data "
                    "has been changed - reboot the device and try again."
                ) from e
            view = memoryview(buf)
            data = None
            for start in range(0, block_count, chunk_blocks):
                n = min(chunk_blocks, block_count - start)
                result = None
                try:
                    # A memoryview slice for the short final chunk, so it
                    # does not allocate a copy of the buffer.
                    data = buf if n == chunk_blocks else view[:n * block_size]
                    result = self._sd.writeblocks(start, data)
                except OSError as e:
                    raise RuntimeError(
                        "Could not write to the SD card during secure erase "
                        "(card may have been removed):\n\n%s\n\n"
                        "The card is now in a half-overwritten, unusable "
                        "state and must be reformatted before it can be "
                        "used again." % e
                    ) from e
                except MemoryError as e:
                    # Nothing in this loop allocates any more, but a driver
                    # may. MemoryError is not an OSError, so without this it
                    # would escape as a raw traceback and the user would
                    # never be told the card is half-overwritten.
                    raise RuntimeError(interrupted) from e
                if not is_block_op_success(result):
                    raise RuntimeError(
                        "Could not write to the SD card during secure erase "
                        "(block device returned %r). The card is now in a "
                        "half-overwritten, unusable state and must be "
                        "reformatted before it can be used again." % result
                    )
                gc.collect()
                progress_error = None
                if progress_cb is not None:
                    try:
                        await progress_cb((start + n) / block_count)
                    except asyncio.CancelledError as e:
                        raise RuntimeError(interrupted) from e
                    except Exception as e:
                        # A broken progress callback must neither abort an
                        # erase that is already half-done nor skip the
                        # event-loop yield below.
                        progress_error = e
                try:
                    await asyncio.sleep_ms(0)
                except asyncio.CancelledError as e:
                    raise RuntimeError(interrupted) from e
                if progress_error is not None:
                    print(progress_error)
            # Release the erase buffer BEFORE formatting. mkfs() builds
            # VFS/FatFs structures of its own, and holding on to 128 KiB
            # that is not needed any more makes that allocation fail first
            # on a fragmented MicroPython heap - at the one moment where
            # failing is most expensive, with the whole card already
            # overwritten.
            data = None
            view = None
            buf = None
            gc.collect()
            try:
                os.VfsFat.mkfs(self._sd)
            except OSError as e:
                raise RuntimeError(
                    "Overwrite completed, but creating a fresh filesystem "
                    "failed:\n\n%s\n\nThe card's old data has been wiped, "
                    "but it has no valid filesystem and must be reformatted "
                    "on a computer before it can be used." % e
                ) from e
            except MemoryError as e:
                # MemoryError is not an OSError, so without this it would
                # escape as a raw traceback and the user would never be
                # told that the erase itself did complete.
                raise RuntimeError(
                    "Overwrite completed, but there was not enough memory "
                    "to create a fresh filesystem. The card's old data has "
                    "been wiped, but it has no valid filesystem and must be "
                    "reformatted on a computer before it can be used."
                ) from e
            completed = True
        finally:
            # Cleanup must never replace the failure being reported. An
            # exception raised in a finally block supplants the one already
            # propagating, so a power-off that fails while we are reporting
            # "the card is half-overwritten" would hide exactly the message
            # the user needs. Surface a cleanup failure only when there is
            # nothing more important in flight - same rule as unmount().
            cleanup_error = None
            try:
                self._sd.power(False)
            except Exception as e:
                cleanup_error = e
            try:
                if self._led is not None:
                    self._led.off()
            except Exception as e:
                if cleanup_error is None:
                    cleanup_error = e
            if cleanup_error is not None:
                if completed:
                    raise cleanup_error
                print(cleanup_error)


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


def delete_recursively(path, include_self=False, secure=False):
    """
    Removes every entry under `path`.

    With `secure=True` each regular file is handed to secure_delete_file()
    - its bytes overwritten with zeros and flushed before the unlink -
    rather than just os.remove()'d. Use it wherever the tree holds secrets:
    an encrypted wallet descriptor in QSPI free space is still decryptable
    with the unrotated enc_secret, and a signed PSBT left in the SDRAM
    ramdisk survives a warm reset. See secure_delete_file() for what a
    logical overwrite can and cannot reach.

    `secure=True` has no traversal caps of its own - unlike
    secure_delete_tree(), which guards against an adversarial host-supplied
    directory. The trees deleted here are Specter's own app folders, whose
    size is bounded by what Specter itself wrote.
    """
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
            if secure:
                secure_delete_file(f)
            else:
                os.remove(f)
        # directory
        elif _file[1] == 0x4000:
            delete_recursively(f, secure=secure)
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


SECURE_DELETE_CHUNK = 4096


def secure_delete_file(path):
    """
    Overwrites a file's contents with zeros, flushes that overwrite to the
    storage device and only then unlinks it. Returns the number of bytes
    overwritten.

    A plain os.remove() only unlinks the directory entry - the file's old
    bytes are still physically on the card until that space happens to be
    reused, and can often be recovered with an undelete tool in the
    meantime. This closes that gap for individual files;
    SDCard.erase_and_format() is the equivalent whole-card operation.

    Best-effort, not forensic sanitization: this overwrites the logical
    blocks the filesystem hands us. Flash media remap writes internally, so
    an older physical copy can survive in space the controller no longer
    exposes. NIST SP 800-88 makes the same point - reaching every historic
    copy needs purge or destroy, not an overwrite through the normal
    read/write interface.

    One pass of zeros, deliberately. NIST SP 800-88 asks for user-addressable
    data to be replaced with non-sensitive data, not for that data to be
    random, and multi-pass overwriting is a magnetic-media practice that on
    flash only spends write cycles. Zeros also keep this off the hardware
    RNG: os.urandom() calls rng_get() once per byte on the pinned firmware,
    and rng_get() busy-waits for RNG_SR_DRDY, so random data would make a
    tree at the SECURE_DELETE_MAX_TOTAL_BYTES cap block for over a minute -
    this function is synchronous and yields to nothing. Matches
    erase_and_format(), which writes zeros for the same reason.

    The file is opened once and its size read from that same handle via
    seek(0, 2)/tell() rather than stat-then-open: a stat/open gap would let
    an attacker with write access swap the path between the size check and
    the overwrite, causing us to wipe the wrong file.

    What this reaches is the file's CURRENT allocation, and nothing else.
    Two residues on FAT are worth naming, because both are ordinary
    filesystem behaviour rather than exotic flash effects:

    * Earlier versions of the same file. Opening a path "wb" truncates it,
      which frees its old cluster chain without overwriting it, and the
      rewrite is then usually placed elsewhere. Overwriting the file that
      exists today does not touch clusters an earlier version was written
      to. A caller replacing a sensitive file should secure-delete it first
      and create it fresh, rather than truncating over it.
    * The directory entry. FatFs marks a deleted entry rather than clearing
      it, so the file NAME - including its long-file-name records - stays
      readable in the directory sector after the contents are gone.

    Persistence of the overwrite is only as strong as strict_sync()
    below can make it on this runtime; see there.
    """
    zeros = bytes(SECURE_DELETE_CHUNK)
    view = memoryview(zeros)
    with open(path, "r+b") as f:
        f.seek(0, 2)  # seek to end
        size = f.tell()
        f.seek(0)
        remaining = size
        while remaining > 0:
            chunk = min(remaining, SECURE_DELETE_CHUNK)
            # A memoryview slice for the short final chunk, so it does not
            # allocate a copy.
            data = zeros if chunk == SECURE_DELETE_CHUNK else view[:chunk]
            written = f.write(data)
            if written != chunk:
                raise OSError(
                    "short write during secure delete (%r of %d bytes)"
                    % (written, chunk)
                )
            remaining -= written
        strict_sync(f)
    os.remove(path)
    return size


def strict_sync(f=None):
    """
    Flushes as far down the stack as this runtime allows, and propagates
    every error it does report - unlike sync() above, which exists to be
    called where a failure genuinely does not matter and swallows
    everything.

    Pass the file object whose write is being flushed, if there is one, so
    its buffer is pushed out before the filesystem is synced.

    How far that is, is worth stating rather than assuming. On the pinned
    MicroPython the filesystem layer is not fully fail-closed: the VFS
    adapter calls the block device's writeblocks() and discards its return
    value ("TODO handle error return" in vfs_blockdev.c), pyb.SDCard reports
    a failed write by returning False rather than raising, and the SD
    driver's IOCTL_SYNC is a no-op that always reports success. A physical
    write that the card rejected can therefore reach Python as a successful
    write followed by a successful sync.

    So this raises on every failure the runtime surfaces, but a clean return
    is not proof that the overwrite reached the medium. Closing that gap
    means propagating block-device status through the VFS layer in the
    MicroPython fork, not more checking here.
    """
    if f is not None:
        f.flush()
    if hasattr(os, "sync"):
        os.sync()
        return
    if f is not None and hasattr(os, "fsync"):
        # CPython on platforms without os.sync (notably Windows).
        os.fsync(f.fileno())
        return
    if hasattr(os, "fsync"):
        # A directory-level change (a rename) on a CPython host without
        # os.sync. There is no handle to push and nothing portable to call.
        return
    # No sync call at all. That is a property of the runtime, not a sync
    # that failed, so it is not an error.
    #
    # "MicroPython always has os.sync" is true of the device firmware,
    # which binds it in ports/stm32/moduos.c - but NOT of the unix
    # simulator build, which binds neither os.sync nor os.fsync. Raising
    # here made every save of a recovery phrase fail on the simulator with
    # a traceback, and every secure delete with it, while saying nothing
    # about the hardware. Where there is nothing to sync with, the flush
    # above is genuinely all there is to do.


# An adversarial directory with thousands of entries would otherwise make
# secure_delete_tree() enumerate, walk and remove entries for an unbounded
# amount of time (DoS). A BitBox backup directory has only a few entries, so
# these leave ample room for legitimate trees.
SECURE_DELETE_MAX_ENTRIES = 200
SECURE_DELETE_MAX_DEPTH = 16
SECURE_DELETE_MAX_FILE_BYTES = 4 * 1024 * 1024
SECURE_DELETE_MAX_TOTAL_BYTES = 8 * 1024 * 1024

_TOO_BIG_HINT = "use 'Format entire SD card' instead"


def secure_delete_tree(path):
    """
    secure_delete_file()s every regular file under `path`, then removes the
    now-empty directories, including `path` itself. Used for multi-file
    items such as a BitBox backup directory, where each of the redundant
    copies must be overwritten rather than just unlinked.

    The tree is enumerated and size-checked BEFORE anything is overwritten,
    so a tree exceeding one of the SECURE_DELETE_* caps is rejected up front
    and can never be left half-wiped by a cap. All cap decisions live here
    rather than in secure_delete_file(), which just overwrites the file it
    is given.

    That is a guarantee about the caps, not atomicity: once the overwrite
    loop starts, an I/O error on the third file leaves the first two gone
    and the rest in place. Atomic destruction of a whole FAT tree is not
    something this can offer.
    """
    files = _collect_files(
        path,
        max_entries=SECURE_DELETE_MAX_ENTRIES,
        max_depth=SECURE_DELETE_MAX_DEPTH,
        max_file_bytes=SECURE_DELETE_MAX_FILE_BYTES,
        max_total_bytes=SECURE_DELETE_MAX_TOTAL_BYTES,
    )
    for file_path in files:
        secure_delete_file(file_path)
    _remove_empty_dirs(path)


def _close_entries(entries):
    """
    Closes an os.ilistdir() iterator if it exposes close().

    MicroPython's ilistdir() keeps a directory handle open until it is
    exhausted or closed, and the traversals below deliberately abandon it
    early when a cap is exceeded. Leaving that close to the GC would hold a
    FAT descriptor open across the deletes that follow, so every traversal
    here closes through this one helper.
    """
    close = getattr(entries, "close", None)
    if callable(close):
        close()


def _collect_files(path, max_entries=SECURE_DELETE_MAX_ENTRIES,
                   max_depth=SECURE_DELETE_MAX_DEPTH,
                   max_file_bytes=None, max_total_bytes=None):
    """
    Returns the full paths of every regular file under `path`.

    Walks the tree iteratively with an explicit stack rather than by
    recursion: the device has a small fixed Python stack, and a deep or
    adversarial directory must not be able to exhaust it. Aborts as soon as
    more than `max_entries` entries have been seen, `max_depth` is exceeded
    or - when the size limits are given - a single file or the tree as a
    whole is too large. Modifies and deletes nothing.
    """
    files = []
    entry_count = 0
    total_bytes = 0
    stack = [(path, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise RuntimeError(
                "directory is deeper than %d levels - %s"
                % (max_depth, _TOO_BIG_HINT)
            )
        entries = os.ilistdir(current)
        try:
            for name, entry_type, *_rest in entries:
                if name in (".", ".."):
                    continue
                file_path = "%s/%s" % (current, name)
                entry_count += 1
                # Checked while enumerating, not afterwards: an adversarial
                # directory must not get us to walk (or retain) the whole
                # listing before we notice it is over the cap.
                if entry_count > max_entries:
                    raise RuntimeError(
                        "directory contains more than %d entries - %s"
                        % (max_entries, _TOO_BIG_HINT)
                    )
                if entry_type == 0x4000:
                    stack.append((file_path, depth + 1))
                    continue
                if entry_type != 0x8000:
                    continue
                if max_file_bytes is not None or max_total_bytes is not None:
                    total_bytes += _checked_file_size(
                        file_path, max_file_bytes
                    )
                    if (
                        max_total_bytes is not None
                        and total_bytes > max_total_bytes
                    ):
                        raise RuntimeError(
                            "tree contains more than %d bytes - %s"
                            % (max_total_bytes, _TOO_BIG_HINT)
                        )
                files.append(file_path)
        finally:
            _close_entries(entries)
    return files


def _checked_file_size(file_path, max_file_bytes=None):
    """Returns the size of `file_path`, rejecting unusable stat metadata
    and - when given - any file above `max_file_bytes`."""
    try:
        size = os.stat(file_path)[6]
    except Exception as e:
        raise RuntimeError(
            "Could not inspect file before secure delete: %s" % file_path
        ) from e
    if not is_valid_count(size, allow_zero=True):
        raise RuntimeError("file has invalid size metadata: %s" % file_path)
    if max_file_bytes is not None and size > max_file_bytes:
        raise RuntimeError(
            "file is %d bytes (maximum %d) - %s"
            % (size, max_file_bytes, _TOO_BIG_HINT)
        )
    return size


def _remove_empty_dirs(path, max_depth=SECURE_DELETE_MAX_DEPTH):
    """
    Removes `path` and every directory under it, deepest first.

    Iterative for the same reason as _collect_files(). Must be called after
    secure_delete_file() has unlinked every regular file, so that each
    directory is in fact empty by the time it is removed.
    """
    dirs = []
    stack = [(path, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise RuntimeError(
                "directory is deeper than %d levels - %s"
                % (max_depth, _TOO_BIG_HINT)
            )
        dirs.append(current)
        entries = os.ilistdir(current)
        try:
            for name, entry_type, *_rest in entries:
                if name in (".", ".."):
                    continue
                if entry_type == 0x4000:
                    stack.append(("%s/%s" % (current, name), depth + 1))
        finally:
            _close_entries(entries)
    for directory in reversed(dirs):
        os.rmdir(directory)


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


# errno.EINVAL - same value in MicroPython's uerrno. Spelled out rather than
# imported so this cannot depend on which errno module a build freezes in.
_EINVAL = 22


def _umount_if_mounted(path):
    """
    Unmounts `path`, tolerating it already being unmounted.

    wipe() can now fail partway and be retried, and it reaches here with
    /flash and /qspi already detached from the previous attempt.
    MicroPython raises OSError(EINVAL) for a mountpoint it cannot find in
    the table (mp_vfs_umount in extmod/vfs.c), so a retry would otherwise
    die on the first unmount and never reach the overwrite at all - on the
    critical-error path, forever.

    Only that specific case is swallowed. Any other unmount failure still
    propagates, because it means the filesystem is still attached and the
    wipe must not proceed.
    """
    try:
        os.umount(path)
    except OSError as e:
        if e.args and e.args[0] == _EINVAL:
            return
        raise


# Internal-flash block range overwritten by wipe(), from the disco board
# block map below. Named so that the range written and the minimum geometry
# required to write it cannot drift apart.
WIPE_FIRST_BLOCK = 256
WIPE_LAST_BLOCK = 449


def wipe():
    """
    Blocks map in disco board
    0: MBR
    1   - 255:   reserved
    256 - 447:   internal flash
    448 - 33215: QSPI

    What this does and does not overwrite, precisely, because "wipe"
    suggests more than the block range above delivers:

    * Internal flash (256-447) is overwritten in full. That is where the
      keystore secret, the PIN state and the encryption secret live, so the
      key material itself is destroyed.
    * Of the QSPI only its first blocks (448-449) are overwritten. The
      filesystem there is destroyed with them, but the ~16 MiB behind it -
      wallet descriptors, wallet metadata, host and global settings - is
      not raw-overwritten. Those files are deleted through the filesystem
      above and are stored encrypted under keys derived from the secret in
      the internal flash, so destroying that secret is what makes them
      unrecoverable. This is cryptographic erasure of the QSPI, not an
      overwrite of it, and it is only as good as the internal-flash
      overwrite that precedes it.
    * Volatile memory is not scrubbed. The reboot below is
      pyb.hard_reset() -> NVIC_SystemReset(), which does not clear SRAM,
      and MicroPython's gc_init() only resets the allocation tables rather
      than the heap itself. Secrets held in RAM can therefore survive the
      reset in the physical SRAM until they are overwritten by ordinary
      allocation.
    """
    # delete files normally in simulator
    try:
        delete_recursively(fpath("/flash"))
        delete_recursively(fpath("/qspi"))
    except:
        pass
    # on real hardware overwrite the raw flash blocks
    if not simulator:
        _umount_if_mounted("/flash")
        _umount_if_mounted("/qspi")
        f = pyb.Flash()
        block_size = f.ioctl(5, None)
        block_count = f.ioctl(4, None)
        # Same sanity check the SD erase uses - a driver reporting a bogus
        # block size here would overwrite the wrong amount of flash. The
        # loop below writes a hardcoded block range, so the device must also
        # actually be large enough to contain it; min_blocks makes that a
        # checked precondition rather than an assumption.
        validate_block_geometry(block_size, block_count, "internal flash",
                                min_blocks=WIPE_LAST_BLOCK + 1)
        # One zero-filled block, allocated once before the first write and
        # reused for every block.
        #
        # Zeros rather than random data. NIST SP 800-88 asks for
        # user-addressable data to be replaced with non-sensitive data, not
        # for that data to be random, so a constant pattern is not the
        # weaker choice here - and it matches secure_delete_file() and
        # erase_and_format(), which write zeros for the same reason. What
        # decides it on this path is the dependency: this is the emergency
        # wipe, reached from CriticalErrorWipeImmediately because something
        # already went badly wrong, and os.urandom() puts the RNG
        # peripheral and its driver between that state and the overwrite.
        # A constant pattern needs none of that, allocates once instead of
        # once per block (a MemoryError partway through a wipe is a wipe
        # that did not happen), and is deterministic enough to compare
        # against.
        try:
            zeros = bytes(block_size)
        except MemoryError as e:
            raise RuntimeError(
                "Wiping the device failed: not enough memory to "
                "start the overwrite.\n\nThe device has NOT been "
                "wiped - data may still be present."
            ) from e
        for i in range(WIPE_FIRST_BLOCK, WIPE_LAST_BLOCK + 1):
            result = f.writeblocks(i, zeros)
            # pyb.Flash.writeblocks() returns the integer status rather than
            # raising (storage.c returns MP_OBJ_NEW_SMALL_INT(ret)), so a
            # failed write is silent unless the result is checked.
            if not is_block_op_success(result):
                raise RuntimeError(
                    "Wiping the device failed at block %d (the flash driver "
                    "returned %r).\n\nThe device has NOT been wiped - data "
                    "may still be present." % (i, result)
                )
        # Force the write-behind cache out to flash BEFORE resetting.
        # pyb.Flash writes into a RAM cache (flashbdev.c sets
        # FLASH_FLAG_DIRTY) that is only written out on an explicit
        # BDEV_IOCTL_SYNC or after 5 seconds of idle, and pyb.hard_reset()
        # goes straight to NVIC_SystemReset() without flushing storage. This
        # wipe writes ~200 blocks and resets immediately, so without an
        # explicit sync the entire overwrite could be discarded along with
        # the cache. Making this call is the part that matters. The same
        # ioctl also flushes the QSPI device, whose first blocks are inside
        # the range above (storage_flush() issues BDEV_IOCTL_SYNC and
        # BDEV2_IOCTL_SYNC).
        #
        # The status check below is defensive only, and must not be read as
        # verification that the flush succeeded: on the pinned firmware
        # pyb_flash_ioctl returns a hardcoded 0 for SYNC, and storage_flush()
        # discards the results of both underlying flushes, so a low-level
        # failure cannot reach Python here at all. It is checked anyway
        # because other block devices do report, and because a driver that
        # starts reporting should not be ignored. A read-back would not close
        # the gap either: flash_cache_sector_id is not cleared by the sync,
        # so reads of the most recently written sector still come from the
        # RAM cache (flash_cache_get_addr_for_read) and would confirm nothing
        # about what actually reached the flash.
        result = f.ioctl(3, None)  # MP_BLOCKDEV_IOCTL_SYNC
        if not is_block_op_success(result):
            raise RuntimeError(
                "Wiping the device failed: the overwrite could not be "
                "flushed to flash (the driver returned %r).\n\nThe device "
                "has NOT been reliably wiped." % result
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
