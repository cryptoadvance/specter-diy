# Developer notes for Specter-DIY

## Compiling the code yourself

See the [build documentation](build.md) for instructions on how to compile the code.

## Enabling developer mode

By default USB communication is off. This means that when you connect the board to the computer it will NOT mount the `PYBFLASH` anymore and there will be no way to connect to debug shell.

In order to connect to the board, modify those lines in [boot.py](https://github.com/cryptoadvance/specter-diy/blob/2f51e152bcdb184cf719792e6c5f972214e3dd36/boot/main/boot.py#L33-L40) like this:
```python
# configure usb from start if you want, 
# otherwise will be configured after PIN
pyb.usb_mode("VCP+MSC") # debug mode with USB and mounted storages from start
#pyb.usb_mode("VCP") # debug mode with USB from start
# disable at start
# pyb.usb_mode(None)
# os.dupterm(None,0)
# os.dupterm(None,1)
```

and after flashing, restart the device, go to Device settings > Communication > USB communication, turn it on and Confirm. Then you can connect using the micro-USB port and with something like:
```
# Linux
screen /dev/ttyACM0 115200 # or maybe ttyACM1 or ttyACM2
# Mac
screen /dev/tty.usbmodem14403 115200`.
```

All `print()` statements will appear in the terminal output. You can keep both the mini-USB and micro-USB connected at the same time, with the power jumper in either position. This makes it easier to flash the firmware and then connect to the device.

## Writing a simple app

Specter can be extended with custom apps. Most of the functionality is already splitted into apps, like `WalletManager` to manage your wallets, `MessageApp` to sign bitcoin messages, `XpubApp` to show master public keys etc.

Check out the [apps](../src/apps) folder to understand how they work.

TODO: More detailed description
