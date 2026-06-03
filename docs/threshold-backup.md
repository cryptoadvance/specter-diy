# Threshold mnemonic backup (Kurihara n-of-m XOR)

This document describes the `kurihara` module (`src/kurihara.py`): the pure,
GUI-less core of an `n`-of-`m` **threshold backup** for BIP39 mnemonics. It
lets you split a seed into `m` shares such that **any `n`** of them reconstruct
it, while **any `n − 1`** reveal *nothing* about it.

It is a paper-friendly alternative to the existing single-mnemonic backup:

| Scheme | Loss tolerance | Confidentiality | Needs software |
| --- | --- | --- | --- |
| Single copy | none | n/a | no |
| SeedXOR (m-of-m) | none | perfect until last share | no |
| **Kurihara n-of-m (this)** | up to `m − n` | perfect until threshold | no* |
| Shamir / SLIP-39 | up to `m − n` | perfect until threshold | yes (GF arithmetic) |

\* Reconstruction reduces to XORs of hex strings and can be done by hand; this
module simply automates it on the device.

> **Status.** This first contribution ships the **audited arithmetic core and
> unit tests only** — no on-device GUI yet. Wiring it into an app/menu is
> intended as a follow-up PR so the security-critical math can be reviewed in
> isolation first.

## The scheme

The underlying construction is the ideal threshold XOR scheme of Kurihara,
Kiyomoto, Fukushima and Tanaka (ISC 2008). The BIP39-specific adaptation, the
pen-and-paper derivation, the security-property verifications and ready-to-print
templates are detailed in the accompanying whitepaper (see References). Each
share is **exactly the same size as the secret** (the "ideal" property), so when
the secret is BIP39 entropy, every share re-encodes to a valid BIP39 mnemonic of
the same word count — a plausible standalone wallet.

A secret of `L` bits is split into `p − 1` fragments `K_1..K_{p-1}` (with
`K_0 = 0`), where `p` is the smallest prime `≥ m`. Using `(n − 1)·p` uniform
random values `R^(t)_l`, the `q`-th piece of share `i` is

```
W_{i,q} = XOR over t of  R^(t)_{(t·i + q) mod p}   XOR   K_{(q − i) mod p}
```

`p` must be prime so that `i ↦ t·i mod p` is a bijection for every `t ≠ 0`;
otherwise two shares could collide and leak fragments below the threshold.

Reconstruction stacks the pieces of any `n` shares into a linear system over
`GF(2)` and eliminates the random values by XOR (Gaussian elimination). The
module represents each equation's coefficients as a *set* of column indices —
XOR of two rows is the symmetric difference — which keeps the solver free of
big-integer bitmasks and portable to MicroPython.

## Profiles

`L` must split into `p − 1` byte-aligned fragments. The two recommended
profiles:

| Profile | `L` | Words | `p` | Use case |
| --- | --- | --- | --- | --- |
| **2-of-3** | 128 | 12 | 3 | individual / couple, tolerates one loss |
| **3-of-5** | 256 | 24 | 5 | team / family, tolerates two losses |

Wider configurations (4-of-7, 5-of-9) are possible at the cost of a bulkier
reconstruction.

## Security properties

Two information-theoretic guarantees, proven in the Kurihara paper:

- **Perfect confidentiality** — any coalition of `≤ n − 1` shares learns
  nothing: the conditional distribution of the secret stays uniform.
- **Recoverability** — any coalition of `≥ n` shares determines the secret
  uniquely.

The transition is binary: there is no progressive leak as shares accumulate.

What the core does **not** cover (operational concerns, left to the eventual
app / the operator):

- **Randomness quality.** Confidentiality assumes the `R^(t)_l` are uniform and
  independent. On device they come from `rng.get_random_bytes`; the function
  also accepts an injected `randfunc` (used for deterministic test vectors).
- **Transcription integrity.** XOR detects no error. The BIP39 checksum only
  catches errors made *after* reconstruction, not a mis-transcribed share. Per
  line parity / per-page CRC are recommended for paper backups.
- **Active tampering.** A modified share yields a wrong (but checksum-valid)
  seed. Defend with a separately-stored hash (MAC) of the entropy.

## Module API

```python
from kurihara import KuriharaScheme

sch = KuriharaScheme(n=3, m=5, L=256)

# split (random secret, or pass secret=<L/8 bytes>)
secret, shares = sch.generate()

# each share is a valid BIP39 mnemonic of the same word count
import kurihara
words = kurihara.share_to_mnemonic(shares[0])

# reconstruct from any n shares
secret == sch.reconstruct(shares[:3])           # True

# rebuild Share objects from mnemonics alone, then reconstruct
rebuilt = [kurihara.share_from_mnemonic(pid, mnemonic, 3, 5, 256)
           for pid, mnemonic in collected]
sch.reconstruct(rebuilt)

# regenerate a lost share (bit-for-bit identical) from any n others
regenerated = sch.reconstruct_lost(shares[:3], lost_id=5)
```

`KuriharaScheme` raises `ValueError` for invalid parameters, sub-threshold
coalitions, and shares from mismatched instances.

## Tests

`test/tests/test_kurihara.py` runs under the Unix simulator:

```
make test
```

It exercises, for the profiles 2-of-3, 2-of-5, 3-of-5, 4-of-5 and 2-of-2:

- every `n`-coalition reconstructs the secret;
- every `(n − 1)`-coalition is rejected;
- lost-share regeneration is bit-for-bit identical and usable in a new
  coalition;
- each share encodes to a valid mnemonic and the secret round-trips through the
  mnemonics;
- a deterministic known-answer vector guards the construction formula.

## References

- CaverneCrypto, *Bitcoin Mnemonic Backup via Threshold XOR (n-of-m): A
  pen-and-paper adaptation of the Kurihara scheme to BIP39*, 2026 —
  <https://doi.org/10.5281/zenodo.20734041> (the whitepaper this module
  implements; CC BY 4.0)
- J. Kurihara, S. Kiyomoto, K. Fukushima, T. Tanaka, *A New (k, n)-Threshold
  Secret Sharing Scheme and Its Extension*, ISC 2008 —
  <https://eprint.iacr.org/2008/409>
