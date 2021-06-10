# Developer notes for Specter-DIY

## Compiling the code yourself

We use this build as a platform for Specter: https://github.com/diybitcoinhardware/f469-disco

To compile the firmware you will need `arm-none-eabi-gcc` compiler.

On MacOS install it using brew: `brew install arm-none-eabi-gcc`

On Debian: `sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi gdb-arm-none-eabi openocd`

On Arch Linux: `sudo pacman -S arm-none-eabi-gcc arm-none-eabi-binutils arm-none-eabi-gdb arm-none-eabi-newlib openocd`

Run `make disco` to get the binary or `make unix` to compile the simulator. They will be in the `bin` folder.

`specter-diy.bin` file is the firmware that you need to copy to the device.

The easiest way to start developing is to use a [simulator](./simulator.md), and when you are done - try it on a real hardware.

## Enabling developer mode

By default developer mode and USB communication are turned off. This means that when you connect the board to the computer it will NOT mount the `PYBFLASH` anymore and there will be no way to connect to debug shell.

To turn on the developer mode get to the main screen (enter PIN code, generate recovery phrase, enter password), and then go to **Settings - Security - turn on Developer mode - Save**.

Now the board will restart and get mounted to the computer as before. You can also connect to the board over miniUSB and get to interactive console (baudrate 115200). You can use `screen` or `putty` or `minicom` for that, i.e. `screen /dev/tty.usbmodem14403 115200`.

## Writing a simple app

Specter can be extended with custom apps. Most of the functionality is already splitted into apps, like `WalletManager` to manage your wallets, `MessageApp` to sign bitcoin messages, `XpubApp` to show master public keys etc.

Check out the [apps](../src/apps) folder to understand how they work.

TODO: More detailed description
