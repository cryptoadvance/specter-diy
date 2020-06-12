# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal

import pyb, os, time
import platform

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

# poweroff on button press
pwrcb = lambda e: pwr.off()
pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# uncomment this lines if you want to override DEV_ENABLED and USB_ENABLED
# platform.DEV_ENABLED = True
# platform.USB_ENABLED = True

# set up usb mode
if platform.USB_ENABLED and platform.DEV_ENABLED:
    pyb.usb_mode('CDC+MSC')
elif platform.USB_ENABLED:
    pyb.usb_mode('CDC')
elif platform.DEV_ENABLED:
    pyb.usb_mode('CDC+MSC')
else:
    pyb.usb_mode(None)

if platform.DEV_ENABLED and platform.USB_ENABLED:
    repl = pyb.UART('YB',115200)
    # redirect REPL to STLINK UART
    os.dupterm(repl,0)
if platform.USB_ENABLED:
    # unconnect REPL from USB
    os.dupterm(None, 1)
