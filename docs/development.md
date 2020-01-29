# Developer noted for Specter-DIY

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
