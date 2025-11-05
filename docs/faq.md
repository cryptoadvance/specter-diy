# General Questions

## *What do I need to build Specter-DIY?*

To build Specter yourself you need:

 - STM32F469 discovery board
 - QR Code scanner from Waveshare
 - Power Bank
 - miniUSB cable
 - A few pin connectors 

[Shopping list link](https://github.com/cryptoadvance/specter-diy/blob/master/docs/shopping.md) + [assembly link](https://github.com/cryptoadvance/specter-diy/blob/master/docs/assembly.md)
Waveshare QR scanner is recommended as it has a good quality/price ratio.

## *Is specter-DIY safe to use?*

Yes, kinda. The security level of Specter-DIY is comparable to commercial hardware wallets present on the market. We implemented a secure bootloader that verifies firmware upgrades, so you can be sure that only signed firmware can be uploaded to the device after initial setup.

Note that *initial* firmware installation is *not verified* and the security of this process is limited to the security of your computer. During initial installation make sure you verified PGP signatures and flash the firmware from a secure computer.

## *I'm wondering what if someone takes the device? How does Specter-DIY approach this scenario?*

There are no known attacks that would allow extraction of the keys from the device - our secure bootloader sets a security flag of the microcontroller and the only thing the attacker can do is erase the device completely and install malicious firmware.

To mitigate this attack Specter-DIY has "anti-phishing words" on the PIN screen that are displayed when you start entering the PIN code. These words are unique for every device and will change if the device is erased. So make sure these words remain the same when you are entering the PIN code.

By default the device operates in amnesic mode - it forgets your recovery phrase when you power it off. This means you need to enter your recovery phrase every time when you use the device. Optionally you can save the recovery phrase on the device itself, or on the SD card. In the latter case, the SD card works as a second factor - you can access your keys only if you have both the device and the SD card.

## *Currently there is a `specter_hwi.py` file, which implements the HWIClient for Specter-DIY. Is there any reason you didn't add that directly to HWI?*

We do not plan to add Specter-DIY to HWI - we discourage USB as a communication channel for Specter-DIY. Use QR codes or SD card instead.

## *Do you have a physical security design?*

Physical security of Specter-DIY is limited to the security features available on the microcontroller. It theoretically can be hacked using glitching attacks, but they were not demonstrated on this MCU series.

We also have support for secure smartcards as key storage, but it requires a special adaptor board (Specter Shield). We are planning to add support for off-the-shelf smartcard readers, but no time estimates here.

## *Is there a simulator I can try the Specter-DIY with?*

Yes. Specter-DIY has a [simulator](https://github.com/cryptoadvance/specter-diy/blob/master/docs/simulator.md).

## *How do I load firmware updates to Specter-DIY?*

Initial setup on an empty board happens over miniUSB, but this is the only time you need to connect your device to the computer. After that you need to use SD card for upgrades - insert an SD card with upgrade file to the device and turn it on. Integrity and signatures of the upgrade file are checked by the secure bootloader.

## *Can Specter-DIY register cosigner xpubs like ColdCard? I know you wipe private keys on shutdown, but do you save stuff like that?*

Yes, we keep wallet descriptors and other public info.

## *Once you add the javacard (secure element) you'll save the private keys, too?*

With the secure element you will have three options:

 - agnostic mode, forgets key after shutdown
 - store key on the smartcard but do all crypto on application MCU
 - store key and do crypto on the secure element

At the moment, we have implementation for the first two options. Last seems to be the most secure, but then you need to trust proprietary crypto implementation. The second option saves the private key on the secure element under pin protection, and it can be encrypted, so the secure element never knows the private keys.

## *What happens if I lock my Specter-Javacard by entering the wrong PIN too many times?*

When the Specter-Javacard applet reaches its PIN retry limit the card is permanently locked and the applet becomes unusable. The only recovery is to uninstall the Specter-Javacard applet and then install it again. This reset process cannot be performed directly on the Specter-DIY hardware, but you can complete it with the [SeedSigner smartcard-compatible fork](https://github.com/3rdIteration/seedsigner) or any computer that has a USB smartcard reader.

# Troubleshooting questions

# I can't flash my device via Mini-USB ?

There is a file called `FAIL.txt` saying `The interface firmware FAILED to reset/halt the target MCU`

The Device is probably protected. You can't upgrade via MiniUSB anymore but just via SD-card. Please carefully read the Release-notes.

# I want to do a factory-reset. How can i remove the protection?

https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/remove_protection.md

## *Does anyone have any tips on mounting the power bank and QR code scanner to the STM32 board in a somewhat ergonomic manner?*

Use the smallest powerbank possible. Check out the [gallery](https://github.com/cryptoadvance/specter-diy/blob/master/docs/pictures/gallery/README.md) to see how people do it.




