# Security of Specter-DIY

## Hardware

Display is contolled by application MCU. 

Secure element integration is not there yet - at the moment secrets are also stored on the main MCU. But you can use the wallet without storing the secret - you need to enter your recovery phrase every time. Why to remember long passphrase if you can remember the mnemonic?

Device uses external flash to store some files (QSPI), but all user files are signed by the wallet and checked when loaded. Secret files are never stored on external flash (will never be...).

QR scanning functionality is on a separate microcontroller so all image processing happens outside of security-critical MCU. At the moment USB and SD card are still managed by the main MCU, so don't use SD card and USB if you want to reduce attack surface.

## PIN protection (user authentication)

During the first boot a unique secret is generated on the main MCU. This secret allows you to verify that the device was not replaced by a malicious one - when you enter the PIN code you see a list of words that will remain the same while the secret is there.

Your PIN code together with this unique secret are used to generate a decryption key for your entropy. So if the attacker would be able to bypass PIN screen, decryption will still fail.

## Generation of the recovery phrase

This is one of the most important parts of the wallet - to generate the key securely. To do this well we use multiple sources of entropy:

- TRNG of the microcontroller. Proprietary, certified and probably good but we don't trust it
- Touchscreen. Every time you touch the screen we measure the position and the moment when this touch happened (in microcontroller ticks at 180MHz).
- Built-in microphones - not yet. The board has two microphones, so hardware wallet can listen to you and mix in this data to the entropy pool.

All this entropy is hashed together and converted to your recovery phrase. The resulting entropy is always better than any of the individual sources.

## Transactions verification

The following rules apply to transactions that wallet will sign:

- mixed inputs from different wallets are not allowed
- change outputs to addresses not belonging to the wallet are NOT change
- legacy transactions are not supported
- to use a multisig setup you first need to import the wallet by scanning it's descriptor

