# General Questions

## *What does the Specter-DIY consist of?*

It consists of:

 - STM32F469 discovery board
 - QR Code scanner from Waveshare
 - Power Bank (small)
 - miniUSB and microUSB cable
 - Prototype Shield
 - A few pin connectors 

[Shopping list link](https://github.com/cryptoadvance/specter-diy/blob/master/docs/shopping.md) + [assembly link](https://github.com/cryptoadvance/specter-diy/blob/master/docs/assembly.md)
Waveshare QR scanner is recommended as it has a good quality/price ratio.

## *Is specter-DIY safe to use?*

Do not use it on mainnet yet unless it's only being used as one of the signers in multisig setup! But feel free to experiment with it on testnet, regtest or signet.

## *I'm wondering what if someone takes the device? How does Specter-DIY approach this scenario?*

It supports passphrases as an additional security layer, but currently it has two modes of operation - agnostic when your secrets are not stored on the device and you need to enter recovery phrase every time you use the device, and reckless when it is stored on flash and can be extracted. 

We are working on smart card support so you could store your keys on removable secure element in a credit card form factor, as well as an option to encrypt secrets with a key stored on the SD card. See this recently opened [issue](https://github.com/cryptoadvance/specter-diy/issues/64) thanks to @Thomas1378 in the Telegram chat!

## *Currently there is a `specter_hwi.py` file, which implements the HWIClient for Specter-DIY. Is there any reason you didn't add that directly to HWI?*

Putting it into HWI means: "this is a hardware wallet people should consider using for real". Currently, we would strongly advice NOT to use USB with Specter-DIY, but to use QR codes instead.

We will make a pull request to HWI when we think it's safe enough. In particular when we will have a secure bootloader that verifies signatures of the firmware, and USB communication is more reliable. 

## *Do you have a physical security design?*

No security at the moment, but it also doesn't store the private key. Working on integration of secure element similar to the ColdCard's (mikroe secure chip). At the moment it's more like a toy.

## *Is there a simulator I can try the Specter-DIY with?*

Yes. Specter-DIY in simulator-mode simulates QR code scanner over TCP, see [here](https://diybitcoinhardware.com/f469-disco/simulator/?script=https://raw.githubusercontent.com/diybitcoinhardware/f469-disco/master/docs/tutorial/4_miniwallet/main.py)

## *Is there a goal to get Specter-DIY loading firmware updates from the SD card?*

At the moment we don't have a proper bootloader and secure element integration yet, but we're moving in that direction! 
I think SD card is a good choice, also QR codes might be possible, but we need to experiment with them a bit.

## *Can Specter-DIY register cosigner xpubs like ColdCard? I know you wipe private keys on shutdown, but do you save stuff like that?*

Yes, we keep wallet descriptors and other public info.

## *Once you add the javacard (secure element) you'll save the private keys, too?*

With the secure element you will have three options:

 - agnostic mode, forgets key after shutdown
 - store key on the smartcard but do all crypto on application MCU
 - store key and do crypto on the secure element

Last seems to be the most secure, but then you trust proprietary crypto implementation. Second option saves private key on the secure element under pin protection, but also encrypted, so secure element never knows the private key.

# Troubleshooting questions

# I can't flash my device via Mini-USB ?

There is a file called `FAIL.txt` saying `The interface firmware FAILED to reset/halt the target MCU`

The Device is probably protected. You can't upgrade via MiniUSB anymore but just via SD-card. Please carefully read the Release-notes.

# I want to do a factory-reset. How can i remove the protection?

https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/remove_protection.md

## *Does anyone have any tips on mounting the power bank and QR code scanner to the STM32 board in a somewhat ergonomic manner?*

Use the smallest powerbank possible.

## *With achow's HWI tool, input and output PSBT are the same. And with Electrum 4, I get a rawtransaction, not a base64 PSBT.*

I solved my issue, it turns out my PSBT needed bip32 hints (whatever that means) included. I can now open lightning channels straight from hardware wallet!

# TECHNICAL QUESTIONS (not dev related)

## *Does specter-desktop require `txindex=1` to be set in your `bitcoin.conf`?*

No, but you need to enable wallets! `disablewallet=0`

## *Does specter-desktop specify an RPC wallet in the `bitcoin.conf` or append wallet name to node url?*

It specifes `-rpcwallet` with every call to `bitcoin-cli`


