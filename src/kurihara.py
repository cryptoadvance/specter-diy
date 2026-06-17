"""
Kurihara ideal (k, n)-threshold XOR secret sharing.

Underlying scheme: J. Kurihara, S. Kiyomoto, K. Fukushima, T. Tanaka,
"A New (k, n)-Threshold Secret Sharing Scheme and Its Extension",
ISC 2008, https://eprint.iacr.org/2008/409

BIP39 adaptation, pen-and-paper derivation, security-property verification and
ready-to-print templates: CaverneCrypto, "Bitcoin Mnemonic Backup via Threshold
XOR (n-of-m): A pen-and-paper adaptation of the Kurihara scheme to BIP39", 2026,
https://doi.org/10.5281/zenodo.20734041 (CC BY 4.0).

This is the pure, GUI-less core of the threshold-backup feature: it splits a
secret into ``m`` shares such that any ``n`` of them reconstruct it while any
``n - 1`` reveal nothing (perfect, information-theoretic confidentiality).
Every share is exactly the same size as the secret (the "ideal" property), so
when the secret is BIP39 entropy each share re-encodes to a valid BIP39
mnemonic of the same word count.

Only XOR is used; there is no finite-field arithmetic beyond GF(2). The module
depends only on ``rng`` for randomness (injectable for tests) and, optionally,
on ``embit.bip39`` for the mnemonic <-> entropy glue. The arithmetic core has
no external dependency and is therefore trivial to audit and to unit-test off
device.

Construction formula (with K_0 = 0 by convention):

    W_{i,q} = XOR over t of  R^(t)_{(t*i + q) mod p}   XOR   K_{(q - i) mod p}

where p is the smallest prime >= m, the K_q are the p-1 fragments of the
secret, and the R^(t)_l are (n-1)*p uniform random values.
"""

import rng
from binascii import hexlify


def xor_bytes(*chunks):
    """Bit-wise XOR of several equal-length byte sequences."""
    out = bytearray(len(chunks[0]))
    for chunk in chunks:
        for i in range(len(chunk)):
            out[i] ^= chunk[i]
    return bytes(out)


def is_prime(k):
    if k < 2:
        return False
    if k < 4:
        return True
    if k % 2 == 0:
        return False
    i = 3
    while i * i <= k:
        if k % i == 0:
            return False
        i += 2
    return True


def smallest_prime_gte(n):
    """Smallest prime greater than or equal to n."""
    candidate = n if n > 2 else 2
    while not is_prime(candidate):
        candidate += 1
    return candidate


class Share:
    """One share of the split.

    part_id : 1-based share number (S_1, S_2, ...).
    pieces  : list of p-1 byte chunks of d bytes each (W_{i,0}..W_{i,p-2}).
    meta    : dict of instance parameters, shared across sibling shares.
    """

    def __init__(self, part_id, pieces, meta):
        self.part_id = part_id
        self.pieces = pieces
        self.meta = meta

    def to_bytes(self):
        """Concatenated pieces: exactly L bits, a valid BIP39 entropy."""
        return b"".join(self.pieces)

    def __repr__(self):
        return "Share(S_%d, instance=%s)" % (
            self.part_id, self.meta.get("instance", "?")
        )


class KuriharaScheme:
    """Kurihara n-of-m ideal threshold XOR secret-sharing scheme."""

    # BIP39 entropy sizes, in bits
    VALID_L = (128, 160, 192, 224, 256)

    def __init__(self, n, m, L):
        if not (2 <= n <= m):
            raise ValueError("need 2 <= n <= m")
        if L not in self.VALID_L:
            raise ValueError("L=%d is not a standard BIP39 entropy size" % L)
        self.n = n
        self.m = m
        self.L = L
        self.p = smallest_prime_gte(m)
        if (L % (self.p - 1)) != 0 or ((L // (self.p - 1)) % 8) != 0:
            raise ValueError(
                "L=%d is not divisible into p-1=%d byte-aligned fragments; "
                "use a matching profile (e.g. 2-of-3/L=128, 3-of-5/L=256)"
                % (L, self.p - 1)
            )
        self.num_fragments = self.p - 1
        self.d_bytes = L // self.num_fragments // 8

    # ---- generation ----------------------------------------------------

    def _split_secret(self, secret):
        """Split the secret into p-1 fragments; K_0 = 0 by convention."""
        zero = bytes(self.d_bytes)
        fragments = [zero]
        for j in range(self.num_fragments):
            fragments.append(secret[j * self.d_bytes:(j + 1) * self.d_bytes])
        return fragments

    def _gen_random(self, randfunc):
        """Draw (n-1) sets of p random values (the R^(t)_l)."""
        return [
            [randfunc(self.d_bytes) for _ in range(self.p)]
            for _ in range(self.n - 1)
        ]

    def _piece(self, i, q, K, R):
        """Compute the piece W_{i,q} from the Kurihara formula."""
        terms = []
        for t in range(self.n - 1):
            terms.append(R[t][(t * i + q) % self.p])
        terms.append(K[(q - i) % self.p])
        return xor_bytes(*terms)

    def generate(self, secret=None, randfunc=None):
        """Build m shares with threshold n.

        secret   : L/8 bytes; if None a fresh random secret is drawn.
        randfunc : callable(nbytes) -> bytes for the random values and the
                   secret. Defaults to rng.get_random_bytes. Injectable so
                   tests can produce deterministic vectors.

        Returns (secret, [Share, ...]).
        """
        if randfunc is None:
            randfunc = rng.get_random_bytes
        if secret is None:
            secret = randfunc(self.L // 8)
        if len(secret) != self.L // 8:
            raise ValueError("secret must be %d bytes" % (self.L // 8))

        K = self._split_secret(secret)
        R = self._gen_random(randfunc)
        instance = hexlify(randfunc(4)).decode()
        meta = {
            "instance": instance,
            "n": self.n, "m": self.m, "L": self.L, "p": self.p,
        }

        shares = []
        for i in range(self.m):
            pieces = [self._piece(i, q, K, R)
                      for q in range(self.num_fragments)]
            shares.append(Share(i + 1, pieces, dict(meta)))
        return secret, shares

    # ---- reconstruction (Gaussian elimination over GF(2)) --------------

    def reconstruct(self, shares):
        """Reconstruct the secret from at least n shares."""
        self._check_coalition(shares)
        K, _ = self._solve([(s.part_id - 1, s.pieces) for s in shares])
        out = []
        for j in range(1, self.p):
            out.append(K[j])
        return b"".join(out)

    def reconstruct_lost(self, shares, lost_id):
        """Regenerate the lost share S_{lost_id} (1-based) from n others.

        The result is bit-for-bit identical to the original share thanks to
        the shift symmetry of the random values: any choice for the residual
        free variables yields the same recomputed pieces.
        """
        self._check_coalition(shares)
        if not (1 <= lost_id <= self.m):
            raise ValueError("share id out of range: %d" % lost_id)
        i_lost = lost_id - 1
        for s in shares:
            if s.part_id - 1 == i_lost:
                raise ValueError("S_%d is already in the coalition" % lost_id)

        K, R = self._solve([(s.part_id - 1, s.pieces) for s in shares])
        pieces = [self._piece(i_lost, q, K, R)
                  for q in range(self.num_fragments)]
        return Share(lost_id, pieces, dict(shares[0].meta))

    def _check_coalition(self, shares):
        """Ensure enough shares, all from the same instance."""
        if len(shares) < self.n:
            raise ValueError(
                "need %d shares, got %d" % (self.n, len(shares))
            )
        ref = shares[0].meta.get("instance")
        for s in shares[1:]:
            if s.meta.get("instance") != ref:
                raise ValueError("shares come from different instances")

    def _solve(self, observed):
        """Solve the Kurihara linear system for the observed pieces.

        Each piece W_{i,q} is one linear equation over GF(2^d). The GF(2)
        coefficient row is represented as a *set* of active column indices
        (XOR of two rows = symmetric difference of their column sets), which
        keeps the elimination free of big-integer bitmasks and portable to
        MicroPython.

        Column layout:
            R^(t)_l  ->  t*p + l            (t = 0..n-2, l = 0..p-1)
            K_j      ->  num_r + (j-1)      (j = 1..p-1, K_0 absorbed)

        Returns (K, R). Structurally free variables are left at zero; this
        affects neither the K_q nor any regenerated share piece.
        """
        num_r = (self.n - 1) * self.p
        num_k = self.num_fragments
        num_vars = num_r + num_k

        # Build one equation [cols:set, val:bytes] per observed piece.
        equations = []
        for i, pieces in observed:
            for q in range(self.num_fragments):
                cols = set()
                for t in range(self.n - 1):
                    cols.add(t * self.p + (t * i + q) % self.p)
                k_idx = (q - i) % self.p
                if k_idx != 0:
                    cols.add(num_r + (k_idx - 1))
                equations.append([cols, pieces[q]])

        # Gaussian elimination, one pivot per column.
        pivot_of = {}
        used = set()
        for col in range(num_vars):
            pivot = None
            for r in range(len(equations)):
                if r not in used and (col in equations[r][0]):
                    pivot = r
                    break
            if pivot is None:
                continue
            pivot_of[col] = pivot
            used.add(pivot)
            p_cols, p_val = equations[pivot]
            for r in range(len(equations)):
                if r != pivot and (col in equations[r][0]):
                    equations[r][0] = equations[r][0] ^ p_cols
                    equations[r][1] = xor_bytes(equations[r][1], p_val)

        # Extract the fragments K_1..K_{p-1} (free residuals stay zero).
        zero = bytes(self.d_bytes)
        K = [zero] * self.p
        for j in range(1, self.p):
            col = num_r + (j - 1)
            if col not in pivot_of:
                raise ValueError("K_%d undetermined: not enough shares?" % j)
            K[j] = equations[pivot_of[col]][1]

        # Extract the random values R^(t)_l (free residuals stay zero).
        R = [[zero] * self.p for _ in range(self.n - 1)]
        for t in range(self.n - 1):
            for l in range(self.p):
                col = t * self.p + l
                if col in pivot_of:
                    R[t][l] = equations[pivot_of[col]][1]

        return K, R


# ---- BIP39 glue --------------------------------------------------------
#
# A share's concatenated pieces are exactly L bits, i.e. a standard BIP39
# entropy, so each share re-encodes to a valid mnemonic of the same word
# count (a plausible decoy). embit is imported lazily so the arithmetic core
# above carries no external dependency.


def _bip39():
    from embit import bip39
    return bip39


def entropy_to_mnemonic(entropy):
    return _bip39().mnemonic_from_bytes(entropy)


def mnemonic_to_entropy(mnemonic):
    return _bip39().mnemonic_to_bytes(mnemonic.strip())


def share_to_mnemonic(share):
    """Encode a share as a BIP39 mnemonic (its pieces, concatenated)."""
    return entropy_to_mnemonic(share.to_bytes())


def share_from_mnemonic(part_id, mnemonic, n, m, L, instance="input"):
    """Decode a BIP39 mnemonic into a Share.

    BIP39 decoding drops the checksum bits; the L entropy bits are split into
    p-1 pieces of d bytes.
    """
    entropy = mnemonic_to_entropy(mnemonic)
    if len(entropy) * 8 != L:
        raise ValueError(
            "mnemonic carries %d bits of entropy, expected %d"
            % (len(entropy) * 8, L)
        )
    p = smallest_prime_gte(m)
    d_bytes = L // (p - 1) // 8
    pieces = [entropy[q * d_bytes:(q + 1) * d_bytes] for q in range(p - 1)]
    meta = {"instance": instance, "n": n, "m": m, "L": L, "p": p}
    return Share(part_id, pieces, meta)
