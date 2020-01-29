# Security of Specter-DIY

## Hardware

Display is contolled by application MCU. 

Secure element integration is not there yet - at the moment secrets are also stored on the main MCU.

Device uses external flash to store some files (QSPI), but all user files are signed by the wallet and checked when loaded. Secret files are never stored on external flash (will never be...).

QR scanning functionality is moved to a separate microcontroller to remove image processing functionality from security-critical MCU. But at the moment USB and SD card are still handled by the main MCU, so don't use SD card and USB if you want to reduce attack surface further.

## PIN protection (user authentication)

During the first boot a unique secret is generated on the main MCU. This secret allows you to verify that the device was not replaced by a malicious one - when you enter the PIN code you see a list of words that will remain the same while the secret is there.

Your PIN code together with this unique secret are used to generate a decryption key for your entropy. So if the attacker would be able to bypass PIN screen, decryption will still fail.

## Transactions verification

The following rules apply to transactions that wallet will sign:

- mixed inputs from different wallets are not allowed
- change outputs to addresses not belonging to the wallet are NOT change
- legacy transactions are not supported
- to use a multisig setup you first need to import the wallet
