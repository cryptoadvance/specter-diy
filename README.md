# Specter-DIY

## DISCLAIMER

This firmware is **WORK IN PROGRESS — USE AT YOUR OWN RISK**, better on testnet. 

This wallet is a **FUNCTIONAL PROTOTYPE**. This means we use it to experiment with user interface, communication methods and new interesting features (like anti chosen-nonce protocol, CoinJoin and Lightning). But this prototype is not ment to be secure. That's why **we don't store your private keys on the device** - you need to type your recovery phrase every time you power it on.

We also have a #Reckless option that allows you to store recovery phrase on the device (no pin, no encryption - for testing purposes).

If something doesn't work open an issue here or ask a question in our [Telegram group](https://t.me/spectersupport) or [Slack](https://join.slack.com/t/spectersupport/shared_invite/enQtNzY4MTQ2MTg0NDY1LWQzMGMzMTk2MWE2YmVmNzE3ODgxODIxNWRlMzJjZTZlMDBlMjA5YzVhZjQ0NzJlNmE0N2Q4MzE0ZGJiNjM4NTY).

## What is this project for?

It is a Do-It-Yourself airgapped hardware wallet that uses QR codes for communication with the computer (i.e. [Specter Desktop app](https://github.com/cryptoadvance/specter-desktop) on top of Bitcoin Core). It can be used as an additional item in your multisignature setup that has a completely different security model:

- It can be built from off-the-shelf hardware - this reduces chance of the supply chain attack
- It is airgapped with a very limited uni-directional communication protocol (QR codes) - you control communication with the host
- It can be tuned and extended according to your security model

## Current status

Works for single key and multisig transactions.

Supported networks: Mainnet, Testnet, Regtest, Signet.

## Shopping list

While we are coding you can buy the components. Somehow expensive, but the price can be reducesed if you are ok with soldering.

Main part of the device is the developer board:

- STM32F469I-DISCO developer board (i.e. from [Mouser](https://eu.mouser.com/ProductDetail/STMicroelectronics/STM32F469I-DISCO?qs=kWQV1gtkNndotCjy2DKZ4w==) or [Digikey](https://www.digikey.com/product-detail/en/stmicroelectronics/STM32F469I-DISCO/497-15990-ND/5428811))
- **Mini**USB cable (for example [this](https://eu.mouser.com/ProductDetail/Omron-Automation-and-Safety/USB-MINIUSB?qs=sGAEpiMZZMt93J8DTi5DC6y9EQiX1Vkv))

For QR code scanner you have several options.

**Option 1.** Lazy, minimal soldering required, extremely nice scanner but pretty expensive:

- [Barcode Click](https://www.mikroe.com/barcode-click) + [Adapter](https://www.mikroe.com/arduino-uno-click-shield)

**Option 2.** Requires some soldering / mounting and configuration:

- [Waveshare scanner](https://www.waveshare.com/barcode-scanner-module.htm) - you will need to configure it to use UART for communication, solder a wire to the trigger button and connect to the D5 pin of the board. See more details [here](waveshare.md).

Extra: battery & power charger/booster - docs will follow later.

We are also working on the kit that you could buy from us that will include a 3d printed case, QR code scanner, battery and charging circuit, but without the main part - dev board. This way supply chain attack is still not an issue as the security-critical components are bought from random electronic store.

## Dev plan

- [x] Single key functionality
- [x] Reckless storage
- [x] Multisig
- [ ] SD card support
- [ ] Secure element integration
- [ ] Secure boot
- [ ] DIY kit

## Video and screenshots

Check out [this Twitter thread](https://twitter.com/StepanSnigirev/status/1168923849699876881) to get an idea how it works.

A few crappy pictures:

### Init screens

![](./docs/pictures/init.jpg)

### Wallet screens

![](./docs/pictures/wallet.jpg)
