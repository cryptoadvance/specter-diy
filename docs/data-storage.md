# Data Storage on Specter-DIY

This document lists all data persisted by Specter-DIY, where it is stored,
and how it is protected. It reflects the current implementation in `src/`
(keystore, hosts, apps) — if you find a mismatch, please report it (see
[`SECURITY.md`](../SECURITY.md)).

## Storage Areas

The device uses three persistent storage areas, plus one volatile one:

- **Internal Flash** (`/flash`) — keystore secrets, PIN state, saved
  mnemonics, network selection
- **QSPI Flash** (`/qspi`) — wallet data, host settings, global settings
- **SD Card** (`/sd`) — optional mnemonic backups, exported files
- **SDRAM ramdisk** (`/sdram`, volatile) — temporary storage for untrusted
  host data (e.g. PSBTs being processed); gone at power-off, never
  persisted

## The Device Secret

On first boot the device generates a single 32-byte random secret stored
unencrypted at `/flash/keystore/secret`. Its confidentiality relies
entirely on the MCU's readout protection (see
[security-model.md](./security-model.md)). It is the root of all derived
keys:

| Derived key | Derivation | Purpose |
|-------------|------------|---------|
| Anti-phishing key | `tagged_hash("auth", secret)` | Generates the words shown during PIN entry |
| Settings key | `tagged_hash("settings key", secret)` | Encrypts global and host settings |
| User key | `tagged_hash("userkey", secret)` | Encrypts Liquid asset labels; basis of the device UID |
| UID | `hexlify(tagged_hash("uid", userkey)[:4]).decode()` | 4-byte device identifier, hex-encoded as **8 characters** |

With the smartcard keystore, the user key is instead derived as
`tagged_hash("userkey", secret + card_pubkey)` — i.e. it is unique per
device *and* card, and so is the UID.

The anti-phishing words are generated per entered PIN digit using
HMAC-SHA256 of the derived key and the BIP-39 wordlist. They are **not**
stored — computed fresh each time you type your PIN.

## Internal Flash (`/flash`)

| Data | Path | Format | Protection |
|------|------|--------|------------|
| Device secret | `/flash/keystore/secret` | 32 raw bytes | None (relies on MCU readout protection) |
| PIN state | `/flash/keystore/pin` | JSON: `{"pin": hex, "pin_attempts_max": N, "pin_attempts_left": N}` | AEAD with device secret |
| Encryption secret | `/flash/keystore/enc_secret` | 32 random bytes | AEAD with PIN-derived key |
| Saved mnemonics ("reckless" mode) | `/flash/keystore/reckless.<name>` | Mnemonic string | AEAD with encryption secret |
| Network selection | `/flash/network` | Plain text, e.g. `main`, `test`, `liquidv1` | None |

The PIN itself is stored as an HMAC-SHA256 keyed with
`tagged_hash("pin", secret)` — without the device secret it cannot be
brute-forced offline. The encryption secret (`enc_secret`) is a random key
used to encrypt saved mnemonics and SD-card key backups; it is itself
encrypted with `pin_secret = tagged_hash("pin", secret + pin)`, derived
from both the device secret and your PIN — so changing your PIN only
requires re-encrypting this one key.

### Saving, replacing and deleting a saved mnemonic

Saving a mnemonic writes the encrypted file and synchronizes it. When an
existing file is replaced, the user must confirm the replacement; Specter
then performs a best-effort logical overwrite and removes the old file before
writing the new encrypted file with strict synchronization. Deleting a
mnemonic uses the same best-effort logical overwrite-before-remove operation.

This is not forensic erasure. The firmware checks every write and every error
reported by the runtime, but the current MicroPython VFS/block-device layer
may not propagate every physical I/O failure. Wear-levelling may also retain
historical physical copies. A successful operation therefore means that the
logical overwrite path completed as far as the runtime could verify it; only
physical destruction provides a forensic guarantee.

These operations are deliberately **not power-loss transactional**. A power
interruption during save, replacement or deletion may cause loss of the
locally stored mnemonic. There is no `.old` / `.tmp` recovery protocol and
no guarantee that a valid local copy remains. Users must maintain an
independent recovery backup of their recovery phrase.

## QSPI Flash (`/qspi`)

### Wallet Data

Each wallet lives in `/qspi/wallets/<fingerprint_hex>/<network>/<n>/` with
two files:

| File | Content | Protection |
|------|---------|------------|
| `descriptor` | Full descriptor string, e.g. `wpkh([fp/path]xpub/{0,1}/*)` | AEAD with idkey (`m/0x1D'` from seed) |
| `meta` | JSON: `{"gaps": [20, ...], "name": "My Wallet", "unused_recv": 0}` | AEAD with idkey |

The xpub is embedded inside the descriptor string. `gaps` tracks the
maximum derived address index per branch (receive/change) plus the gap
limit of 20; `unused_recv` tracks the next unused receive address.

Wallet names are stored in the `meta` file. When importing a wallet via
descriptor, if the input contains `&`, everything before the last `&` is
parsed as the name (e.g. `"My Wallet&wpkh(...)"`).

### Liquid Asset Labels (`/qspi/wallets/uid<8_hex>/assets_<network>`)

User-defined labels for Liquid assets: JSON mapping asset hex IDs to label
strings. Encrypted with the user key.

### Host Settings (`/qspi/hosts/<ClassName>.settings`)

| Host | Stored fields |
|------|---------------|
| `USBHost.settings` | `{"enabled": true/false}` (default: disabled) |
| `QRHost.settings` | `{"enabled", "aim", "light", "sound", "raw_fix_applied"}` |
| `SDHost.settings` | `{"enabled": true/false}` |

All encrypted with the settings key. The marker file
`/qspi/hosts/.qr_factory_reset_done` tracks whether the QR scanner's
initial factory reset was performed.

### Global Settings (`/qspi/global/global.settings`)

JSON: `{"experimental": {"taproot": true/false}}`. Encrypted with the
settings key.

## SD Card (Optional)

| File | Content | Protection |
|------|---------|------------|
| `specterdiy<hex_id>.<name>` | Mnemonic backup | AEAD with encryption secret |
| `<first_word>.txt` | Plaintext mnemonic export | None |
| `bip85-*.txt` | BIP-85 derived mnemonics / keys | None |
| xpub / descriptor exports | Various formats (`.txt` / `.json`) | None |

The SD card mnemonic backups use a device-specific prefix
(`specterdiy<hex_id>`, derived from the device secret via
`tagged_hash("sdid", secret)`) and are encrypted with the encryption
secret — so only this device can recognize and decrypt them. Everything
else on the card is only written when you explicitly choose an export, and
is unencrypted.

## Smartcard (Optional)

With the smartcard keystore, the card stores a small TLV blob containing
the **seed entropy** (the raw bytes of your mnemonic). Two variants:

- **Encrypted (device-bound)**: AEAD with key
  `tagged_hash("scenc", device_secret)`; a fingerprint
  `tagged_hash("scid", device_secret)[:4]` lets the device detect data
  written by a different device. If the device is wiped, the card's data
  becomes permanently inaccessible.
- **Plaintext (portable)**: same container format but with a publicly
  known constant key, so the card works on any Specter-DIY after PIN
  entry.

Access to the card requires the card PIN; the attempt limit is enforced
by the card itself and bricks the card when exhausted. The seed never
touches the MCU's internal flash in this mode.

## What Is NOT Persisted

- **Entropy pool**: lives in RAM only, fed from the hardware TRNG and
  touchscreen input
- **XPubs**: derived on-demand from the mnemonic; only descriptor strings
  containing them are stored
- **Anti-phishing words**: computed on-the-fly from the device secret and
  the PIN digits entered so far
- **Mnemonic in temporary seed mode**: if you never save your key, it
  lives only in RAM and is gone at power-off
- **BIP-39 passphrase**: never stored anywhere; entered whenever the key
  is loaded
- **Untrusted host data** (PSBTs, descriptors being processed): only in
  the volatile SDRAM ramdisk

## Encryption Details

There is no AES-GCM in the firmware. All persistent "AEAD" blobs use
Specter-DIY's own `aead_encrypt` / `aead_decrypt` helper construction
(`src/helpers.py`):

- **Encryption**: AES-CBC with a random 16-byte IV and `0x80`-padding
- **Authentication**: HMAC-SHA256 over `associated_data || iv ||
  ciphertext`, appended to the blob (encrypt-then-MAC); verified before
  decryption
- **Subkeys**: separate AES and HMAC keys are derived from the
  caller-provided key via `tagged_hash("aes", key)` and
  `tagged_hash("hmac", key)` (BIP-340-style tagged hashes)

The idkey used for wallet data is the private key at derivation path
`m/0x1D'` from your seed — so wallet data is tied to your specific
mnemonic: it stays unreadable without the seed, and tampering is detected
when the files are loaded.
