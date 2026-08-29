import sys

if sys.implementation.name != 'micropython':
    from native_support import setup_native_stubs

    setup_native_stubs()

from unittest import TestCase

import pyb
import platform
from tests.util import clear_testdir


# The end of the QSPI region is no longer a platform constant - wipe()
# reads it from the block device. Tests still pin the value the block map
# was verified against, so a change in the wiped range stays visible here.
VERIFIED_QSPI_END_BLOCK = 33216


class FakeFlash:
    """
    Records every writeblocks()/ioctl() call - including their relative
    order in a shared `events` log - so tests can check exactly which
    blocks were (or were not) overwritten, what data was written, and
    that write/sync/reboot happen in the right order, without touching
    real hardware.
    """

    def __init__(self, block_size=512, block_count=None, fail_at_blocks=None,
                 raise_at_blocks=None, fail_sync=False, sync_error_code=None):
        self.block_size = block_size
        self.block_count = block_count if block_count is not None else VERIFIED_QSPI_END_BLOCK
        self.calls = []  # list of (block_num, num_blocks)
        self.fail_at_blocks = set(fail_at_blocks or [])
        self.raise_at_blocks = set(raise_at_blocks or [])
        self.fail_sync = fail_sync
        self.sync_error_code = sync_error_code
        self.ioctl_calls = []
        self.events = []  # shared write/sync (and, externally, reboot) order log

    def ioctl(self, cmd, arg):
        self.ioctl_calls.append(cmd)
        if cmd == 5:  # MP_BLOCKDEV_IOCTL_BLOCK_SIZE
            return self.block_size
        if cmd == 4:  # MP_BLOCKDEV_IOCTL_BLOCK_COUNT
            return self.block_count
        if cmd == 3:  # MP_BLOCKDEV_IOCTL_SYNC
            self.events.append(("sync",))
            if self.fail_sync:
                raise OSError("simulated sync failure")
            if self.sync_error_code is not None:
                return self.sync_error_code
            return 0
        return None

    def writeblocks(self, block_num, buf):
        assert len(buf) % self.block_size == 0
        n = len(buf) // self.block_size
        self.calls.append((block_num, n))
        self.events.append(("write", block_num, n, bytes(buf)))
        if block_num in self.raise_at_blocks:
            raise OSError("simulated flash failure")
        if block_num in self.fail_at_blocks:
            return -5  # negative errno == failure, per block protocol
        return 0

    def written_blocks(self):
        """Returns the set of individual block numbers passed a buffer."""
        blocks = set()
        for start, n in self.calls:
            blocks.update(range(start, start + n))
        return blocks


class BlockMapConstantsTest(TestCase):
    """
    Pins down the verified hardware block map (see platform.py) so a
    future edit can't silently reintroduce an off-by-one or shrink the
    wiped range.
    """

    def test_internal_flash_range(self):
        self.assertEqual(platform.INTERNAL_FLASH_START_BLOCK, 256)
        self.assertEqual(platform.INTERNAL_FLASH_END_BLOCK, 448)
        # 192 blocks * 512 bytes == 96 KiB == FLASH_MEM_SEG1 on STM32F469xx
        self.assertEqual(
            platform.INTERNAL_FLASH_END_BLOCK - platform.INTERNAL_FLASH_START_BLOCK,
            192,
        )

    def test_qspi_start(self):
        # Only the start of the QSPI region is a constant. Its end comes
        # from the block device at run time, so there is nothing here to
        # go stale against a differently sized chip.
        self.assertEqual(platform.QSPI_START_BLOCK, 448)
        # 32768 blocks * 512 bytes == 16 MiB == the on-board QSPI chip
        self.assertEqual(
            VERIFIED_QSPI_END_BLOCK - platform.QSPI_START_BLOCK,
            32768,
        )

    def test_no_hardcoded_geometry_left_in_platform(self):
        # Guards the point of this change: block size and total block
        # count must not creep back in as module constants.
        self.assertFalse(hasattr(platform, "FLASH_BLOCK_SIZE"))
        self.assertFalse(hasattr(platform, "QSPI_END_BLOCK"))

    def test_qspi_starts_immediately_after_internal_flash(self):
        self.assertEqual(platform.QSPI_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK)

    def test_reserved_region_is_excluded(self):
        # blocks 0-255 (fake MBR + reserved/bootloader sectors) must never
        # be part of either wiped range
        self.assertGreaterEqual(platform.INTERNAL_FLASH_START_BLOCK, 256)


class SecureOverwriteBlocksTest(TestCase):
    def test_wipes_full_range_with_no_gaps_or_overrun(self):
        f = FakeFlash()
        ok = platform._secure_overwrite_blocks(
            f, platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK, 512
        )
        self.assertTrue(ok)
        self.assertEqual(
            f.written_blocks(),
            set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK)),
        )
        # first and last block of the range must be included (off-by-one guard)
        self.assertIn(platform.INTERNAL_FLASH_START_BLOCK, f.written_blocks())
        self.assertIn(platform.INTERNAL_FLASH_END_BLOCK - 1, f.written_blocks())
        # the end block itself (exclusive bound) must never be written
        self.assertNotIn(platform.INTERNAL_FLASH_END_BLOCK, f.written_blocks())

    def test_wipes_full_qspi_range(self):
        f = FakeFlash()
        ok = platform._secure_overwrite_blocks(
            f, platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK, 512
        )
        self.assertTrue(ok)
        self.assertEqual(
            f.written_blocks(),
            set(range(platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK)),
        )
        self.assertIn(platform.QSPI_START_BLOCK, f.written_blocks())
        self.assertIn(VERIFIED_QSPI_END_BLOCK - 1, f.written_blocks())
        self.assertNotIn(VERIFIED_QSPI_END_BLOCK, f.written_blocks())

    def test_never_touches_blocks_outside_requested_range(self):
        f = FakeFlash()
        platform._secure_overwrite_blocks(f, 300, 320, 512)
        for start, n in f.calls:
            self.assertGreaterEqual(start, 300)
            self.assertLessEqual(start + n, 320)

    def test_uses_given_block_size_for_buffers(self):
        f = FakeFlash(block_size=4096)
        platform._secure_overwrite_blocks(f, 0, 32, 4096, chunk_blocks=8)
        for start, n in f.calls:
            self.assertLessEqual(n * 4096, 8 * 4096)

    def test_chunking_never_loads_whole_region_at_once(self):
        f = FakeFlash()
        platform._secure_overwrite_blocks(f, 0, 1000, 512, chunk_blocks=16)
        for _, n in f.calls:
            self.assertLessEqual(n, 16)
        self.assertGreater(len(f.calls), 1)

    def test_write_failure_does_not_stop_the_wipe(self):
        f = FakeFlash(fail_at_blocks={16})
        ok = platform._secure_overwrite_blocks(f, 0, 64, 512, chunk_blocks=16)
        self.assertFalse(ok)
        # every chunk should still have been attempted despite the failure
        self.assertEqual(f.written_blocks(), set(range(0, 64)))

    def test_write_exception_does_not_stop_the_wipe(self):
        f = FakeFlash(raise_at_blocks={32})
        ok = platform._secure_overwrite_blocks(f, 0, 64, 512, chunk_blocks=16)
        self.assertFalse(ok)
        self.assertEqual(f.written_blocks(), set(range(0, 64)))

    def test_writes_a_fixed_pattern_not_random_data(self):
        # os.urandom() on this port draws one hardware RNG sample per byte
        # (~10us each), which would make a 16 MiB QSPI wipe take minutes
        # just to generate the buffers. A fixed pattern is just as
        # effective against the "read the chip directly" threat model,
        # since every touched sector gets erased and reprogrammed either
        # way, so the loop must not depend on true randomness.
        f = FakeFlash()
        platform._secure_overwrite_blocks(f, 0, 64, 512, chunk_blocks=16)
        for _, _, _, buf in f.events:
            self.assertEqual(buf, bytes(len(buf)))

    def test_reuses_one_buffer_instead_of_allocating_per_chunk(self):
        f = FakeFlash()
        platform._secure_overwrite_blocks(f, 0, 64, 512, chunk_blocks=16)
        full_chunks = [buf for _, _, n, buf in f.events if n == 16]
        self.assertGreater(len(full_chunks), 1)
        # every full-size chunk must be the exact same underlying bytes
        # object, not a freshly allocated one each iteration
        self.assertTrue(all(buf is full_chunks[0] for buf in full_chunks))


class WipeSimulatorTest(TestCase):
    def setUp(self):
        clear_testdir()
        self.rebooted = False

        def fake_reboot():
            self.rebooted = True

        self._orig_reboot = platform.reboot
        platform.reboot = fake_reboot

        def fail_if_called(*args, **kwargs):
            raise AssertionError("hardware block device must not be touched in simulator mode")

        self._orig_flash = getattr(pyb, "Flash", None)
        pyb.Flash = fail_if_called

    def tearDown(self):
        platform.reboot = self._orig_reboot
        if self._orig_flash is None:
            del pyb.Flash
        else:
            pyb.Flash = self._orig_flash
        clear_testdir()

    def test_wipe_deletes_files_and_never_touches_hardware(self):
        platform.maybe_mkdir(platform.fpath("/flash"))
        platform.maybe_mkdir(platform.fpath("/qspi"))
        with open(platform.fpath("/flash/secret.txt"), "w") as f:
            f.write("do not recover me")
        with open(platform.fpath("/qspi/wallet.json"), "w") as f:
            f.write("{}")

        platform.wipe()

        self.assertTrue(self.rebooted)
        self.assertFalse(platform.file_exists(platform.fpath("/flash/secret.txt")))
        self.assertFalse(platform.file_exists(platform.fpath("/qspi/wallet.json")))


class WipeHardwareTest(TestCase):
    """
    Exercises the `if not simulator:` branch of wipe() by flipping the
    module-level `simulator` flag, without requiring real STM32 hardware.
    """

    def setUp(self):
        clear_testdir()
        self._orig_simulator = platform.simulator
        platform.simulator = False

        self.fake = None
        self.rebooted = False

        def fake_reboot():
            self.rebooted = True
            if self.fake is not None:
                self.fake.events.append(("reboot",))

        self._orig_reboot = platform.reboot
        platform.reboot = fake_reboot

        self._orig_umount = platform.os.umount if hasattr(platform.os, "umount") else None
        self.umounted = []
        platform.os.umount = lambda path: self.umounted.append(path)

    def tearDown(self):
        platform.simulator = self._orig_simulator
        platform.reboot = self._orig_reboot
        if self._orig_umount is not None:
            platform.os.umount = self._orig_umount
        else:
            del platform.os.umount
        if hasattr(pyb, "Flash"):
            del pyb.Flash
        clear_testdir()

    def test_successful_wipe_overwrites_both_regions_and_reboots(self):
        fake = FakeFlash()
        self.fake = fake
        pyb.Flash = lambda: fake

        platform.wipe()

        self.assertTrue(self.rebooted)
        self.assertEqual(sorted(self.umounted), ["/flash", "/qspi"])
        expected = set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK))
        expected |= set(range(platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK))
        self.assertEqual(fake.written_blocks(), expected)
        # never touch the fake MBR or the reserved/bootloader blocks
        for start, n in fake.calls:
            self.assertGreaterEqual(start, 256)
        # the write-behind cache must be forced out to physical flash
        # before reboot, or the last dirty sector could be lost on reset -
        # once after the internal-flash loop, once after the QSPI loop
        self.assertEqual(fake.ioctl_calls.count(platform.MP_BLOCKDEV_IOCTL_SYNC), 2)

    def test_failed_wipe_raises_and_does_not_reboot(self):
        fake = FakeFlash(fail_at_blocks={platform.QSPI_START_BLOCK})
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        # a partial wipe must never look like a successful one
        self.assertFalse(self.rebooted)

    def test_flash_unmount_failure_still_overwrites_and_raises(self):
        def failing_umount(path):
            if path == "/flash":
                raise OSError("simulated unmount failure")
            self.umounted.append(path)

        platform.os.umount = failing_umount
        fake = FakeFlash()
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        # a failed /flash unmount must not be silently treated as success
        self.assertFalse(self.rebooted)
        # but the raw overwrite must still have been attempted for both
        # regions, to destroy as much data as safely possible
        expected = set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK))
        expected |= set(range(platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK))
        self.assertEqual(fake.written_blocks(), expected)
        # /qspi unmount is independent and should still have happened
        self.assertEqual(self.umounted, ["/qspi"])

    def test_qspi_unmount_failure_still_overwrites_and_raises(self):
        def failing_umount(path):
            if path == "/qspi":
                raise OSError("simulated unmount failure")
            self.umounted.append(path)

        platform.os.umount = failing_umount
        fake = FakeFlash()
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        self.assertFalse(self.rebooted)
        expected = set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK))
        expected |= set(range(platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK))
        self.assertEqual(fake.written_blocks(), expected)
        # /flash unmount is independent and should still have happened
        self.assertEqual(self.umounted, ["/flash"])

    def test_both_unmounts_failing_still_overwrites_and_raises(self):
        def failing_umount(path):
            raise OSError("simulated unmount failure")

        platform.os.umount = failing_umount
        fake = FakeFlash()
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        self.assertFalse(self.rebooted)
        expected = set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK))
        expected |= set(range(platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK))
        self.assertEqual(fake.written_blocks(), expected)

    def test_sync_exception_raises_and_does_not_reboot(self):
        fake = FakeFlash(fail_sync=True)
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        self.assertFalse(self.rebooted)
        # the overwrite itself must still have completed fully
        expected = set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK))
        expected |= set(range(platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK))
        self.assertEqual(fake.written_blocks(), expected)

    def test_sync_error_return_code_raises_and_does_not_reboot(self):
        # A failed sync doesn't have to raise - the pinned driver can also
        # just hand back a nonzero/negative-errno return code. That must
        # be treated as a failure too, not just an exception.
        fake = FakeFlash(sync_error_code=-5)
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        self.assertFalse(self.rebooted)
        expected = set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK))
        expected |= set(range(platform.QSPI_START_BLOCK, VERIFIED_QSPI_END_BLOCK))
        self.assertEqual(fake.written_blocks(), expected)

    def test_larger_block_size_is_taken_from_the_device(self):
        # Block size is read back, not assumed: a device reporting 4096
        # must still be wiped, using its own size rather than refused.
        fake = FakeFlash(block_size=4096,
                         block_count=platform.QSPI_START_BLOCK + 64)
        self.fake = fake
        pyb.Flash = lambda: fake

        platform.wipe()

        self.assertTrue(self.rebooted)
        for _start, _n, buf in [e[1:] for e in fake.events if e[0] == "write"]:
            self.assertEqual(len(buf) % 4096, 0)

    def test_smaller_chip_is_wiped_to_its_reported_end(self):
        # A chip smaller than the one the map was verified against used
        # to abort the whole wipe. Wiping everything the device actually
        # has is better than leaving all of it behind.
        end = VERIFIED_QSPI_END_BLOCK - 4096
        fake = FakeFlash(block_count=end)
        self.fake = fake
        pyb.Flash = lambda: fake

        platform.wipe()

        self.assertTrue(self.rebooted)
        expected = set(range(platform.INTERNAL_FLASH_START_BLOCK, platform.INTERNAL_FLASH_END_BLOCK))
        expected |= set(range(platform.QSPI_START_BLOCK, end))
        self.assertEqual(fake.written_blocks(), expected)
        self.assertNotIn(end, fake.written_blocks())

    def test_larger_chip_is_wiped_to_its_reported_end(self):
        end = VERIFIED_QSPI_END_BLOCK + 1024
        fake = FakeFlash(block_count=end)
        self.fake = fake
        pyb.Flash = lambda: fake

        platform.wipe()

        self.assertTrue(self.rebooted)
        self.assertIn(end - 1, fake.written_blocks())
        self.assertNotIn(end, fake.written_blocks())

    def test_device_not_reaching_the_split_point_aborts(self):
        # The internal/QSPI boundary is the one value that cannot be read
        # back. If the device does not extend past it, the assumed layout
        # is wrong and the block numbers mean nothing - refuse.
        platform.maybe_mkdir(platform.fpath("/qspi"))
        with open(platform.fpath("/qspi/wallet.json"), "w") as fh:
            fh.write("{}")

        fake = FakeFlash(block_count=platform.QSPI_START_BLOCK)
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        self.assertFalse(self.rebooted)
        # must refuse before touching anything - not a single write,
        # unmount, or delete
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.umounted, [])
        self.assertTrue(platform.file_exists(platform.fpath("/qspi/wallet.json")))

    def test_unusable_block_size_aborts(self):
        platform.maybe_mkdir(platform.fpath("/flash"))
        with open(platform.fpath("/flash/secret.txt"), "w") as fh:
            fh.write("still here")

        fake = FakeFlash(block_size=0)
        self.fake = fake
        pyb.Flash = lambda: fake

        with self.assertRaises(Exception):
            platform.wipe()

        self.assertFalse(self.rebooted)
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.umounted, [])
        self.assertTrue(platform.file_exists(platform.fpath("/flash/secret.txt")))

    def test_matching_geometry_does_not_block_the_wipe(self):
        fake = FakeFlash(block_size=512, block_count=VERIFIED_QSPI_END_BLOCK)
        self.fake = fake
        pyb.Flash = lambda: fake

        platform.wipe()

        self.assertTrue(self.rebooted)

    def test_write_then_sync_then_reboot_ordering(self):
        # Not just "sync was called somewhere" (that's covered above) but
        # that the *last* sync happens strictly after the *last* write and
        # strictly before reboot - the actual ordering the write-behind
        # cache depends on. There are two syncs (internal flash, then
        # QSPI): the first one sits between the two write loops, so only
        # the final sync is required to be the very last thing before
        # reboot.
        fake = FakeFlash()
        self.fake = fake
        pyb.Flash = lambda: fake

        platform.wipe()

        kinds = [event[0] for event in fake.events]
        self.assertEqual(kinds.count("sync"), 2)
        self.assertIn("write", kinds)
        self.assertIn("reboot", kinds)
        last_write_index = max(i for i, k in enumerate(kinds) if k == "write")
        last_sync_index = max(i for i, k in enumerate(kinds) if k == "sync")
        reboot_index = kinds.index("reboot")
        self.assertLess(last_write_index, last_sync_index)
        self.assertLess(last_sync_index, reboot_index)

    def test_internal_flash_synced_before_qspi_overwrite_starts(self):
        # The intermediate sync (added so a power loss during the long
        # QSPI loop doesn't strand the internal-flash overwrite in RAM)
        # must happen strictly between the two write loops, not after
        # QSPI writes have already started.
        fake = FakeFlash()
        self.fake = fake
        pyb.Flash = lambda: fake

        platform.wipe()

        kinds = [event[0] for event in fake.events]
        first_sync_index = kinds.index("sync")
        qspi_write_indices = [
            i for i, e in enumerate(fake.events)
            if e[0] == "write" and e[1] >= platform.QSPI_START_BLOCK
        ]
        self.assertTrue(qspi_write_indices)
        self.assertLess(first_sync_index, min(qspi_write_indices))
