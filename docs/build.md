# Build

Clone the repository recursively `git clone https://github.com/cryptoadvance/specter-diy.git --recursive`

`bootloader` folder contains a [secure bootloader](https://github.com/cryptoadvance/specter-bootloader) that you can customize with your own firmware signing keys.

## Prerequisities

There are multiple ways to get all necessary tools. The recommended way is to use the Nix flake with direnv.
If that's too complicated for you, you can use the traditional `nix-shell` or install the tools manually (which mighty be tricky to get the dependencies right).

### Nix flake (Recommended)

The easiest way to get all necessary tools is to use the Nix flake from the root of the repository. You need to have [Nix](https://nixos.org/) (on Mac use [determinate](https://github.com/DeterminateSystems/nix-installer)) with flakes enabled.
Install direnv with `brew install direnv` (on Mac) or `sudo apt install direnv` (on Linux).

Make sure that [flakes are enabled](https://nixos.wiki/wiki/Flakes) in your Nix config.

```sh
# Enter development shell
nix develop

# Or use with direnv for automatic activation
direnv allow
```


### Nix shell

Alternatively, you can use the traditional `shell.nix`:

```sh
nix-shell
```
You'll need to have [Nix](https://nixos.org/) installed as well.

### Prerequisities (Manually): Board

To compile the firmware for the board you will need `arm-none-eabi-gcc` compiler.

**Debian/Ubuntu**:
```sh
sudo apt-get install build-essential gcc-arm-none-eabi binutils-arm-none-eabi gdb-multiarch openocd
```

**Archlinux**:
```sh
sudo pacman -S arm-none-eabi-gcc arm-none-eabi-binutils openocd base-devel python-case
```
You might need change default gcc flag settings with `CFLAGS_EXTRA="-w"`. Export it or set the variable before of `make`
to avoid warnings being raised as errors.

**MacOS**:
```sh
brew tap ArmMbed/homebrew-formulae
brew install arm-none-eabi-gcc
```

On **Windows**: Install linux subsystem and follow Linux instructions.

### Prerequisities (Manually): Simulator

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

To build custom bootloader and firmware that you will be able to sign check out the bootloader doc on [self-signed firmware](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/selfsigned.md). To wipe flash and remove protections on the device with the secure bootloader check out [this doc](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/remove_protection.md).

To build an open firmware (no bootloader and signature verifications) run `make disco`. The result is the `bin/specter-diy.bin` file that you can copy-paste to the board over miniUSB.

To build a simulator run `make unix` - it will compile a micropython simulator for mac/unix and store it under `bin/micropython_unix`.

To launch a simulator either run `bin/micropython_unix simulate.py` or simly run `make simulate`.

If something is not working you can clean up with `make clean`

## Run Unittests

Currently unittests work only on linuxport, and there are... not many... Contributions are very welcome!

```
make test
```
