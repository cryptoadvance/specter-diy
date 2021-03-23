# Apps tools

This is a very experimental feature, disabled in production for now. Only for developers atm.

## `combine.py`

Combines multiple files in the folder into a single python script so it can be frozen using `mpy-cross`.

It is kinda ugly and assumes that nothing important happens on import.

Usage: `python3 combine.py /path/to/directory/`

Skip this step if your app is in one file already.

After that use `mpy-cross /path/to/monofile.py` and it will create an `.mpy` file for your app. `mpy-cross` is located in `specter-diy/f469-disco/micropython/mpy-cross/mpy-cross`. For unixport use `mpy-cross -mcache-lookup-bc monofile.py`.

## `signapp.py`

Signs an `.mpy` file with hard-coded private keys (for now) and creates `.mapp` file that can be installed on the board from the SD card.

Usage: `python3 signapp.py appfile.mpy`
