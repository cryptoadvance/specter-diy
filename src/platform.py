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
    """True for a plain positive integer (or non-negative with allow_zero).
    Rejects bools, which are ints in Python."""
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return value >= 0 if allow_zero else value > 0


# Upper bound for a reported block size: the wipe buffer can never be
# smaller than one block, so a device reporting more than this cannot be
# wiped in bounded memory. Real SD cards and the internal flash report 512.
MAX_SANE_BLOCK_SIZE = 64 * 1024


def is_block_op_success(result):
    """
    True if a block-device call reported success. Conventions differ:
    pyb.SDCard.writeblocks() returns True/False, pyb.Flash's returns the
    integer status (0 or negative errno), generic block devices return
    None. Anything unrecognised fails closed: a block that was never
    written must never count as a successful wipe.
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
    Rejects bogus block-device geometry before a destructive,
    geometry-driven operation: non-positive or non-integer values, a block
    size too large to buffer, and - via min_blocks - a device too small
    for a fixed block range the caller is about to write.
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


# erase_and_format() reports exactly three failure outcomes; these are the
# shared tails of the two destructive ones.
_HALF_OVERWRITTEN = (
    "The card is now in a half-overwritten, unusable state and must be "
    "reformatted before it can be used again."
)
_INTERRUPTED = (
    "Secure erase was interrupted before completion. " + _HALF_OVERWRITTEN
)
_NO_FILESYSTEM = (
    "The card's old data has been wiped, but it has no valid filesystem "
    "and must be reformatted on a computer before it can be used."
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
        mount_attempted = False
        try:
            powered = self._sd.power(True)
            if powered is False:
                raise RuntimeError("Could not initialize SD card")
            mount_attempted = True
            os.mount(self._sd, "/sd")
            self._mounted = True
        except Exception:
            # Do not power down while VFS state is unknown. If os.mount()
            # was attempted, first detach /sd (or positively establish
            # that it was never mounted); otherwise no VFS mount exists.
            detached = not mount_attempted
            if mount_attempted:
                try:
                    _umount_if_mounted("/sd")
                    detached = True
                except Exception as cleanup_error:
                    print(cleanup_error)
            if detached:
                try:
                    self._sd.power(False)
                except Exception as cleanup_error:
                    print(cleanup_error)
                try:
                    if self._led is not None:
                        self._led.off()
                except Exception as cleanup_error:
                    print(cleanup_error)
            raise

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
            # Keep the first error for the caller, but always attempt both
            # cleanup operations: a failed sync must not skip the umount.
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
            # Invariant: never power down the card while the VFS still has
            # /sd mounted - that would leave the VFS pointing at a dead
            # block device. So only clear _mounted after a real umount (a
            # later call must be able to retry), and only cut power once
            # the mount is gone or the card is positively known absent.
            if unmounted:
                self._mounted = False
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
        True only when the card is POSITIVELY known to be gone. A presence
        probe that raises proves nothing (the bus may have glitched), so it
        counts as "still there" - otherwise a double fault (umount fails
        AND the probe fails) would cut power while /sd is still mounted.
        Never raises: a failing probe must not mask an in-flight error.
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
        """False only in the simulator build (see the module-level
        `simulator` flag), where SDCard is constructed without a block
        device and /sd is an ordinary host directory."""
        return self._sd is not None

    async def erase_and_format(self, progress_cb=None):
        """
        Overwrites every block of the card with zeros, then creates a
        fresh, empty FAT filesystem. Irreversible: destroys the whole
        card, not only the files Specter-DIY created. Best-effort logical
        sanitization, not forensic erasure - see secure_delete_file().

        Only three failure outcomes exist, and they are reported as such:
        nothing was changed (any failure before the first block write),
        the card is half-overwritten and must be reformatted (any failure
        or task cancellation once the overwrite has begun - never reported
        as success, never followed by mkfs), or the overwrite completed
        but filesystem creation failed. The user-facing confirmation and
        the "do not remove the card" warning belong to the caller.

        progress_cb(fraction), if given, is awaited roughly every 128 KiB
        of progress (not once per writeblocks() call - the write buffer can
        be forced down to a single block on a tight heap, and redrawing the
        bar every 512 bytes would be its own slowdown). The event loop is
        yielded to on the same cadence either way - a progress_cb that
        never awaits (e.g. one that only redraws a progress bar) would
        otherwise starve the GUI task for the whole erase - so a failing
        progress_cb is handled separately from that yield.

        On a fragmented heap the write buffer is stepped down (128 KiB,
        64 KiB, ... , finally one block) until one size allocates. A
        smaller buffer only makes the erase slower, never less complete;
        "not enough memory to start" is reported only when even a
        single-block buffer cannot be allocated, and in that case nothing
        on the card has been touched.
        """
        if not self.is_present:
            raise RuntimeError("SD card is not present")
        self.unmount()
        if not self.has_block_device:
            # Simulator build: nothing to overwrite at block level - clear
            # the directory that stands in for the card instead.
            delete_recursively(fpath("/sd"))
            if progress_cb is not None:
                await progress_cb(1.0)
            return
        completed = False
        if self._led is not None:
            self._led.on()
        try:
            try:
                powered = self._sd.power(True)
                # pyb.SDCard.power() reports a failed power-on by returning
                # False rather than raising; block devices without a status
                # return None. Only an explicit False counts as failure.
                if powered is False:
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
            # One zero-filled buffer, allocated BEFORE the first destructive
            # write and reused for every chunk: a MemoryError here costs
            # nothing (no block has been touched), while one mid-loop would
            # leave a half-overwritten card. Zeros are a complete overwrite
            # for sanitization - see secure_delete_file() for why one pass
            # of zeros, never random.
            #
            # 128 KiB amortizes SD writes, but a fragmented MicroPython heap
            # cannot always spare one contiguous 128 KiB block - that is the
            # "Not enough memory to start the secure erase" seen on real
            # hardware. Rather than abort the whole operation, step the
            # request down (128, 64, 32, ... KiB, then a single block) and
            # keep the largest buffer that allocates. block_size is capped
            # by the geometry check above, so every candidate is bounded.
            buf = None
            alloc_error = None
            buf_blocks = max(1, (128 * 1024) // block_size)
            while True:
                try:
                    buf = bytearray(buf_blocks * block_size)
                    break
                except MemoryError as e:
                    alloc_error = e
                    gc.collect()
                    if buf_blocks <= 1:
                        break
                    buf_blocks = max(1, buf_blocks // 2)
            if buf is None:
                raise RuntimeError(
                    "Not enough memory to start the secure erase. No data "
                    "has been changed - reboot the device and try again."
                ) from alloc_error
            view = memoryview(buf)
            data = None
            # Run gc and yield to the GUI roughly every 128 KiB, however
            # small the write buffer had to be: a single-block buffer would
            # otherwise gc.collect() and redraw the bar on every 512-byte
            # write and crawl for that reason alone.
            report_blocks = max(buf_blocks, max(1, (128 * 1024) // block_size))
            next_report = report_blocks
            for start in range(0, block_count, buf_blocks):
                n = min(buf_blocks, block_count - start)
                result = None
                try:
                    # A memoryview slice for the short final chunk, so it
                    # does not allocate a copy of the buffer.
                    data = buf if n == buf_blocks else view[:n * block_size]
                    result = self._sd.writeblocks(start, data)
                except OSError as e:
                    raise RuntimeError(
                        "Could not write to the SD card during secure "
                        "erase (card may have been removed):\n\n%s\n\n%s"
                        % (e, _HALF_OVERWRITTEN)
                    ) from e
                except MemoryError as e:
                    # MemoryError is not an OSError; without its own
                    # handler it would escape as a raw traceback.
                    raise RuntimeError(_INTERRUPTED) from e
                if not is_block_op_success(result):
                    raise RuntimeError(
                        "Could not write to the SD card during secure "
                        "erase (block device returned %r). %s"
                        % (result, _HALF_OVERWRITTEN)
                    )
                done = start + n
                if done < next_report and done < block_count:
                    continue
                next_report = done + report_blocks
                gc.collect()
                progress_error = None
                if progress_cb is not None:
                    try:
                        await progress_cb(done / block_count)
                    except asyncio.CancelledError as e:
                        raise RuntimeError(_INTERRUPTED) from e
                    except Exception as e:
                        # A broken progress callback must neither abort a
                        # half-done erase nor skip the yield below.
                        progress_error = e
                try:
                    await asyncio.sleep_ms(0)
                except asyncio.CancelledError as e:
                    raise RuntimeError(_INTERRUPTED) from e
                if progress_error is not None:
                    print(progress_error)
            # Release the erase buffer BEFORE mkfs() allocates its own
            # VFS/FatFs structures.
            data = None
            view = None
            buf = None
            gc.collect()
            try:
                os.VfsFat.mkfs(self._sd)
            except OSError as e:
                raise RuntimeError(
                    "Overwrite completed, but creating a fresh filesystem "
                    "failed:\n\n%s\n\n%s" % (e, _NO_FILESYSTEM)
                ) from e
            except MemoryError as e:
                raise RuntimeError(
                    "Overwrite completed, but there was not enough memory "
                    "to create a fresh filesystem. %s" % _NO_FILESYSTEM
                ) from e
            completed = True
        finally:
            # Cleanup must never supplant an in-flight failure: an
            # exception raised here would replace the one being
            # propagated. Surface a cleanup failure only when there is
            # nothing more important to report - same rule as unmount().
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

    With `secure=True` each regular file goes through secure_delete_file()
    (overwrite-then-unlink) rather than os.remove(). Use it for trees that
    hold secrets: encrypted wallet descriptors in QSPI, PSBT scratch in
    the SDRAM ramdisk. Unlike secure_delete_tree() there are no traversal
    caps - the trees deleted here are Specter's own app folders, bounded
    by what Specter itself wrote.
    """
    # remove trailing slash
    if path is None:
        raise RuntimeError("Path is not specified")
    path = path.rstrip("/")
    files = os.ilistdir(path)
    try:
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
    finally:
        _close_entries(files)

    files = os.ilistdir(path)
    try:
        num_of_files = sum(1 for _ in files)
    finally:
        _close_entries(files)
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
    Overwrites a file's contents with one pass of zeros, flushes, and only
    then unlinks it. Returns the number of bytes overwritten.

    A plain os.remove() only unlinks the directory entry - the old bytes
    sit in free space until reused, readable with an undelete tool. This
    closes that gap for individual files; SDCard.erase_and_format() is the
    whole-card equivalent.

    One zero pass is deliberate: NIST SP 800-88 asks for user-addressable
    data to be replaced with non-sensitive data - random is not required,
    extra passes are a magnetic-media practice, and os.urandom() costs one
    busy-waiting rng_get() per byte on this hardware. Never use the RNG in
    a destructive path.

    The size is read from the open handle itself (seek/tell), not stat,
    so a stat/open gap cannot redirect the overwrite. Every write is
    checked, and a failed overwrite or sync means NO unlink.

    Best-effort, not forensic: this overwrites the file's current logical
    allocation. Wear-levelling flash can retain historic physical copies
    the controller no longer exposes; only physical destruction rules
    that out, on SD cards and internal flash alike. Persistence of the
    overwrite is only as strong as strict_sync() is on this runtime.
    """
    zeros = bytes(SECURE_DELETE_CHUNK)
    view = memoryview(zeros)
    with open(path, "r+b") as f:
        f.seek(0, 2)  # seek to end
        size = f.tell()
        if not is_valid_count(size, allow_zero=True):
            raise OSError("invalid file size during secure delete: %r" % size)
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
    Flushes as far down the stack as this runtime allows, propagating
    every error it reports - unlike sync(), which deliberately swallows
    everything for paths where a failure does not matter.

    A clean return is not proof the overwrite reached the medium: on the
    pinned MicroPython the VFS adapter discards writeblocks() results
    ("TODO handle error return" in vfs_blockdev.c) and pyb.SDCard's
    IOCTL_SYNC is a no-op. That gap can only be closed in the MicroPython
    fork, not here.
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
    # No sync call at all - true of the unix simulator build, which binds
    # neither os.sync nor os.fsync. That is a property of the runtime, not
    # a failed sync, so it is not an error.


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
    so a tree over one of the SECURE_DELETE_* caps is rejected up front and
    can never be left half-wiped by a cap. All cap decisions live here -
    secure_delete_file() just overwrites the file it is given.

    That is a guarantee about the caps, not atomicity: an I/O error
    mid-tree leaves the already-processed files gone and the rest in
    place. Atomic destruction of a whole FAT tree is not offered.
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
    """Closes an os.ilistdir() iterator if it exposes close(): MicroPython
    keeps a directory handle open until the iterator is exhausted or
    closed, and the traversals below deliberately abandon it early."""
    close = getattr(entries, "close", None)
    if callable(close):
        close()


def _collect_files(path, max_entries=SECURE_DELETE_MAX_ENTRIES,
                   max_depth=SECURE_DELETE_MAX_DEPTH,
                   max_file_bytes=None, max_total_bytes=None):
    """
    Returns the full paths of every regular file under `path`. Iterative
    (explicit stack) because the device has a small fixed Python stack.
    Aborts as soon as a cap is exceeded - an adversarial directory must
    not be walked or retained beyond the cap. Modifies nothing.
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
                # Checked mid-enumeration, not afterwards: an adversarial
                # directory must not be walked (or retained) beyond the cap.
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
    """Removes `path` and every directory under it, deepest first.
    Iterative for the same reason as _collect_files(). Call only after the
    files are gone, so each directory really is empty."""
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
    Unmounts `path`, tolerating it already being unmounted. wipe() can
    fail partway and be retried, reaching here with the filesystem already
    detached by the previous attempt; MicroPython raises OSError(EINVAL)
    for a mountpoint not in the mount table (mp_vfs_umount in vfs.c).

    Only that specific case is swallowed. Any other unmount failure still
    propagates - the filesystem is still attached and the wipe must not
    proceed.
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

    Exactly what this destroys, because "wipe" suggests more than it does:

    * Internal flash (256-447) is overwritten in full - keystore secret,
      PIN state and the encryption secret, i.e. the key material itself.
    * Of the QSPI only its filesystem blocks (448-449) are overwritten. The
      filesystem entries are also logically removed above before the raw
      overwrite. The ~16 MiB behind them is not physically overwritten:
      host/global settings and other device-state data use keys derived from
      the device secret, but wallet descriptors and metadata use the
      seed-derived idkey (m/0x1D') and do not become cryptographically erased
      merely because the device secret is destroyed. Without the original
      seed those wallet files remain undecryptable, but this is not a blanket
      physical or forensic erasure of QSPI.
    * Volatile memory is not scrubbed: pyb.hard_reset() does not clear
      SRAM, so secrets held in RAM can survive the reset until ordinary
      allocation overwrites them.
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
        # The loop writes a hardcoded block range, so the device must
        # provably contain it - a checked precondition, not an assumption.
        validate_block_geometry(block_size, block_count, "internal flash",
                                min_blocks=WIPE_LAST_BLOCK + 1)
        # One zero-filled block, allocated once before the first write.
        # Zeros, never random: this is the emergency wipe, reached from
        # CriticalErrorWipeImmediately because something already went
        # wrong - it must not depend on the RNG peripheral and driver
        # still working. See secure_delete_file() for the policy.
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
            # pyb.Flash.writeblocks() returns the integer status instead
            # of raising, so a failed write is silent unless checked.
            if not is_block_op_success(result):
                raise RuntimeError(
                    "Wiping the device failed at block %d (the flash driver "
                    "returned %r).\n\nThe device has NOT been wiped - data "
                    "may still be present." % (i, result)
                )
        # Force the write-behind cache out to flash BEFORE resetting:
        # pyb.Flash caches writes in RAM (flashbdev.c) that only an
        # explicit SYNC ioctl flushes, and pyb.hard_reset() resets without
        # flushing. Without this call the whole overwrite above could be
        # discarded along with the cache, and the reboot would present an
        # unwiped device as wiped.
        # The status return is defensive only: on the pinned firmware the
        # SYNC ioctl reports a hardcoded success and discards the
        # underlying flush results, so a low-level failure cannot reach
        # Python here. Checked anyway - a driver that starts reporting
        # must not be ignored - but a clean return is not proof the data
        # reached the flash (see strict_sync() for the same VFS gap).
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
