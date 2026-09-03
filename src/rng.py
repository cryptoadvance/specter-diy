# random number generator
# if os.urandom is available - entropy goes from hardware TRNG
# in simulator just use /dev/urandom
import hashlib
from errors import BaseError

entropy_pool = b"7" * 64

try:
    from os import urandom as get_trng_bytes
except:

    def get_trng_bytes(nbytes):
        with open("/dev/urandom", "rb") as f:
            return f.read(nbytes)


class RNGError(BaseError):
    """Raised when the hardware TRNG output fails a basic sanity check."""

    NAME = "RNG Error"


_FP = 1 << 32


def _expected_distinct(nbytes):
    """Expected number of distinct byte values in nbytes of healthy output.

    256 * (1 - (255/256)**nbytes), floored. Computed in fixed point rather
    than floats so the threshold is identical on every build - MicroPython on
    the F469 is single precision, CPython in the tests is double.
    """
    # (255/256)**nbytes in Q32, by repeated squaring
    r = _FP
    b = (255 * _FP) // 256
    while nbytes:
        if nbytes & 1:
            r = (r * b) // _FP
        b = (b * b) // _FP
        nbytes >>= 1
    return (256 * (_FP - r)) // _FP


def _looks_dead(data):
    """Detect a stalled or failed TRNG.

    rng_get() in the STM32 port returns 0 on timeout (ports/stm32/rng.c) and
    os.urandom() calls it once per byte, so a dead peripheral surfaces as
    all-zero output - or, more generally, as a single repeated byte. A
    peripheral that stalls only intermittently surfaces as mostly-repeated
    output with a few live bytes mixed in, so a plain "all bytes equal" test
    is not enough. Two checks:

    1. No single byte value may cover more than half the buffer. This is what
       catches a partial stall - 25 zeros and 7 live bytes in 32 is obviously
       broken, yet has enough distinct values to pass a counting test.
    2. The number of distinct values must be at least half of what healthy
       output gives (_expected_distinct). Scaling with the expectation matters
       because distinct values saturate at 256: a fixed threshold that is safe
       for 16 bytes accepts a 75%-dead 1000-byte buffer.

    Both are far from the healthy distribution, so a false rejection is below
    2^-24 for the shortest checked buffer and below 2^-40 from 16 bytes up
    (16 bytes is a 12-word seed, 32 a 24-word one).

    This is a liveness check, not a proof of health: no cheap check can
    distinguish a healthy TRNG from a subtly biased one. It only catches the
    failure mode where the peripheral stops responding, which is currently
    silent.

    The check is skipped for very small requests, where a repeated byte can
    occur legitimately and is not evidence of failure.
    """
    n = len(data)
    if n < 4:
        return False
    # iterating bytes yields one int per byte, so counts maps byte value ->
    # occurrences and top is the largest of those counts
    counts = {}
    top = 0
    for byte in data:
        c = counts.get(byte, 0) + 1
        counts[byte] = c
        if c > top:
            top = c
    # below 8 bytes a majority value is plausible in healthy output
    # (b"\x00\x00\x00\x01" is fine), so only the count check applies there
    if n >= 8 and top * 2 > n:
        return True
    return 2 * len(counts) < _expected_distinct(n)


# assuming that entropy_pool has some real entropy
# we can generate bytes using it as well
def get_random_bytes(nbytes):
    global entropy_pool
    d = get_trng_bytes(nbytes)
    if _looks_dead(d):
        raise RNGError("TRNG returned no entropy")
    feed(d)
    # if more than 64 - just do trng
    if nbytes > 64:
        return d
    else:
        h = hashlib.sha512(entropy_pool)
        h.update(d)
        return h.digest()[:nbytes]


# we hash together entropy pool and data we got
def feed(data):
    global entropy_pool
    h = hashlib.sha512(entropy_pool)
    h.update(data)
    entropy_pool = h.digest()
