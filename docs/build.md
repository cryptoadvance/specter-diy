# Build

Clone the repository recursively `git clone https://github.com/cryptoadvance/specter-diy.git --recursive`

`bootloader` folder contains a [secure bootloader](https://github.com/cryptoadvance/specter-bootloader) that you can customize with your own firmware signing keys.

## Prerequisities

### Nix shell

The easiest way to get all necessary tools is to run `nix-shell` from the root of the repository. You need to have [Nix](https://nixos.org/) installed.

### Prerequisities: Board

To compile the firmware for the board you will need `arm-none-eabi-gcc` compiler.

#### Debian/Ubuntu

```sh
sudo apt-get install build-essential gcc-arm-none-eabi binutils-arm-none-eabi gdb-multiarch openocd
```

#### Archlinux

```sh
sudo pacman -S arm-none-eabi-gcc arm-none-eabi-binutils openocd base-devel python-case
```
You might need change default gcc flag settings with `CFLAGS_EXTRA="-w"`. Export it or set the variable before of `make`
to avoid warnings being raised as errors.

#### MacOS

```sh
brew install arm-none-eabi-gcc
```

#### Windows

Install the Linux subsystem and follow Linux instructions. The recommended distribution as of this writing is **Ubuntu 22.04 LTS**.  It can be installed using the following command in the **administrator's PowerShell**:

```sh
# Install Ubuntu 22.04 as WSL Linux environment
wsl --install -d Ubuntu-22.04
# Start new instance of Ubuntu 22.04 (if multiple distros are present in system)
wsl -d Ubuntu-22.04
```

To install all the dependencies on Windows, make sure the **universe** repository is enabled and the package list is up to date. If not, here is a quick fix:

```sh
# Uncomment all lines in /etc/apt/sources.list that begin with # deb
sudo sed -i 's/^# deb/deb/' /etc/apt/sources.list
# Enable universe repository
sudo add-apt-repository universe
# Update package list
sudo apt update
```

### Prerequisities: Simulator

You may need to install SDL2 library to simulate the screen of the device.

#### Linux

```sh
sudo apt install libsdl2-dev
```

#### MacOS

```sh
brew install sdl2
```

To make the SDL2 library available to your C/C++ toolchain, ensure that Homebrew’s include and library paths are added to the compiler and linker flags. If they are not already set, you can add the following lines to your shell profile (commonly `~/.zprofile` or `~/.bash_profile`) or configure them in another way before making the Unix build:

```sh
export LDFLAGS="-L/opt/homebrew/lib $LDFLAGS"
export CPPFLAGS="-idirafter /opt/homebrew/include $CPPFLAGS"
export CFLAGS="-idirafter /opt/homebrew/include $CFLAGS"
```

#### Windows

- `sudo apt install libsdl2-dev` on Linux side.
- install and launch [Xming](https://sourceforge.net/projects/xming/) on Windows side
- set `export DISPLAY=:0` on linux part

[VcXsrv](https://github.com/marchaesen/vcxsrv) is another viable option for running X11 applications on Windows. Here is an example environment that should be configured on the WSL side:

```sh
export LIBGL_ALWAYS_INDIRECT=0
export LIBGL_ALWAYS_SOFTWARE=true
export DISPLAY=127.0.0.1:0
export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
```

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
