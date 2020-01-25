# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal

import pyb, os, time

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

# poweroff on button press
pwrcb = lambda e: pwr.off()
pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# pyb.usb_mode('CDC')
# check if blue button is pressed
# userbtn = pyb.Switch()

# leds = [pyb.LED(i) for i in range(1,5)]
# for led in leds:
#     led.on()
# for led in leds[::-1]:
#     time.sleep(0.25)
#     led.off()

# if not userbtn.value():
#     # don't use USB
#     pyb.usb_mode('CDC')
# else:
#     # use USB as mass storage for development
#     pyb.usb_mode('CDC+MSC')

repl = pyb.UART('YB',115200)
# redirect REPL to STLINK UART
os.dupterm(repl,0)
# unconnect REPL from USB
os.dupterm(None, 1)
# pyb.main('main.py') # main script to run after this one
# pyb.usb_mode('CDC+MSC') # act as a serial and a storage device
# pyb.usb_mode('CDC+HID') # act as a serial device and a mouse
