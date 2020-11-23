# Build

Clone the repository recursively `git clone https://github.com/cryptoadvance/specter-diy.git --recursive`

`bootloader` folder contains a [secure bootloader](https://github.com/cryptoadvance/specter-bootloader).

## Prerequisities

### Prerequisities: Board

To compile the firmware for the board you will need `arm-none-eabi-gcc` compiler.

On **MacOS** install it using brew:
```sh
brew tap ArmMbed/homebrew-formulae
brew install arm-none-eabi-gcc
```

On **Linux**:
```sh
sudo apt-get install gcc-arm-none-eabi binutils-arm-none-eabi gdb-multiarch openocd
```

On **Windows**: Install linux subsystem and follow Linux instructions.

### Prerequisities: Simulator

You may need to install SDL2 library to simulate the screen of the device.

**Linux**:
```sh
sudo apt install libsdl2-dev
```

**MacOS**:
```sh
brew install sdl2
```

**Windows**:
- `sudo apt install libsdl2-dev` on Linux side.
- install and launch [Xming](https://sourceforge.net/projects/xming/) on Windows side
- set `export DISPLAY=:0` on linux part

## Build

To build custom bootloader and firmware that you will be able to sign check out the bootloader doc on [self-signed firmware](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/selfsigned.md).

To build an open firmware (no bootloader and signature verifications) run `make disco`. The result is the `bin/specter-diy.bin` file that you can copy-paste to the board over miniUSB.

To build a simulator run `make unix` - it will compile a micropython simulator for mac/unix and store it under `bin/micropython_unix`.

To launch a simulator either run `bin/micropython_unix simulate.py` or simly run `make simulate`.

If something is not working you can clean up with `make clean`

## Run Unittests

Currently unittests work only on linuxport, and there are... not many... Contributions are very welcome!

```
make test
```
