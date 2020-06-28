# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal

import pyb, os, time

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

# poweroff on button press
pwrcb = lambda e: pwr.off()
pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# set up usb mode to nothing at first,
# will be reconfigured during the runtime
pyb.usb_mode(None)
# pyb.usb_mode("VCP+MSC") # debug mode without USB from start

# # redirect repl to stlink
# stlk = pyb.UART('YB',9600)
# os.dupterm(stlk,0)
os.dupterm(None,0)
os.dupterm(None,1)
