# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal
import pyb, os

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

# v1.4.1-rc1 - use odd rc for main firmware and even for debug
# so it's possible to upgrade from debug to main firmware.
# (rc99 is final version for production)
version = "<version:tag10>0100400201</version:tag10>"

# poweroff on button press
pwrcb = lambda e: pwr.off()
pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# configure usb from start if you want, 
# otherwise will be configured after PIN
# pyb.usb_mode("VCP+MSC") # debug mode without USB from start
# disable at start
# pyb.usb_mode(None)
# os.dupterm(None,0)
# os.dupterm(None,1)

# inject version to platform module
import platform
platform.version = version

# uncomment to run some custom main:
pyb.main("hardwaretest.py")