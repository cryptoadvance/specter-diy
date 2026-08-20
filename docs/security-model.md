# Security of Specter-DIY

This document explains the security model of Specter-DIY: what the device
protects against, what it explicitly does NOT protect against, and which
mechanisms implement these guarantees.

## Threat model

Specter-DIY is designed to protect your keys against:

- **A compromised host computer.** The host only ever sees public data
  (xpubs, descriptors, unsigned PSBTs) and signatures. Private keys never
  leave the device. All critical information (receive addresses, amounts,
  change outputs) is shown on the device screen for user verification.
- **A thief with the locked device.** Stored secrets are encrypted with a
  key derived from your PIN and a unique internal device secret. The PIN
  is rate-limited (see below), so brute-forcing it on the device is
  impractical.
- **A device swap / evil maid after setup.** The anti-phishing words shown
  during PIN entry change if the internal secret is gone — i.e. if the
  device was replaced or its firmware was reflashed without the locked
  bootloader.
- **Malicious firmware upgrades.** After the initial installation the
  secure bootloader only accepts firmware signed by the release keys (or
  your own keys if you use a self-signed bootloader).

Explicitly **out of scope**:

- **Physical attacks with lab equipment** (chip decapsulation, power/EM
  side-channel analysis, glitching) against the main MCU. Without the
  smartcard, secrets live in the application MCU. If this threat matters
  to you, use the smartcard storage mode or don't store the key on the
  device at all (temporary seed mode).
- **Compromised hardware before first use** (supply chain). Buy components
  from reputable sources and inspect the device. The anti-phishing words
  only protect you *after* you have set up the device.
- **The QR scanner's own firmware.** The scanner module only forwards
  decoded data to the main MCU, which treats it as untrusted input, but a
  malicious scanner could feed you crafted QR codes. Physical inspection
  and buying from reputable sources apply here as well.

## Hardware

Display is controlled by the application MCU.

The device uses external flash (QSPI) to store wallet files (descriptors,
wallet metadata, settings). These files are encrypted and authenticated
(AES-CBC + HMAC-SHA256, encrypt-then-MAC) with a key derived from your
seed at `m/0x1D'` — so a flash dump alone reveals neither your xpubs nor
your wallet structure, and tampering with the files is detected when they
are loaded.

QR scanning functionality runs on a separate scanner module, so all image
processing happens outside of the security-critical MCU. USB and SD card
are managed by the main MCU — avoid them if you want to reduce the attack
surface (USB is off by default, see "Communication channels" below).

For a complete list of what data the device persists, where it is stored
and how it is protected, see [`data-storage.md`](./data-storage.md).

## Firmware verification

Specter-DIY uses a dedicated secure bootloader — the
[specter-bootloader](https://github.com/cryptoadvance/specter-bootloader)
project, included in this repo as the `bootloader/` submodule and
specified in
[`doc/bootloader-spec.md`](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/bootloader-spec.md).
After the initial installation, the device only accepts signed firmware:

- Upgrades arrive on an SD card as a single `specter_upgrade*.bin` file.
  The bootloader verifies ECDSA signatures (secp256k1, SHA-256,
  Bitcoin-message-style over a bech32-encoded payload hash) **after**
  copying the payload to internal flash — data is read back from flash,
  not from the removable SD card.
- **Multisignature with configurable thresholds** is supported. There is
  a key hierarchy: *vendor keys* can sign the bootloader and the main
  firmware, *maintainer keys* can sign the main firmware only. Keys are
  added and compromised keys are revoked by releasing a new bootloader.
- **Downgrades are prohibited** — a version check record stores the
  latest version ever programmed to the device, for both the bootloader
  and the main firmware.
- The bootloader itself consists of a tiny **non-upgradable start-up
  code** plus **two redundant bootloader copies**; on every boot the
  start-up code integrity-checks both copies and runs the newest intact
  one. On every normal boot the main firmware's integrity record is
  verified as well.

The **initial** installation is the trust-critical step, because the
bootloader is not installed at the factory — you flash it yourself:

1. Verify the PGP signature of `sha256.signed.txt`. Since v1.10.3 the
   hash file is signed with the **"Specter Signer 2026"** key,
   controlled by k9ert
   (fingerprint `9DC3 3CA8 3058 9DE3 B322 5C26 EEF5 756B 2EA4 2349`,
   available from the
   [Ubuntu keyserver](http://keyserver.ubuntu.com/pks/lookup?op=get&search=0x9dc33ca830589de3b3225c26eef5756b2ea42349)).
   Older releases were signed with [Stepan's release
   key](https://stepansnigirev.com/ss-specter-release.asc).
2. Verify the hash of `initial_firmware_<version>.bin` against the signed
   hash file.
3. Flash from a computer you trust.

Note that v1.10.3 is also a real-world example of the key rotation
described above: it ships a bootloader with a new vendor key set, and
devices on v1.9.0 or earlier must install it before they can accept any
later upgrades.

See [`quickstart.md`](./quickstart.md) for the full procedure. The
firmware is [reproducible](./reproducible-build.md), so you can verify
that release binaries match the published source code. And if you don't
want to trust the release keys at all, you can build the bootloader with
**your own public keys** and sign upgrades yourself — the signing message
is a standard Bitcoin signed message, so most hardware wallets can do it
([`doc/selfsigned.md`](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/selfsigned.md)).

### Readout and write protection

The bootloader can be built with flash protection enabled
(`READ_PROTECTION=1 WRITE_PROTECTION=1`, see the bootloader
[README](https://github.com/cryptoadvance/specter-bootloader#readme)):

- **RDP Level 1** blocks external readout of the internal flash. An
  attacker can still erase the chip via JTAG/SWD — but that also erases
  the internal secret, so the manipulation is visible to you: the
  anti-phishing words shown at PIN entry will be different.
- **RDP Level 2** disables JTAG/SWD completely and is **irreversible** —
  the board can never be debugged or unbricked via SWD again. It is
  therefore blocked by default and requires a manual source code change
  to enable. Think twice.
- **Write protection** protects the flash sectors of the start-up code,
  the bootloader and the main firmware against modification.

Removing the protection afterwards (see
[`doc/remove_protection.md`](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/remove_protection.md))
always wipes the entire flash, including the internal secret.

## PIN protection (user authentication)

During the first boot a unique secret is generated on the main MCU. This
secret is stored unencrypted in the internal flash
(`/flash/keystore/secret`) — its confidentiality relies entirely on the
MCU's readout protection (see "Readout and write protection"). It allows
you to verify that the device was not replaced by a malicious one — when
you enter the PIN code you see a list of words that remains the same
while the secret is there.

Your PIN together with this unique secret is used to generate the
decryption key for your Bitcoin keys (if you store them). So even if an
attacker bypasses the PIN screen, decryption still fails.

The unencrypted secret is, however, the weak point to be aware of: if an
attacker manages to read the internal flash — which is exactly what the
readout protection is designed to prevent — they obtain the device
secret together with the PIN file. That enables two follow-up attacks:
brute-forcing your PIN **offline** at full speed (the 10-attempt limit
no longer applies), and **cloning the anti-phishing words** onto a
malicious device so it *looks* like your device. With RDP enabled this
scenario is blocked: the attacker can only erase the chip, which
destroys the secret and is visible to you. This is why we recommend
enabling readout protection (see "Readout and write protection").

Brute-force protection is enforced on the device:

- At most **10 PIN attempts** are allowed; afterwards the device wipes
  itself.
- The PIN check is an HMAC keyed with the internal secret, so the PIN
  cannot be brute-forced offline from flash contents alone.
- The PIN state file is authenticated; tampering with it triggers a wipe
  as well.

Choose a PIN that is not trivially guessable — 10 attempts are few, but
"1234"-style PINs are still a bad idea.

## Secret storage modes

Specter-DIY supports three storage modes:

- **Temporary seed mode** — **recommended.** The device stores no
  private keys: your recovery phrase lives only in RAM and is gone at
  power-off, so there is no secret to extract from a stolen device.
  Note that non-secret data still persists: the device secret, PIN
  state, settings, and any wallet descriptors you imported — and those
  descriptors contain your xpubs. Wallet data is encrypted with a key
  derived from your seed (at `m/0x1D'`), so it stays unreadable until
  you re-enter the phrase, but its presence on the flash is visible.
- **Smartcard** (requires a Specter Shield / Shield-Lite with smartcard
  slot and a JavaCard) — **recommended.** The secret is stored on a
  PIN-protected smartcard and only moved to the MCU's RAM when unlocked.
  The seed never touches the MCU's internal flash, so even a complete
  readout of the MCU reveals nothing about your key; and the card, as a
  dedicated secure element, is built to resist exactly the physical
  attacks that are out of scope for the main MCU. Communication between
  the MCU and the card runs over an encrypted secure channel, the card
  itself enforces the PIN attempt limit in hardware and bricks when it
  is exhausted, and the anti-phishing words are derived from both the
  internal device secret and the card's public key — so you detect if
  either the device or the card was swapped. You can store the secret
  on the card either encrypted (bound to this device) or as plaintext
  (portable to any Specter-DIY after PIN entry).
- **Internal flash ("reckless" mode)** — **not recommended for real
  funds.** The mnemonic is stored AEAD-encrypted in the flash of the
  main MCU, with a key derived from your PIN and the internal device
  secret, and it is protected by the PIN attempt limit described above.
  But this is fundamentally a software-only barrier: the main MCU is not
  a secure element, and a sufficiently equipped attacker with physical
  access should be considered able to extract the flash contents (see
  "Threat model" and "Known limitations") — at that point the security
  of your funds reduces to the entropy of your PIN. Use this mode only
  for testing or small amounts.

Whatever mode you use: your recovery phrase backup is the ultimate
fallback. The device can always be wiped, lost or destroyed — make sure
your mnemonic is backed up safely and independently of the device.

## Generation of the recovery phrase

This is one of the most important parts of the wallet — generating the key
securely. We use multiple sources of entropy:

- **TRNG of the microcontroller.** Proprietary, certified and probably
  good, but we don't trust it alone.
- **Touchscreen.** Every touch contributes the position and the moment of
  the touch (in microcontroller ticks at 180 MHz).

All entropy is hashed together (SHA-512 based entropy pool) and converted
to your recovery phrase. The resulting entropy is always at least as good
as the best individual source. Note: the two microphones on the board are
currently NOT used as an entropy source.

## High level logic - wallets

Specter operates as a key storage. It holds HD private keys that can be
involved in wallets. Wallets are defined by their
[descriptors](./descriptors.md). We support miniscript as well.

Every wallet belongs to a particular network. A wallet imported on
`testnet` is not available on `mainnet` or `regtest` — you need to switch
to that network and import the wallet separately. Supported networks are
Mainnet, Testnet, Regtest and Signet. Liquid support exists in the
codebase but is not actively maintained.

## Transaction verification

The following rules apply to transactions that the wallet will sign:

- If mixed inputs from different wallets are found, the user is warned
  ([attack](https://blog.trezor.io/details-of-the-multisig-change-address-issue-and-its-mitigation-6370ad73ed2a)).
- Change outputs show the name of the wallet they are sent to.
- To use a multisig or miniscript wallet you first need to import the
  wallet by adding the wallet descriptor (over QR, USB or SD card). The
  device only signs for wallets it knows.

Change is verified for you automatically: the device identifies change
outputs against the imported wallet descriptor and labels them with the
wallet name. What the device cannot check is the *recipient* — so always
verify the receive address and the transaction details (amounts, fees)
on the device screen. The screen is the trusted output channel, the host
computer is not.

## Communication channels

- **QR codes** are the default and recommended channel: airgapped,
  unidirectional per frame and limited in capacity, so you stay in control
  of the data flow.
- **USB** is **off by default**. It can be enabled in the device settings
  and provides the host protocol described in
  [`communication.md`](./communication.md). Enable it only when you need
  it.
- **SD card** is used for firmware upgrades and optionally for PSBTs,
  descriptors and key backups. Treat every file on it as untrusted input
  — and the card itself as sensitive: mnemonic backups written by the
  device (`specterdiy<hex-id>.<name>`) are encrypted and only readable by
  this device, but anything you explicitly export — plain mnemonic
  `.txt` files, BitBox02-format backups, BIP-85-derived keys, xpub files —
  is written **unencrypted** (and only when you choose that export).

Regardless of the channel, the host software (Specter Desktop, Bitcoin
Core, etc.) is considered untrusted: it can withhold transactions or show
you wrong information on its own screen, but it cannot make the device
sign something you didn't confirm on the device screen.

## Importing a native BitBox02 microSD backup

Specter can import a wallet directly from an original BitBox02 microSD backup
(`Key management` -> `Import recovery phrase` -> `BitBox microSD backup`).
The parser lives in [`src/bitbox_backup.py`](../src/bitbox_backup.py) (format
decoding/validation, no hardware or GUI dependencies) and
[`src/bitbox_sd.py`](../src/bitbox_sd.py) (read-only SD card discovery); the
menu flow is `Specter.import_bitbox_backup()` in
[`src/specter.py`](../src/specter.py).

**The backup is not encrypted.** BitBox02's native microSD backup format
(`messages/backup.proto` in
[bitbox02-firmware](https://github.com/BitBoxSwiss/bitbox02-firmware),
Apache-2.0) has a single defined mode, `PLAINTEXT`, and stores the wallet's
raw BIP-39 entropy in the clear inside a small protobuf message. **Anyone
with physical access to the SD card can read the wallet's recovery phrase
directly off it**, without a PIN, password or any device. This is a property
of the BitBox02 backup format itself, not a Specter limitation - Specter's
job here is only to import what's already unencrypted on the card, and it
shows an explicit "not encrypted" warning before doing so.

A few things that are *not* required or used during import, since they
don't apply to this format:

- **The BitBox device password is never asked for and never needed.** It
  protects the BitBox02's own internal flash storage, not the microSD
  backup - the backup file itself has no such protection.
- **A BIP-39 passphrase is never read from the backup.** A BitBox microSD
  backup contains only the BIP-39 entropy; the format has no field for a
  passphrase. Specter does not ask for one during the import either - after
  the recovery phrase has been imported you can apply a BIP-39 passphrase
  through Specter's normal existing passphrase workflow, exactly as after
  any other recovery phrase import. Note that a BIP-39 passphrase is a
  value you choose yourself and is entirely unrelated to the BitBox device
  password.
- The 32-byte value in the file called `checksum` is a SHA-256 corruption
  check, **not an authentication tag**. It proves the file wasn't damaged in
  storage/transit, but it does nothing to stop someone who can write their
  own bytes to the card from producing a "valid" (self-consistent) forged
  backup. It is not presented as, and must not be understood as, proof that
  the backup came from a genuine BitBox02.

**What the import checks**, in order, before anything is ever loaded:

1. Every file is opened read-only and capped at 1024 bytes (BitBox02's own
   `SD_MAX_FILE_SIZE`) before parsing.
2. The protobuf is decoded by a small, special-purpose parser restricted to
   exactly the five messages in `backup.proto` - not a general protobuf
   library. It rejects (rather than guesses at) truncated or overlong
   varints, non-canonical varint encodings, length prefixes that would run
   past the buffer, protobuf "groups" (wire types 3/4), unknown/duplicate
   backup-version selectors, and duplicate occurrences of any known
   singular field. This is stricter than plain proto3 "last field wins"
   semantics, deliberately, since a genuine BitBox02 backup never needs to
   duplicate a field.
3. The stored checksum is recomputed (little-endian `u32` fields, the
   64-byte zero-padded name, the 32-byte seed field, the 20-byte zero-padded
   generator string, and the historical `length` field, which is `0` on
   current backups but is still read and used verbatim for older ones) and
   compared against the value in the file. A mismatch is rejected outright.
4. Only 16/24/32-byte entropy (12/18/24-word mnemonics) is accepted; the
   32-byte `seed` field's unused tail must be all-zero padding.
5. The backup id (the 64-character hex directory name) is independently
   recomputed as `HMAC-SHA256("backup", entropy zero-padded to 32 bytes)`
   and compared against the directory the files were loaded from.
6. A BitBox02 backup has three (normally identical) copies. Specter reads
   all three read-only, validates each independently, and:
   - uses the result if one or more copies are individually valid, but only
     after confirming that *all* individually-valid copies agree with each
     other byte-for-byte - conflicting valid copies abort the import with an
     explicit error instead of silently picking one (this is stricter than
     bitbox02-firmware's own loader, which returns the first valid copy it
     finds without cross-checking the others);
   - otherwise, if all three files are the same length, attempts a
     bitwise-majority reconstruction (`(a&b)|(a&c)|(b&c)` per byte) and
     re-runs the *entire* validation pipeline above (checksum and backup id
     included) against the reconstructed data before it is ever used. A
     majority-recovered import shows an explicit warning asking the user to
     verify the recovery phrase carefully.
   - if none of that succeeds, the import is rejected.
7. Only after all of the above passes does Specter show the backup's
   metadata (name, creation time in UTC, word count, generator/firmware
   string, the full backup id wrapped onto two lines - so it can be
   compared character-for-character against what the BitBox App or a real
   BitBox02 shows - and whether majority recovery was used) and the
   recovered recovery phrase, using the existing recovery-phrase
   confirmation screen. Nothing is loaded into the keystore until the user
   explicitly confirms the phrase.

**Where the BitBox-specific code ends.** Step 7 is the boundary. Once a
valid mnemonic has been recovered, the import hands it to
`Specter.confirm_and_set_mnemonic()` - literally the same method the
QR/SD/USB host import uses - and does nothing else afterwards. From that
point on nothing in Specter knows, or needs to know, that the phrase came
from a BitBox backup.

Specter's other recovery-phrase sources deliberately assemble the steps
before that point differently, and are not expected to share code with it:
manual entry and key generation confirm the words inside the entry screen
itself and therefore call `Specter.set_mnemonic()` directly, while loading
an already stored key (internal flash, SD card or smartcard) needs neither a
confirmation nor a new save and so applies `keystore.set_mnemonic()` from
within the keystore. What *is* guaranteed - and covered by
`ImportSourceEquivalenceTest` in `test/tests_native/test_bitbox_backup_flow.py`
- is that all of these end in the same place: the same mnemonic with an
empty password reaching the keystore, exactly one app re-initialisation, no
automatic passphrase, no automatic persistence, and the main menu as the
destination.

**What the import never does:**

- It never writes, renames, or deletes anything on the SD card - every file
  is opened read-only.
- It never auto-saves the imported key. Exactly like every other recovery
  phrase import in Specter, `set_mnemonic()` only loads the key into RAM;
  whether to work amnesically, store the key encrypted, export it in
  plaintext, or add a passphrase remains the user's explicit choice
  afterwards, through the existing Specter menus.
- It never adds BitBox-specific screens or prompts after the phrase has been
  confirmed - in particular it does not ask about a BIP-39 passphrase, a PIN,
  or a storage medium.
- On any cancellation or error at any step, the previously loaded key (if
  any) is left completely untouched, and no file on the card is modified.

**Known limits:**

- Directory names are matched as exactly 64 lowercase hex characters; an
  uppercase or mixed-case directory (which genuine BitBox02 firmware never
  produces - it always writes lowercase hex) is ignored rather than
  case-folded, to avoid any ambiguity on the case-insensitive FAT
  filesystem used on the card.
- **Zeroization is partial by design, and worth stating precisely.** The
  buffers the import code *owns* are explicitly overwritten as soon as they
  are no longer needed: the three raw file images (right after parsing,
  before any user-facing screen), the intermediate 32-byte padded seed
  field, the extracted entropy of every rejected or redundant copy, and
  finally the imported entropy itself once the mnemonic has been derived
  (including on every abort and exception path). `ParsedBackup` keeps
  exactly one entropy buffer rather than re-slicing it on each access,
  precisely so that a single `zeroize()` reaches all of it.

  What this does **not** cover, and cannot in pure Python: the final
  mnemonic is a `str` and immutable, so it cannot be wiped - the same is
  already true of every other recovery-phrase path in Specter. Likewise,
  intermediate `bytes` slices produced while decoding the protobuf, and the
  one immutable copy that must be handed to `embit.bip39` (see below), stay
  in the heap until garbage collected. In short: the number of live secret
  copies is deliberately minimised and the owned ones are wiped, but no
  guarantee of full memory erasure is offered or implied.

  One sharp edge worth recording, since it is easy to reintroduce: embit's
  `bip39.mnemonic_from_bytes()` performs `entropy += checksum` internally,
  which for a `bytearray` argument **mutates the caller's buffer in place**
  (16 bytes in, 48 bytes out). The import therefore hands embit an
  immutable `bytes` copy on purpose; removing that conversion as a
  "needless copy" would silently corrupt the entropy buffer and defeat its
  zeroization.

- The SD card is mounted only for the two short, purely read-only
  operations that need it (listing the backup directories, and reading the
  three files of the chosen backup) and is unmounted again before any
  confirmation screen is shown. The card is never left mounted while
  waiting on the user, so removing it mid-dialog cannot affect the import.
- Inserting any SD card increases the main MCU's attack surface, exactly as
  already noted above under "Hardware" - this applies to a BitBox backup
  card exactly as it does to any other SD card content Specter reads.

## Exporting a recovery phrase to the SD card

When you ask Specter to save the loaded recovery phrase to the SD card
(`Show recovery phrase` -> `Save to SD card`, or `Flash & SD card storage`
-> `Save key` -> `SD card`), it offers a choice of formats and tells you
plainly what each one means before anything is written:

- **Plain text (Specter format)** writes the phrase as a plaintext
  `<name>.specter.txt` file. **Anyone holding the card gets full access to
  the funds** - the confirmation dialog says exactly that and tells you to
  treat the card like a handwritten paper backup and never plug it into an
  untrusted computer.
- **Bitbox format** writes a native BitBox02 microSD backup: three
  redundant copies under `bitbox02/<backup id>/`, the same layout a real
  BitBox02 produces, so the card can in principle be restored by a real
  BitBox02 as well (untested on real hardware). The same "not encrypted"
  warning applies - the BitBox microSD format stores the entropy in the
  clear, as described in the import section above. Two deliberate
  differences from real-device output: Specter-DIY has no real-time clock,
  so it writes `timestamp = 0` ("unknown (no clock)" on import) rather
  than fabricating a date, and names the files `0.bin`, `1.bin`, `2.bin`
  instead of timestamped names (the firmware loader ignores file names -
  only the exactly-three-files rule matters). Because the backup id
  depends only on the seed, each recovery phrase has exactly one backup
  directory; the writer refuses to write into a directory that already
  contains files rather than merging into it, since a directory with
  other than exactly three files is rejected by both implementations.
  The written copies are verified immediately by reading them back
  through the same parser the import uses.
- **Encrypted (this device only)** is available when the active keystore
  is `Flash & SD card storage` (SDKeyStore): the phrase is written with
  the same AEAD scheme and device-bound secret as internal-flash storage
  (`specterdiy<hex-id>.<name>`), readable only by this exact device. The
  warning spells out the residual risk: more convenient than plaintext,
  but still a software-only barrier - not comparable to a PIN-protected
  smartcard. With a smartcard keystore active the option is shown but
  disabled, since there is no device-bound secret to encrypt with.

User-chosen backup names are validated before they become file names
(path separators, FAT-invalid and control characters are rejected), and
overwriting an existing file always requires an explicit confirmation.

## Erasing data from the SD card

`Device settings` -> `SD card` shows how many Specter-related items the
card holds (device-encrypted key files, plaintext phrase exports, BitBox
backup directories) and offers **Delete data**, which can erase a single
item or format the whole card:

- **Deleting one item** overwrites the file contents with fresh random
  data several times, syncing after each pass, before unlinking - the
  same overwrite-then-unlink principle BitBox02's own firmware uses when
  it replaces a backup (theirs overwrites once with a fixed byte), except
  with multiple random passes. A plain delete only removes the directory
  entry and leaves the old bytes recoverable until the space is reused.
- **Format entire SD card** overwrites *every block* on the card with
  random data before creating a fresh FAT filesystem - the same approach
  `platform.wipe()` uses for the internal flash - and requires two
  confirmations, since it destroys everything on the card, not just
  Specter's files.

One honest limit, stated in the format confirmation as well: SD cards do
their own wear leveling, so a logically overwritten block may still exist
physically in controller-managed space the host can never reach.
MicroPython's SD driver exposes no hardware erase command (CMD38) that
could close that gap. The random-overwrite passes and the full-card wipe
are the strongest erase Specter-DIY can perform in software and are a
large improvement over plain deletion - but against a well-equipped
forensic attacker, physical destruction is the only certain way to
sanitize any SD card.

## Known limitations and open work

- The firmware has **not undergone an external security audit**. It is
  written in MicroPython to stay auditable, and community review is
  welcome.
- Secure poweroff that actively erases secrets from RAM is on the
  [roadmap](./roadmap.md) — currently RAM is not explicitly scrubbed on
  shutdown.
- Fuzzing and extended testing of parsers (PSBT, descriptors, QR data) is
  ongoing work, see the [roadmap](./roadmap.md).
- Without the smartcard, a sufficiently equipped attacker with prolonged
  physical access to the device should be considered able to extract
  secrets from the main MCU (see "Threat model").

## Reporting vulnerabilities

Please see [`SECURITY.md`](../SECURITY.md) in the repository root for
how to report a vulnerability (contact e-mail, GPG keys for encrypted
reports, scope and disclosure process).
