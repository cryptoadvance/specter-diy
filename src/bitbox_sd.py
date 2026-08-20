"""
SD card discovery for native BitBox02 microSD backups.

BitBox02 stores its backups under a fixed "bitbox02" directory at the SD
card root (see ROOTDIR in bitbox02-firmware/src/sd.c: "0:/bitbox02"), each
backup living in its own sub-directory named after its 64-character
lowercase-hex backup id, containing exactly three (normally identical)
backup files.

This module only ever lists directories and opens files for reading. It
never creates, renames, overwrites, or deletes anything on the card - the
directory is only ever mounted read-only from Specter-DIY's point of view
(the mount itself is still read-write at the filesystem level, since
MicroPython's FAT driver doesn't support a read-only mount mode, but no
write operation is ever issued).
"""
import os
import platform

from bitbox_backup import MAX_FILE_SIZE, zeroize


class BitboxSdError(Exception):
    """Raised for any SD-card discovery/read problem. Messages only ever
    name files/directories/counts - never file contents."""


# Matches ROOTDIR in bitbox02-firmware/src/sd.c ("0:/bitbox02").
BITBOX_ROOT_DIRNAME = "bitbox02"
BACKUP_ID_LENGTH = 64
EXPECTED_FILE_COUNT = 3
# Matches LIST_MAX in bitbox02-firmware/src/sd.c - a hard cap on the number
# of directory entries we'll ever enumerate in one listing, so a card with
# an adversarially huge number of entries can't force unbounded memory use
# just from listing a directory.
MAX_LIST_ENTRIES = 200

_HEX_DIGITS = frozenset("0123456789abcdef")

_TYPE_FILE = 0x8000
_TYPE_DIR = 0x4000


def is_valid_backup_dirname(name):
    """A BitBox02 backup directory is named after its 64-character
    lowercase-hex backup id (backup::id() in backup.rs encodes an
    HMAC-SHA256 digest with Rust's hex::encode(), which is always
    lowercase).

    We deliberately only accept an exact lowercase match - stricter than
    the BitBox02 firmware itself, which will attempt to load any
    directory entry regardless of name and simply fails later if it
    doesn't contain 3 valid files. Being stricter here means we never have
    to decide how to normalize a mixed-case or uppercase directory name
    for subsequent path lookups on a case-insensitive FAT filesystem, and
    it avoids wasting time/memory attempting to load directories that are
    certainly not BitBox backups.
    """
    if len(name) != BACKUP_ID_LENGTH:
        return False
    if "/" in name or "\\" in name:
        return False
    return all(c in _HEX_DIGITS for c in name)


def _sd_root():
    return platform.fpath("/sd")


def _bitbox_root():
    return _sd_root() + "/" + BITBOX_ROOT_DIRNAME


def _listdir_typed(path):
    """Returns a list of (name, entry_type) for the direct children of path,
    where entry_type is the raw os.ilistdir() type field (_TYPE_DIR /
    _TYPE_FILE / something else). Callers compare it explicitly rather than
    getting a pre-reduced is_dir flag, so an unexpected entry type stays
    distinguishable from "regular file".

    Raises BitboxSdError if the path can't be listed at all (e.g. it
    doesn't exist)."""
    entries = []
    listing = os.ilistdir(path)
    try:
        for entry in listing:
            name = entry[0]
            if name in (".", ".."):
                continue
            if len(entries) >= MAX_LIST_ENTRIES:
                raise BitboxSdError(
                    "directory has more than %d entries" % MAX_LIST_ENTRIES
                )
            entries.append((name, entry[1]))
    except OSError as e:
        raise BitboxSdError("could not list directory: %s" % path) from e
    finally:
        # We may abandon the listing early (entry limit); release the
        # underlying directory handle instead of leaving it to the GC.
        # MicroPython's ilistdir iterator has no close(), hence the guard.
        close = getattr(listing, "close", None)
        if close is not None:
            close()
    return entries


def list_backup_dirs():
    """Returns a sorted list of candidate backup directory names (64
    lowercase hex characters) found directly under <sdroot>/bitbox02/.

    This only checks the directory *name* - it does not open or validate
    any files. Call read_backup_files() on a chosen name to actually load
    and (via bitbox_backup) validate its contents.

    The SD card must already be mounted (see platform.sdcard). Returns an
    empty list if the bitbox02 directory doesn't exist - that's not an
    error, it just means there are no BitBox backups on this card.
    """
    root = _bitbox_root()
    try:
        os.stat(root)
    except OSError:
        # bitbox02/ doesn't exist at all - no backups, not an error. Checked
        # separately (rather than by catching BitboxSdError below) so a
        # real problem while listing an existing directory - such as the
        # MAX_LIST_ENTRIES guard tripping - is never mistaken for "no
        # backups" and silently swallowed.
        return []
    entries = _listdir_typed(root)
    names = [
        name for name, entry_type in entries
        if entry_type == _TYPE_DIR and is_valid_backup_dirname(name)
    ]
    names.sort()
    return names


def read_backup_files(dir_name):
    """Reads the files inside <sdroot>/bitbox02/<dir_name>/ read-only.

    Requires the directory to contain exactly EXPECTED_FILE_COUNT (3)
    entries, all of them regular files, each at most MAX_FILE_SIZE bytes.
    Anything else (wrong file count, a sub-directory, an oversized file,
    a read error) raises BitboxSdError rather than guessing which files
    to use - the caller must not silently ignore unexpected SD card
    contents.

    Returns a list of bytearrays (mutable, so callers can zeroize() them
    once they've derived what they need - the file contents include the
    BIP-39 entropy in plaintext).
    """
    if not is_valid_backup_dirname(dir_name):
        raise BitboxSdError("invalid backup directory name")

    dir_path = _bitbox_root() + "/" + dir_name
    entries = _listdir_typed(dir_path)
    if len(entries) != EXPECTED_FILE_COUNT:
        raise BitboxSdError(
            "expected exactly %d files in backup directory, found %d"
            % (EXPECTED_FILE_COUNT, len(entries))
        )

    filenames = []
    for name, entry_type in entries:
        # Require a *regular file* positively, rather than merely "not a
        # directory": an entry of any other type (whatever the filesystem
        # driver may report) is rejected instead of being read blindly.
        if entry_type != _TYPE_FILE:
            raise BitboxSdError(
                "backup directory must contain only regular files"
            )
        filenames.append(name)
    filenames.sort()

    contents = []
    try:
        for name in filenames:
            full_path = dir_path + "/" + name
            try:
                size = os.stat(full_path)[6]
            except OSError as e:
                raise BitboxSdError("could not stat backup file") from e
            if size > MAX_FILE_SIZE:
                raise BitboxSdError("backup file exceeds %d byte limit" % MAX_FILE_SIZE)
            try:
                with open(full_path, "rb") as f:
                    data = bytearray(f.read(MAX_FILE_SIZE + 1))
            except OSError as e:
                raise BitboxSdError("could not read backup file") from e
            if len(data) > MAX_FILE_SIZE:
                # Defends against a TOCTOU race where the file grew between
                # the os.stat() size check above and the read.
                zeroize(data)
                raise BitboxSdError("backup file exceeds %d byte limit" % MAX_FILE_SIZE)
            contents.append(data)
    except BitboxSdError:
        # Nothing is returned to the caller, so wipe whatever we already
        # read - a partially-read backup still contains plaintext entropy.
        for buf in contents:
            zeroize(buf)
        raise
    return contents
