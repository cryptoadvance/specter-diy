# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal
import pyb, os, micropython, time

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

version = "<version:tag10>0100900001</version:tag10>"

leds = [pyb.LED(i) for i in range(1,5)]
# poweroff on button press
def pwrcb(e):
    micropython.schedule(poweroff, 0)

# callback scheduled from the interrupt
def poweroff(_):
    for led in leds:
        led.toggle()
    os.sync()
    time.sleep_ms(300)
    pwr.off()
    time.sleep_ms(300)
    # will never reach here
    for led in leds:
        led.toggle()

pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# configure usb from start if you want, 
# otherwise will be configured after PIN
# pyb.usb_mode("VCP+MSC") # debug mode with USB and mounted storages from start
# pyb.usb_mode("VCP") # debug mode with USB from start
# disable at start
# pyb.usb_mode(None)
# os.dupterm(None,0)
# os.dupterm(None,1)

# inject version to platform module
import platform
platform.version = version
platform.bootloader_locked = False
platform.build_type = "debug"

# Battery monitor: try STC3100 fuel gauge (Shield v1), fall back to ADC (Shield-BE)
i2c = pyb.I2C(1)
i2c.init()
if 112 in i2c.scan():
    i2c.mem_write(0b00010000, 112, 0)
    platform.i2c = i2c
else:
    try:
        platform.bat_adc = pyb.ADC(pyb.Pin("A7", pyb.Pin.IN))
        platform.chg_state_pin = pyb.Pin("H6", pyb.Pin.IN, pyb.Pin.PULL_UP)
    except Exception as e:
        print("Shield-BE battery setup failed:", e)

# uncomment to run some custom main:
pyb.main("hardwaretest.py")
