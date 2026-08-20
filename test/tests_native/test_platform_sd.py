"""
Tests for platform.SDCard.erase_and_format() using a fake block device.

The critical property under test: the chunked overwrite loop must keep
yielding to the asyncio event loop between chunks *even when a progress
callback is provided* - a callback that never awaits anything itself
(e.g. one that only redraws a progress bar) would otherwise run
synchronously and starve the GUI's update loop for the entire format,
freezing the screen on device.
"""
import sys

if sys.implementation.name != "micropython":
    from native_support import setup_native_stubs

    setup_native_stubs()

import asyncio
import os
from unittest import TestCase

import platform

# CPython's asyncio has no sleep_ms (MicroPython does); the platform
# module under test uses it. Provide the usual shim if missing.
if not hasattr(asyncio, "sleep_ms"):
    async def _sleep_ms(ms):
        await asyncio.sleep(ms / 1000.0)
    asyncio.sleep_ms = _sleep_ms

# os.VfsFat only exists in MicroPython; stub mkfs for the native run.
if not hasattr(os, "VfsFat"):
    class _VfsFat:
        @staticmethod
        def mkfs(bdev):
            pass
    os.VfsFat = _VfsFat


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeBlockDevice:
    """Just enough of the MicroPython block-device protocol for
    erase_and_format(): ioctl(4)=block count, ioctl(5)=block size,
    writeblocks(), power()."""

    def __init__(self, block_count, block_size=512):
        self.block_count = block_count
        self.block_size = block_size
        self.writes = []  # (start_block, num_bytes) per call
        self.power_states = []

    def present(self):
        return True

    def ioctl(self, op, arg):
        if op == 4:
            return self.block_count
        if op == 5:
            return self.block_size
        raise OSError("unsupported ioctl")

    def writeblocks(self, start, data):
        self.writes.append((start, len(data)))

    def power(self, state):
        self.power_states.append(state)


class EraseAndFormatTest(TestCase):
    def test_overwrites_every_block_and_reformats(self):
        # 4100 blocks * 512 bytes: with 1 MB chunking (2048 blocks per
        # chunk) this takes 3 write calls, so per-chunk behaviour shows up.
        dev = _FakeBlockDevice(block_count=4100, block_size=512)
        sd = platform.SDCard(sd=dev)
        progress = []

        async def main():
            async def cb(fraction):
                progress.append(fraction)
            await sd.erase_and_format(progress_cb=cb)

        _run(main())

        # every block exactly once, in order, no gaps and no overruns
        self.assertEqual(
            dev.writes,
            [(0, 2048 * 512), (2048, 2048 * 512), (4096, 4 * 512)],
        )
        # one progress callback per chunk, ending at 100%
        self.assertEqual(len(progress), 3)
        self.assertEqual(progress[-1], 1.0)
        # device powered for the operation and powered off afterwards
        self.assertEqual(dev.power_states, [True, False])

    def test_event_loop_keeps_running_with_progress_callback(self):
        dev = _FakeBlockDevice(block_count=4100, block_size=512)
        sd = platform.SDCard(sd=dev)
        ticks = []
        progress = []

        async def ticker():
            # counts event-loop iterations that run while the format is
            # in progress - zero means the format starved the loop
            try:
                while True:
                    ticks.append(1)
                    await asyncio.sleep_ms(0)
            except asyncio.CancelledError:
                pass

        async def main():
            task = asyncio.ensure_future(ticker())

            async def cb(fraction):
                # deliberately never awaits - like a bare screen redraw
                progress.append(fraction)

            await sd.erase_and_format(progress_cb=cb)
            task.cancel()
            await task

        _run(main())

        self.assertEqual(len(progress), 3)
        # the unrelated task ran at least once per written chunk, i.e. the
        # loop was not blocked for the whole operation
        self.assertGreaterEqual(len(ticks), len(progress))

    def test_event_loop_keeps_running_without_progress_callback(self):
        dev = _FakeBlockDevice(block_count=4100, block_size=512)
        sd = platform.SDCard(sd=dev)
        ticks = []

        async def ticker():
            try:
                while True:
                    ticks.append(1)
                    await asyncio.sleep_ms(0)
            except asyncio.CancelledError:
                pass

        async def main():
            task = asyncio.ensure_future(ticker())
            await sd.erase_and_format()
            task.cancel()
            await task

        _run(main())
        self.assertGreaterEqual(len(ticks), 3)

    def test_powered_off_even_on_write_error(self):
        class FailingDevice(_FakeBlockDevice):
            def writeblocks(self, start, data):
                raise OSError("card removed")

        dev = FailingDevice(block_count=4100, block_size=512)
        sd = platform.SDCard(sd=dev)

        async def main():
            # writeblocks failure is re-raised as RuntimeError with a
            # clearer message, but the original OSError is chained via
            # `from e` so __cause__ still points at it.
            with self.assertRaises(RuntimeError) as ctx:
                await sd.erase_and_format()
            self.assertIsInstance(ctx.exception.__cause__, OSError)

        _run(main())
        self.assertEqual(dev.power_states, [True, False])

    def test_invalid_geometry_rejected_before_any_write(self):
        """A block device reporting a zero/None block size or count must
        be rejected with a clear RuntimeError before the overwrite loop
        starts, rather than crashing with a ZeroDivisionError deep inside
        the chunk-size calculation or silently doing nothing."""
        class _BadGeometryDevice(_FakeBlockDevice):
            def __init__(self, block_count, block_size):
                self.block_count = block_count
                self.block_size = block_size
                self.writes = []
                self.power_states = []

        for bad_size, bad_count in [(0, 4100), (512, 0), (None, 4100), (512, None)]:
            dev = _BadGeometryDevice(block_count=bad_count, block_size=bad_size)
            sd = platform.SDCard(sd=dev)

            async def main():
                with self.assertRaises(RuntimeError) as ctx:
                    await sd.erase_and_format()
                self.assertIn("invalid geometry", str(ctx.exception))

            _run(main())
            # must not have attempted a single write
            self.assertEqual(dev.writes, [])
