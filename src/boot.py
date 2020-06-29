# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal

import pyb, os, time

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

# poweroff on button press
pwrcb = lambda e: pwr.off()
pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# configure usb from start if you want, 
# otherwise will be configured
# pyb.usb_mode("VCP+MSC") # debug mode without USB from start
