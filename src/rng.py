# random number generator
# if os.urandom is available - entropy goes from hardware TRNG
# in simulator just use /dev/urandom
import hashlib

entropy_pool = b"7" * 64

try:
    from os import urandom as get_trng_bytes
except:
    def get_trng_bytes(nbytes):
        with open("/dev/urandom", "rb") as f:
            return f.read(nbytes)


class RNGError(Exception):
    """Raised when the hardware TRNG output fails a basic sanity check."""


def _looks_dead(data):
    """Detect a stalled or failed TRNG.

    rng_get() in the STM32 port returns 0 on timeout (ports/stm32/rng.c),
    so a dead peripheral surfaces as all-zero output - or, more generally,
    as a single repeated byte. This is not a proof of health: no cheap
    check can distinguish a healthy TRNG from a subtly biased one. It only
    catches the specific failure mode where the peripheral stops
    responding, which is currently silent.

    The check is skipped for very small requests, where a repeated byte can
    occur legitimately and is not evidence of failure.
    """
    if len(data) < 4:
        return False
    return len(set(data)) <= 1


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
