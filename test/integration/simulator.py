# This is a micropython file to start Specter Simulator
import sys
if sys.implementation.name != "micropython":
	print("This file should run from micropython!")
	sys.exit(1)
sys.path.append('../../src')
sys.path.append('../../f469-disco/libs/common')
sys.path.append('../../f469-disco/libs/unix')
sys.path.append('../../f469-disco/usermods/udisplay_f469/display_unixport')

# make sure USB is enabled
from specter import Specter
Specter.usb = True

import main
# run on the regtest
main.main(network="regtest")