# Developer notes for Specter-DIY

## Compiling the code yourself

See the [build documentation](build.md) for instructions on how to compile the code.

## Enabling developer mode

By default developer mode and USB communication are turned off. This means that when you connect the board to the computer it will NOT mount the `PYBFLASH` anymore and there will be no way to connect to debug shell.


~~To turn on the developer mode get to the main screen (enter PIN code, generate recovery phrase, enter password), and then go to **Settings - Security - turn on Developer mode - Save**.~~
(Currently deactivated for securtiy reasons)

~~Now the board will restart and get mounted to the computer as before. You can also connect to the board over miniUSB and get to interactive console (baudrate 115200). You can use `screen` or `putty` or `minicom` for that, i.e. `screen /dev/tty.usbmodem14403 115200`.~~

In order to connect to the board, modify those lines in [boot.py](https://github.com/cryptoadvance/specter-diy/blob/2f51e152bcdb184cf719792e6c5f972214e3dd36/boot/main/boot.py#L33-L40) like this:
```python
# configure usb from start if you want, 
# otherwise will be configured after PIN
pyb.usb_mode("VCP+MSC") # debug mode with USB and mounted storages from start
#pyb.usb_mode("VCP") # debug mode with USB from start
# disable at start
# pyb.usb_mode(None)
```

and after flashing, you can connect with something like:
```
# Linux
screen /dev/ttyACM0 115200 # or maybe ttyACM1 or ttyACM2
# Mac
screen /dev/tty.usbmodem14403 115200`.
```


## Writing a simple app

Specter can be extended with custom apps. Most of the functionality is already splitted into apps, like `WalletManager` to manage your wallets, `MessageApp` to sign bitcoin messages, `XpubApp` to show master public keys etc.

Check out the [apps](../src/apps) folder to understand how they work.

TODO: More detailed description
