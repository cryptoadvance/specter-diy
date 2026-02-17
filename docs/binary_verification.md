# Verifying the released binaries

This guide explains how to verify the integrity of Specter firmware binaries on the command line of your OS.

## Files needed to verify
- `initial_firmware_v<version>.bin` - Binary with secure bootloader. Use for upgrading from versions below 1.4.0 or first-time upload
- `specter_upgrade_v<version>.bin` - For regular upgrades (after you have once done a first-time upload)
- `sha256.signed.txt` - Contains the expected hashes of the binaries, which are signed by the specter team

> **Note:** Replace `<version>` with your actual firmware version (e.g., 1.9.0)

Download these files for the release you want to use from the Specter DIY repository: https://github.com/cryptoadvance/specter-diy/releases 

## Linux Verification

### Prerequisites
```bash
# GPG is usually pre-installed. If not:
sudo apt-get install gnupg      # Debian/Ubuntu
sudo dnf install gnupg2         # Fedora
```

### Verification Steps

**1. Import Stepan's PGP key:**
```bash
curl -s https://stepansnigirev.com/ss-specter-release.asc | gpg --import
```

**2. Verify the signature of sha256.signed.txt:**
```bash
gpg --verify sha256.signed.txt
```
✓ Look for "Good signature from" message

**3. Verify the hash of the binary:**
```bash
sha256sum -c sha256.signed.txt --ignore-missing
```
✓ Should show "OK" for the binary file(s)

## macOS Verification

### Prerequisites
```bash
# Install GPG via Homebrew
brew install gnupg
```

### Verification Steps

**1. Import Stepan's PGP key:**
```bash
curl -s https://stepansnigirev.com/ss-specter-release.asc | gpg --import
```

**2. Verify the signature of sha256.signed.txt:**
```bash
gpg --verify sha256.signed.txt
```
✓ Look for "Good signature from" message

**3. Verify the hash of the binary:**
```bash
shasum -a 256 -c sha256.signed.txt --ignore-missing
```
✓ Should show "OK" for the binary file(s)

---

## Windows Verification

### Prerequisites
1. Download and install [Gpg4win](https://gpg4win.org/download.html)
2. After installation, open PowerShell or Command Prompt

### Verification Steps

**1. Import Stepan's PGP key:**
```powershell
curl.exe -s https://stepansnigirev.com/ss-specter-release.asc -o stepan-key.asc
gpg --import stepan-key.asc
```

**2. Verify the signature of sha256.signed.txt:**
```powershell
gpg --verify sha256.signed.txt
```
✓ Look for "Good signature from" message

**3. Verify the hash of the binary:**

**Option A - Using CertUtil:**
```cmd
certutil -hashfile initial_firmware_v<version>.bin SHA256
```
Then manually compare the output with the hash in sha256.signed.txt. They need to be the same.

**Option B - Using PowerShell:**
```powershell
(Get-FileHash initial_firmware_v<version>.bin -Algorithm SHA256).Hash.ToLower()
```
Then manually compare the output with the hash in sha256.signed.txt. They need to be the same.
