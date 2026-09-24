# ed25519.py - Optimized version of the reference implementation of Ed25519
#
# Written in 2011? by Daniel J. Bernstein <djb@cr.yp.to>
# 2013 by Donald Stufft <donald@stufft.io>
# 2013 by Alex Gaynor <alex.gaynor@gmail.com>
# 2013 by Greg Price <price@mit.edu>
#
# Source: https://github.com/pyca/ed25519/blob/main/ed25519.py
# Original reference: https://ed25519.cr.yp.to/python/ed25519.py
#
# To the extent possible under law, the author(s) have dedicated all copyright
# and related and neighboring rights to this software to the public domain
# worldwide. This software is distributed without any warranty. See CC0 1.0:
# https://creativecommons.org/publicdomain/zero/1.0/
#
# scalarmult() was rewritten iteratively so it can run on MicroPython, which
# does not have enough stack for the original recursion.

"""
NB: This code is not safe for use with secret keys or secret data.
The only safe use of this code is for verifying signatures on public messages.
"""

import gc
import hashlib

b = 256
q = 2**255 - 19
l = 2**252 + 27742317777372353535851937790883648493


def H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def pow2(x: int, p: int) -> int:
    """== pow(x, 2**p, q)"""
    while p > 0:
        x = x * x % q
        p -= 1
    return x


def inv(z: int) -> int:
    """= z^{-1} mod q, for z != 0"""
    z2 = z * z % q
    z9 = pow2(z2, 2) * z % q
    z11 = z9 * z2 % q
    z2_5_0 = (z11 * z11) % q * z9 % q
    z2_10_0 = pow2(z2_5_0, 5) * z2_5_0 % q
    z2_20_0 = pow2(z2_10_0, 10) * z2_10_0 % q
    z2_40_0 = pow2(z2_20_0, 20) * z2_20_0 % q
    z2_50_0 = pow2(z2_40_0, 10) * z2_10_0 % q
    z2_100_0 = pow2(z2_50_0, 50) * z2_50_0 % q
    z2_200_0 = pow2(z2_100_0, 100) * z2_100_0 % q
    z2_250_0 = pow2(z2_200_0, 50) * z2_50_0 % q
    return pow2(z2_250_0, 5) * z11 % q


d = -121665 * inv(121666) % q
I = pow(2, (q - 1) // 4, q)


def xrecover(y: int) -> int:
    xx = (y * y - 1) * inv(d * y * y + 1)
    x = pow(xx, (q + 3) // 8, q)

    if (x * x - xx) % q != 0:
        x = (x * I) % q

    if x % 2 != 0:
        x = q - x

    return x


By = 4 * inv(5)
Bx = xrecover(By)
B = (Bx % q, By % q, 1, (Bx * By) % q)
ident = (0, 1, 1, 0)

_Bpow = None


def edwards_add(P: tuple, Q: tuple) -> tuple:
    # addition-add-2008-hwcd-3
    # http://www.hyperelliptic.org/EFD/g1p/auto-twisted-extended-1.html
    (x1, y1, z1, t1) = P
    (x2, y2, z2, t2) = Q

    a = (y1 - x1) * (y2 - x2) % q
    b = (y1 + x1) * (y2 + x2) % q
    c = t1 * 2 * d * t2 % q
    dd = z1 * 2 * z2 % q
    e = b - a
    f = dd - c
    g = dd + c
    h = b + a
    x3 = e * f
    y3 = g * h
    t3 = e * h
    z3 = f * g

    return (x3 % q, y3 % q, z3 % q, t3 % q)


def edwards_double(P: tuple) -> tuple:
    # dbl-2008-hwcd
    # http://www.hyperelliptic.org/EFD/g1p/auto-twisted-extended-1.html
    (x1, y1, z1, _) = P

    a = x1 * x1 % q
    b = y1 * y1 % q
    c = 2 * z1 * z1 % q
    e = ((x1 + y1) * (x1 + y1) - a - b) % q
    g = -a + b
    f = g - c
    h = -a - b
    x3 = e * f
    y3 = g * h
    t3 = e * h
    z3 = f * g

    return (x3 % q, y3 % q, z3 % q, t3 % q)


def scalarmult(P: tuple, e: int) -> tuple:
    Q = ident
    while e > 0:
        if e & 1:
            Q = edwards_add(Q, P)
        P = edwards_double(P)
        e = e // 2
    return Q


def _ensure_Bpow():
    global _Bpow
    if _Bpow is not None:
        return
    points = []
    P = B
    for _ in range(253):
        points.append(P)
        P = edwards_double(P)
    _Bpow = points


def scalarmult_B(e: int) -> tuple:
    _ensure_Bpow()
    e = e % l
    P = ident
    for i in range(253):
        if e & 1:
            P = edwards_add(P, _Bpow[i])
        e = e // 2
    if e != 0:
        raise ValueError("scalar reduction failed")
    return P


def encodeint(y: int) -> bytes:
    bits = [(y >> i) & 1 for i in range(b)]
    return bytes(
        [sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(b // 8)]
    )


def encodepoint(P: tuple) -> bytes:
    (x, y, z, _) = P
    zi = inv(z)
    x = (x * zi) % q
    y = (y * zi) % q
    bits = [(y >> i) & 1 for i in range(b - 1)] + [x & 1]
    return bytes(
        [sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(b // 8)]
    )


def bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def Hint(m: bytes) -> int:
    h = H(m)
    return sum(2**i * bit(h, i) for i in range(2 * b))


def isoncurve(P: tuple) -> bool:
    (x, y, z, t) = P
    return (
        z % q != 0
        and x * y % q == z * t % q
        and (y * y - x * x - z * z - d * t * t) % q == 0
    )


def decodeint(s: bytes) -> int:
    return sum(2**i * bit(s, i) for i in range(b))


def decodepoint(s: bytes) -> tuple:
    y = sum(2**i * bit(s, i) for i in range(b - 1))
    x = xrecover(y)
    if x & 1 != bit(s, b - 1):
        x = q - x
    P = (x, y, 1, (x * y) % q)
    if not isoncurve(P):
        raise ValueError("decoding point that is not on curve")
    return P


class SignatureMismatch(Exception):
    pass


def checkvalid(s: bytes, m: bytes, pk: bytes):
    """
    Not safe to use when any argument is secret.

    See module docstring. This function should be used only for
    verifying public signatures of public messages.
    """
    if len(s) != b // 4:
        raise ValueError("signature length is wrong")

    if len(pk) != b // 8:
        raise ValueError("public-key length is wrong")

    R = decodepoint(s[: b // 8])
    A = decodepoint(pk)
    S = decodeint(s[b // 8 : b // 4])
    h = Hint(encodepoint(R) + pk + m)

    (x1, y1, z1, _) = P = scalarmult_B(S)
    (x2, y2, z2, _) = Q = edwards_add(R, scalarmult(A, h))

    if (
        not isoncurve(P)
        or not isoncurve(Q)
        or (x1 * z2 - x2 * z1) % q != 0
        or (y1 * z2 - y2 * z1) % q != 0
    ):
        raise SignatureMismatch("signature does not pass verification")


def verify(key: bytes, payload: bytes, signature: bytes) -> bool:
    """Return True if signature is a valid Ed25519 signature of payload."""
    global _Bpow
    try:
        checkvalid(signature, payload, key)
        return True
    except (SignatureMismatch, ValueError, TypeError):
        return False
    finally:
        # The 253-point table is large; drop it so later steps can allocate.
        _Bpow = None
        gc.collect()
