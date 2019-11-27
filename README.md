# Specter-DIY

## DISCLAIMER

This firmware is **WORK IN PROGRESS — USE AT YOUR OWN RISK**, better on testnet. 

This wallet is a **FUNCTIONAL PROTOTYPE**. This means we use it to experiment with user interface, communication methods and new interesting features (like anti chosen-nonce protocol, CoinJoin and Lightning). But this prototype is not ment to be secure. That's why **we don't store your private keys on the device** by default - you need to type your recovery phrase every time you power it on.

We also have a #Reckless option that allows you to store recovery phrase on the device (no pin, no encryption - for testing and development purposes).

If something doesn't work open an issue here or ask a question in our [Telegram group](https://t.me/spectersupport) or [Slack](https://join.slack.com/t/spectersupport/shared_invite/enQtNzY4MTQ2MTg0NDY1LWQzMGMzMTk2MWE2YmVmNzE3ODgxODIxNWRlMzJjZTZlMDBlMjA5YzVhZjQ0NzJlNmE0N2Q4MzE0ZGJiNjM4NTY).

## What is this project for?

It is a Do-It-Yourself airgapped hardware wallet that uses QR codes for communication with the computer (i.e. [Specter Desktop app](https://github.com/cryptoadvance/specter-desktop) on top of Bitcoin Core). It can be used as an additional item in your multisignature setup that has a completely different security model:

- It can be built from off-the-shelf hardware - this reduces chance of the supply chain attack
- It is airgapped with a very limited uni-directional communication protocol (QR codes) - you control communication with the host
- It can be tuned and extended according to your security model. Most of it is written in python which makes the code easy to audit and change.

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

- [Waveshare scanner](https://www.waveshare.com/barcode-scanner-module.htm) - you will need to configure it to use UART for communication, solder a wire to the trigger button and connect to the D5 pin of the board. See more details [here](docs/waveshare.md).

Extra: battery & power charger/booster - docs will follow later.

We are also working on the kit that you could buy from us that will include a 3d printed case, QR code scanner, battery and charging circuit, but without the main part - dev board. This way supply chain attack is still not an issue as the security-critical components are bought from random electronic store.

## Installing the compiled code
* Connect the DISCO board to your computer via the mini USB cable on the top of the board.
    * The board should appear as a removable disk named DIS_F469NI.
* Go the Releases section of this github repo.
* Download the `specter-diy.bin` file from the latest release.
* Copy the bin file into the root of the DISCO filesystem.
* When the board is done loading the bin the board will reset itself and begin running the Specter UI.
* The on-screen UI should prompt you to calibrate the screen and then will take you to the Specter UI's "What do you want to do?" startup screen.

## Dev plan

- [x] Single key functionality
- [x] Reckless storage
- [x] Multisig
- [ ] Dynamic SD card support
- [ ] Secure element integration
- [ ] Secure boot
- [ ] DIY kit

## Video and screenshots

Check out [this Twitter thread](https://twitter.com/StepanSnigirev/status/1168923849699876881) to get an idea how it works.

A few pictures:

### Init screens

![](./docs/pictures/init.jpg)

### Wallet screens

![](./docs/pictures/wallet.jpg)


## Compiling the code yourself

_(This is an optional step for developers. Typical users can just run off the pre-compiled `specter-diy.bin` file referenced above)_

Micropython now. Ref: https://github.com/diybitcoinhardware/f469-disco

To compile the firmware you will need `arm-none-eabi-gcc` compiler.

On MacOS install it using brew: `brew install arm-none-eabi-gcc`

On Linux: `sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi gdb-arm-none-eabi openocd`

Run `./build.sh` script, it may work. Or not. If not - please open an issue and we will try to figure out.

At the end you should get a `specter-diy.bin` file in the root that you can copy to the device.

### Micropython without frozen firmware

By default when firmware is compiled all python files are optimized and frozen in the firmware.

In order to develop and test firmware without recompiling it every time 
one can use an empty micropython build and copy python files to the board.

1. Go to `f469-disco` folder and run `build_f469_empty.sh`
2. Copy `upy-f469disco-empty.bin` to the board (miniUSB, volume `DIS_F469NI`)
3. Connect over microUSB - you will see `PYBFLASH` volume mounted
4. Copy content of the `f469-disco/libs` folder to the `PYBFLASH`
6. Copy content of `src` folder to `PYBFLASH`
7. Restart the board - it should work

### Simulator

Simulator requires `SDL` library to be installed (`sudo apt install libsdl2-dev` on Linux and `brew install sdl2` on Mac):

To compile the unixport simulator go to `f469-disco` folder and run `./build_unixport.sh`.

If everything goes well you will get a `micropython_unix` binary in this folder.

Now you can run `micropython_unix` binary and ask it to run `main` function of `main.py` file:

```
cd ../src
../f469-disco/micropython_unix -c "import main; main.main()"
```

You should see the screen with the wallet interface. As in unixport we don't have QR code scanner when scan is required the micropython console will ask you to enter the string that should have been scanned by the QR scanner. The simulator is also printing content of the QR codes displayed on the screen to the console.
