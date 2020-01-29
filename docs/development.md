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
