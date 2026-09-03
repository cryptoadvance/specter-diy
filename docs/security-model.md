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
  itself. Note: in the current implementation the attempt counter is
  decremented and persisted *before* the PIN is checked, so the 10th
  attempt already triggers the wipe without verifying the PIN first —
  effectively 9 verification attempts instead of the intended 10 (fail-safe
  direction; a correct PIN entered on the 10th attempt still wipes).
- The PIN check is an HMAC keyed with the internal secret, so the PIN
  cannot be brute-forced offline from flash contents alone.
- The PIN state file is authenticated; tampering with it triggers a wipe
  as well.
- The wipe erases the internal flash of the MCU — it does **not** erase
  the smartcard. The card relies on its own attempt counter and bricks
  itself when exhausted. Note that if the card holds the secret in
  encrypted form, wiping the device makes the card's data permanently
  inaccessible anyway, because the card-encryption key is derived from
  the device secret that was just destroyed.

Two more properties of the PIN check are worth knowing:

- **There is no key stretching.** Deriving keys from the PIN costs a
  single SHA-256. On the device this is fine — the attempt limit stops
  online guessing. But if an attacker reads out the internal flash (the
  exact thing readout protection is meant to prevent), the attempt limit
  no longer applies and PINs can be tried offline at full hardware speed:
  a 4-digit PIN falls in milliseconds, a 6-digit PIN in seconds.
- **There is no time-based delay** between attempts. The persistent,
  fail-closed attempt counter is the only rate limit — it cannot be reset
  by power-cycling the device.

**Choose a long PIN.** Because offline brute-force is the realistic worst
case (flash readout without RDP), do not rely on the 10-attempt limit
alone: use 8 or more digits. "1234"-style PINs are unacceptable, and even
6 digits offer little resistance against an offline attack.

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
  funds.** The mnemonic is stored encrypted and authenticated in the
  flash of the main MCU (AES-CBC + HMAC-SHA256, encrypt-then-MAC — the
  same construction as for wallet files), with a key derived from your
  PIN and the internal device secret, and it is protected by the PIN
  attempt limit described above.
  But this is fundamentally a software-only barrier: the main MCU is not
  a secure element, and a sufficiently equipped attacker with physical
  access should be considered able to extract the flash contents (see
  "Threat model" and "Known limitations") — at that point the security
  of your funds reduces to the entropy of your PIN. Use this mode only
  for testing or small amounts.

Whatever mode you use: your recovery phrase backup is the ultimate
fallback. The device can always be wiped, lost or destroyed — make sure
your mnemonic is backed up safely and independently of the device.

## BIP-39 passphrases

Specter-DIY supports an optional BIP-39 passphrase (sometimes called the
"25th word") that is combined with your recovery phrase to derive the
wallet keys. Properties worth understanding before you use one:

- The passphrase is **never stored** on the device or the smartcard —
  only the mnemonic is saved. You enter the passphrase whenever the key
  is loaded.
- A passphrase-protected wallet is a completely different wallet: a
  different fingerprint, different xpubs, different addresses. There is
  no way to prove that a passphrase wallet does or does not exist, which
  gives you plausible deniability and protects you if someone finds your
  mnemonic backup.
- The flip side: if you forget the passphrase, the funds are
  irrecoverable — your mnemonic backup alone is not enough. And because
  you type it on the touchscreen, it can be observed (shoulder-surfing,
  smudges), so treat it like a password.

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

- Before signing, the device lists every input together with the name of
  the wallet it belongs to and its amount, so you can see exactly which
  of your wallets is spending. Inputs that belong to a wallet the device
  does **not** know are shown as "Unknown wallet" and trigger an explicit
  warning, because the device cannot verify change for them. If a
  transaction spends inputs from more than one wallet group, the device
  shows an explicit mixed-inputs warning at the top of the transaction
  confirmation, so it is visible without scrolling.
  This also applies when known-wallet and unknown-wallet inputs are mixed:
  the unknown-wallet warning is shown and the mixed-inputs warning is
  included in the transaction confirmation. The warning is particularly
  intended to mitigate the class of multisig/mixed-input change-address
  [attack](https://blog.trezor.io/details-of-the-multisig-change-address-issue-and-its-mitigation-6370ad73ed2a).
- Change outputs show the name of the wallet they are sent to.
- To use a multisig or miniscript wallet you first need to import the
  wallet by adding the wallet descriptor (over QR, USB or SD card). The
  device only signs for wallets it knows.

Change is verified for you automatically only when there is one unambiguous
spending wallet, its descriptor has exactly two branches, the output
derivation resolves to branch-list position 1, and the device re-derives the
exact output script from that branch and index. Every other output remains
visible, including receive-branch self-payments and outputs from unusual
descriptors. The branch position is not the raw child-number value in the
descriptor.

The Bitcoin transaction does not contain an `is_change` flag. A PSBT may carry
host-supplied BIP32 or Taproot derivation metadata, but that metadata is
untrusted and is checked against the locally stored descriptor and the actual
output script. If a branch-1 wallet claim does not match, the output remains
visible and the device displays: `Invalid change metadata! Host claimed this
output as wallet change, but it does not match your wallet. Verify the
destination.` This reports inconsistent host metadata; it does not claim that
Bitcoin marked the output as change.

What the device cannot check is the *recipient* of an unverified output — so
always verify the receive address and the transaction details (amounts, fees)
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
  `.txt` files, BIP-85-derived keys, xpub files — is written
  **unencrypted** (and only when you choose that export).

Regardless of the channel, the host software (Specter Desktop, Bitcoin
Core, etc.) is considered untrusted: it can withhold transactions or show
you wrong information on its own screen, but it cannot make the device
sign something you didn't confirm on the device screen.

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
- Transaction warnings are currently implemented in several different
  places rather than in one central pipeline: the device warns about
  unknown wallets in the inputs, about mixed-wallet inputs, about sighash
  flags other than SIGHASH_ALL (offering to sign SIGHASH_ALL inputs only),
  about transactions that were already signed, and about address indexes
  beyond the wallet's gap limit. Brainstorming / open work: consolidate
  these checks into a single warning pipeline and maintain a complete list
  of everything the device verifies before signing.

## Reporting vulnerabilities

Please see [`SECURITY.md`](../SECURITY.md) in the repository root for
how to report a vulnerability (contact e-mail, GPG keys for encrypted
reports, scope and disclosure process).
