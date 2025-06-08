# Build

Clone the repository recursively `git clone https://github.com/cryptoadvance/specter-diy.git --recursive`

`bootloader` folder contains a [secure bootloader](https://github.com/cryptoadvance/specter-bootloader) that you can customize with your own firmware signing keys.

Check [reproducible-build](./reproducible-build.md) if you want to use Docker.

## Prerequisites for the Nix build

There are multiple ways to get all necessary tools. The recommended way is to use the Nix flake with direnv.
If that's too complicated for you, you can use the traditional `nix-shell` or install the tools manually (which mighty be tricky to get the dependencies right).

### Install Nix on Ubuntu 24.04

```sh
sudo apt update
sudo apt install nix
```

Enable the required experimental features for flakes and the new CLI:

```sh
sudo mkdir -p /etc/nix
echo "experimental-features = nix-command flakes" | sudo tee -a /etc/nix/nix.conf
```

Add your user to the `nix-users` group so you can access the Nix store:

```sh
sudo usermod -aG nix-users "$USER"
newgrp nix-users
```

### Nix flake (Recommended)

The easiest way to get all necessary tools is to use the Nix flake from the root of the repository. You need to have [Nix](https://nixos.org/) (on Mac use [determinate](https://github.com/DeterminateSystems/nix-installer)) with flakes enabled. This only works with Nix >2.7 (check with `nix --version`).
Install direnv with `brew install direnv` (on Mac) or `sudo apt install direnv` (on Linux). direnv automatically loads and unloads the environment described in `.envrc` when you enter or leave the repository, so the development tooling is ready without extra commands.

Make sure that [flakes are enabled](https://nixos.wiki/wiki/Flakes) in your Nix config. On Linux systems, your user might need to be added to the nix-users group.

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
brew install arm-none-eabi-gcc
brew install sdl2
```

To make the SDL2 library available to your C/C++ toolchain, ensure that Homebrew’s include and library paths are added to the compiler and linker flags. If they are not already set, you can add the following lines to your shell profile (commonly `~/.zprofile` or `~/.bash_profile`) or configure them in another way before making the Unix build:

```sh
export LDFLAGS="-L/opt/homebrew/lib $LDFLAGS"
export CPPFLAGS="-I/opt/homebrew/include $CPPFLAGS"
export CFLAGS="-I/opt/homebrew/include $CFLAGS"
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

All build commands might need a prefix like `nix develop -c` or need to be run from `nix develop` shell. If you use direnv, you don't need to do anything, apart from an initial `direnv allow`.

### Starting the build

After entering the development shell (either with `nix develop` or via direnv), start the default firmware build with:

```sh
make disco
```

This produces `bin/specter-diy.bin`, which can be flashed by dragging the file onto the board's virtual mass-storage drive or by
using programming tools such as STM32CubeProgrammer.

To build custom bootloader and firmware that you will be able to sign check out the bootloader doc on [self-signed firmware](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/selfsigned.md). To wipe flash and remove protections on the device with the secure bootloader check out [this doc](https://github.com/cryptoadvance/specter-bootloader/blob/master/doc/remove_protection.md).

To build an open firmware (no bootloader and signature verifications) run `make disco`. It also produces the `bin/specter-diy.bin` image ready for flashing via the board's virtual drive or external programming tools.

To build a simulator run `make unix` - it will compile a micropython simulator for mac/unix and store it under `bin/micropython_unix`.

To launch a simulator either run `bin/micropython_unix simulate.py` or simly run `make simulate`.

If something is not working you can clean up with `make clean`

### Automated build script

The top-level `build_firmware.sh` helper runs the full secure build, including the bootloader and signed upgrade package. It
also creates `release/disco-nobootloader.{bin,hex}`, which contain the plain firmware without the secure bootloader. The
`disco-nobootloader.bin` image is identical to the `nix build` output and can be flashed directly to a development board when
you need a faster iteration loop.

## Run Unittests

Currently unittests work only on linuxport, and there are... not many... Contributions are very welcome!

```
make test
```
