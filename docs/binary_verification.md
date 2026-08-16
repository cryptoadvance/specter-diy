# Verifying the released binaries

This guide explains how to verify the integrity of Specter firmware binaries on the command line of your OS.

## Release signing keys

Different releases are signed by different keys. Import the key that corresponds to the release you want to verify, then check that the imported key's fingerprint matches the one listed below. The concrete import and fingerprint-check commands for your operating system are in the Linux, macOS, and Windows sections.

### Specter Signer 2026 (releases v1.10.3 and newer)

- Owner: k9ert
- Fingerprint: `9DC3 3CA8 3058 9DE3 B322 5C26 EEF5 756B 2EA4 2349`

### Stepan Snigirev (older releases, such as v1.9.0)

- Fingerprint: `6F16 E354 F833 93D6 E52E C25F 36ED 357A B24B 915F`

### Verify the imported key's fingerprint

A "Good signature" message alone only means the file was signed by *some* key. To be sure it was signed by the intended release key, compare the fingerprint of the imported key with the fingerprint listed above. The sections below show the commands to display the imported key's fingerprint for each operating system.

## Files needed to verify
- `initial_firmware_v<version>.bin` - Binary with secure bootloader. Use for upgrading from versions below 1.4.0 or first-time upload
- `specter_upgrade_v<version>.bin` - For regular upgrades (after you have once done a first-time upload)
- `sha256.signed.txt` - Contains the expected hashes of the binaries, which are signed by the Specter team

> **Note:** Replace `<version>` with your actual firmware version (e.g., 1.9.0)

Download these files for the release you want to use from the Specter DIY repository: https://github.com/cryptoadvance/specter-diy/releases

---

## Linux Verification

### Prerequisites
```bash
# GPG is usually pre-installed. If not:
sudo apt-get install gnupg      # Debian/Ubuntu
sudo dnf install gnupg2         # Fedora
```

### Verification Steps

**1. Import the release signing key:**

For v1.10.3 and newer:
```bash
gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys 9DC33CA830589DE3B3225C26EEF5756B2EA42349
```

For older releases:
```bash
curl -s https://stepansnigirev.com/ss-specter-release.asc | gpg --import
```

**2. Verify the imported fingerprint:**

For v1.10.3 and newer:
```bash
gpg --list-keys --fingerprint 9DC33CA830589DE3B3225C26EEF5756B2EA42349
```

For older releases:
```bash
gpg --list-keys --fingerprint 6F16E354F83393D6E52EC25F36ED357AB24B915F
```

Compare the displayed fingerprint with the one listed in [Release signing keys](#release-signing-keys).

**3. Verify the signature of sha256.signed.txt:**
```bash
gpg --verify sha256.signed.txt
```
✓ Look for "Good signature from" message

**4. Verify the hash of the binary:**
```bash
sha256sum -c sha256.signed.txt --ignore-missing
```
✓ Should show "OK" for the binary file(s)

---

## macOS Verification

### Prerequisites
```bash
# Install GPG via Homebrew
brew install gnupg
```

### Verification Steps

**1. Import the release signing key:**

For v1.10.3 and newer:
```bash
gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys 9DC33CA830589DE3B3225C26EEF5756B2EA42349
```

For older releases:
```bash
curl -s https://stepansnigirev.com/ss-specter-release.asc | gpg --import
```

**2. Verify the imported fingerprint:**

For v1.10.3 and newer:
```bash
gpg --list-keys --fingerprint 9DC33CA830589DE3B3225C26EEF5756B2EA42349
```

For older releases:
```bash
gpg --list-keys --fingerprint 6F16E354F83393D6E52EC25F36ED357AB24B915F
```

Compare the displayed fingerprint with the one listed in [Release signing keys](#release-signing-keys).

**3. Verify the signature of sha256.signed.txt:**
```bash
gpg --verify sha256.signed.txt
```
✓ Look for "Good signature from" message

**4. Verify the hash of the binary:**

The version of `shasum` shipped with macOS does not support the `--ignore-missing` flag, so the following two approaches are recommended.

#### Option A: Manual comparison (works on every Mac)
```bash
shasum -a 256 initial_firmware_v<version>.bin
shasum -a 256 specter_upgrade_v<version>.bin
```
Then manually compare the outputs with the hashes listed in `sha256.signed.txt`. They must be identical.

#### Option B: Use GNU Coreutils
Install GNU Coreutils via Homebrew:
```bash
brew install coreutils
```
Then run:
```bash
gsha256sum -c sha256.signed.txt --ignore-missing
```
✓ Should show "OK" for the binary file(s)

> Homebrew installs GNU tools with a `g` prefix by default. If you have added `$(brew --prefix coreutils)/libexec/gnubin` to your `PATH`, the command is `sha256sum` instead of `gsha256sum`.

---

## Windows Verification

### Prerequisites
1. Download and install [Gpg4win](https://gpg4win.org/download.html)
2. After installation, open PowerShell or Command Prompt

### Verification Steps

**1. Import the release signing key:**

For v1.10.3 and newer:
```powershell
gpg --keyserver hkps://keyserver.ubuntu.com --recv-keys 9DC33CA830589DE3B3225C26EEF5756B2EA42349
```

For older releases:
```powershell
curl.exe -s https://stepansnigirev.com/ss-specter-release.asc -o stepan-key.asc
gpg --import stepan-key.asc
```

**2. Verify the imported fingerprint:**

For v1.10.3 and newer:
```powershell
gpg --list-keys --fingerprint 9DC33CA830589DE3B3225C26EEF5756B2EA42349
```

For older releases:
```powershell
gpg --list-keys --fingerprint 6F16E354F83393D6E52EC25F36ED357AB24B915F
```

Compare the displayed fingerprint with the one listed in [Release signing keys](#release-signing-keys).

**3. Verify the signature of sha256.signed.txt:**
```powershell
gpg --verify sha256.signed.txt
```
✓ Look for "Good signature from" message

**4. Verify the hash of the binary:**
```cmd
certutil -hashfile initial_firmware_v<version>.bin SHA256
certutil -hashfile specter_upgrade_v<version>.bin SHA256
```
Then manually compare the outputs with the hashes in `sha256.signed.txt`. They need to be the same.

