# Security of Specter-DIY

## Hardware

Display is contolled by application MCU. 

Secure element integration is not there yet - at the moment secrets are also stored on the main MCU. But you can use the wallet without storing the secret - you need to enter your recovery phrase every time. Why to remember long passphrase if you can remember the whole mnemonic?

Device uses external flash to store some files (QSPI), but all user files are signed by the wallet and checked when loaded.

QR scanning functionality is on a separate microcontroller so all image processing happens outside of security-critical MCU. At the moment USB and SD card are still managed by the main MCU, so don't use SD card and USB if you want to reduce attack surface.

## PIN protection (user authentication)

During the first boot a unique secret is generated on the main MCU. This secret allows you to verify that the device was not replaced by a malicious one - when you enter the PIN code you see a list of words that will remain the same while the secret is there.

Your PIN code together with this unique secret are used to generate a decryption key for your Bitcoin keys (if you store them). So if the attacker would be able to bypass PIN screen, decryption will still fail.

If you have locked the firmware (TODO: add instructions link here) it will effectively lock the secret as well, so if the attacker flashes different firmware to the board the secret gets erased and you will be able to recognize it when you start entering PIN code - words sequence will be different.

## Generation of the recovery phrase

This is one of the most important parts of the wallet - to generate the key securely. To do this well we use multiple sources of entropy:

- TRNG of the microcontroller. Proprietary, certified and probably good but we don't trust it
- Touchscreen. Every time you touch the screen we measure the position and the moment when this touch happened (in microcontroller ticks at 180MHz).
- Built-in microphones - not yet. The board has two microphones, so hardware wallet can listen to you and mix in this data to the entropy pool.

All this entropy is hashed together and converted to your recovery phrase. The resulting entropy is always better than any of the individual sources.

## High level logic - wallets

Specter operates as a key storage. It holds HD private keys that can be involved in wallets. Wallets are defined by their [descriptors](./descriptors.md). We support miniscript as well.

Every wallet belongs to a particular network. This means that if you imported a wallet on `testnet` it will not be available on `mainnet` or `regtest` - you need to switch to this network and import the wallet separately.

## Transactions verification

The following rules apply to transactions that wallet will sign:

- if mixed inputs from different wallets are found the user is warned ([attack](https://blog.trezor.io/details-of-the-multisig-change-address-issue-and-its-mitigation-6370ad73ed2a))
- change outputs show the name of the wallet they are sent to
- to use a multisig or miniscript you first need to import the wallet by adding wallet descriptor (over QR, USB or SD card)

