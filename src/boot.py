# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal

import pyb, os, time

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

# poweroff on button press
pwrcb = lambda e: pwr.off()
pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

from platform import USB_ENABLED, DEV_ENABLED

# set up usb mode
if USB_ENABLED and DEV_ENABLED:
    pyb.usb_mode('CDC+MSC')
elif USB_ENABLED:
    pyb.usb_mode('CDC')
elif DEV_ENABLED:
    pyb.usb_mode('MSC')
else:
    pyb.usb_mode(None)

if DEV_ENABLED:
    repl = pyb.UART('YB',115200)
    # redirect REPL to STLINK UART
    os.dupterm(repl,0)
if USB_ENABLED:
    # unconnect REPL from USB
    os.dupterm(None, 1)

# pyb.main('main.py') # main script to run after this one
# pyb.usb_mode('CDC+MSC') # act as a serial and a storage device
# pyb.usb_mode('CDC+HID') # act as a serial device and a mouse
