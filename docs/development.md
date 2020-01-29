# Developer notes for Specter-DIY

## Compiling the code yourself

We use this build as a platform for Specter: https://github.com/diybitcoinhardware/f469-disco

To compile the firmware you will need `arm-none-eabi-gcc` compiler.

On MacOS install it using brew: `brew install arm-none-eabi-gcc`

On Linux: `sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi gdb-arm-none-eabi openocd`

Run `./build.sh` script, it may work. Or not. If not - please open an issue and we will try to figure out.

At the end you should get a `specter-diy.bin` file in the root that you can copy to the device.

### Micropython with editable Specter firmware

By default when firmware is compiled all python files are optimized and frozen in the firmware.

In order to develop and test firmware without recompiling it every time 
one can use a micropython build without specter files and copy them to the board manually:

1. Go to `f469-disco` folder and run `build_f469.sh`
2. Copy `upy-f469disco.bin` to the board (miniUSB, volume `DIS_F469NI`)
3. Connect over microUSB - you will see `PYBFLASH` volume mounted
4. Copy content of `src` folder to `PYBFLASH`
5. Restart the board - it should work

In case above you will be able to change all specter files, but bitcoin library will be frozen in the firmware.

### Micropython without any frozen files

Normally you don't want to change bitcoin library on the board directly, but if you really want to, use `-empty` binary instead. In this case the wallet will work a bit slower.

1. Go to `f469-disco` folder and run `build_f469_empty.sh`
2. Copy `upy-f469disco-empty.bin` to the board (miniUSB, volume `DIS_F469NI`)
3. Connect over microUSB - you will see `PYBFLASH` volume mounted
4. Copy content of the `f469-disco/libs` folder to the `PYBFLASH`
5. Copy content of `src` folder to `PYBFLASH`
6. Restart the board - it should work

## Enabling developer mode

By default developer mode and USB communication are turned off. This means that when you connect the board to the computer it will NOT mount the `PYBFLASH` anymore and there will be no way to connect to interactive shell.

To turn on the developer mode get to the main screen (enter PIN code, generate recovery phrase, enter password), and then go to **Settings - Security - turn on Developer mode - Save**.

Now the board will restart and get mounted to the computer as before. You can also connect to the board over miniUSB and get to interactive console (baudrate 115200). You can use `screen` or `putty` or `minicom` for that, i.e. `screen /dev/tty.usbmodem14403 115200`.

By default the board is in an inifinite loop, but you can press Ctrl+C to interrupt the main loop. Type `entropy` for example, and you will see what is the entropy currently loaded in the wallet. To resume wallet operation run `ioloop()` and the GUI will become responsive again.

In the next section we will run the board in non-blocking mode such that you could test all the functionality including the GUI from interactive console.

## Interactive testing

There are a few changes we need to make to enter interactive mode:

In `boot.py` we uncomment two lines, first one right after `from platform import ...`, we need to override `DEV_ENABLED` to make sure we don't lock everything up:

```py
# uncomment this lines if you want to override DEV_ENABLED
platform.DEV_ENABLED = True
platform.USB_ENABLED = True
```

and at the very end we override the main script that will run on the board:

```py
# uncomment this line to get interactive access over REPL
pyb.main('repl.py')
```

Now if you reboot the board and connect to it over serial you will see an interactive console where you can type stuff. And GUI is still responsive.

For example, you can type the following:

```py
>>> specter.entropy = b'a'*16
>>> specter.init_keys("")
```

And you will get to the main screen right away. You can check the mnemonic now (in Settings) - it should be `gesture arch flame security bid radar machine club gesture arch flame search`.

**IMPORTANT** *Serial port over miniUSB is extremely unreliable! It's because STLink MCU that forwards all the data to the computer was programmed badly by STMicroelectronics, so if you paste large chinks of data there it can crash!*

To avoid this problem it makes sense to redirect REPL to USB port instead of UART.
Make sure you enabled USB in `boot.py`: `platform.USB_ENABLED = True` and uncomment lines in `repl.py`:

```py
platform.USB_ENABLED = False
usb = pyb.USB_VCP()
os.dupterm(usb, 1)
```

Now you should be able to communicate with the board over microUSB port - way more reliable communication channel.

## Getting to the right place from start

As we just saw it's easy to get to the right point of the wallet logic with just a few commands. If you are working on something particular it makes sense to add these lines directly to `repl.py`.

If you check the content of the `repl.py` file there are already a few lines we can uncomment. For example we can redefine folder that will be used to store userdata:

```py
# uncomment these lines if you want to use another folder for user data
import platform
platform.storage_root = platform.storage_root.replace("userdata", "testdata")
```

Or we can load entropy and directly get to the transaction confirmation screen:

```py
specter.entropy = b'a'*16
specter.init_keys("")
b64_tx = "cHNidP8BAHICAAAAASennaTt01cWyJ+TqGWjRFWIWYVnS0Y5ryTOUZ8CYfOjAQAAAAD/////AoCWmAAAAAAAF6kU882+nVMDKGj4rKzjDB6NjyJqSBCHaD9dBQAAAAAWABRBSsx9Jvr9HbkmtcrVUTmyQwZ8RAAAAAAAAQEfAOH1BQAAAAAWABQv2DQYUfvhErERHLIhTpALzVSuwyIGA/atwQoWuTysuzKNRc9RFhoyKQiKbkH6Ij/n6P4aGJ0BGC1zTIlUAACAAQAAgAAAAIAAAAAAAAAAAAAAIgIDD0zYLV7pO7S8QpLMj6a/uMCljkXFdh0D5XBHupOcGIoYLXNMiVQAAIABAACAAAAAgAEAAAAAAAAAAA=="
specter.parse_transaction(b64_tx)
```

We can even confirm this transaction from repl. It's not very straightforward at the moment and glitchy, but doable:

```py
# get the top popup - confirmation screen
from gui import popups
scr = popups.popups[-1]
# confirm the transaction
scr.confirm()
```

## Architecture of the wallet

... :(