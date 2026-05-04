# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal
import pyb, os, micropython, time
import sys

# Clean sys.path from qspi
# Shouldn't happen in production, but just in case.
for p in sys.path:
    if "qspi" in sys.path:
        sys.path.remove(p)

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

version = "<version:tag10>0101000199</version:tag10>"

# Battery monitor: try STC3100 fuel gauge (Shield v1), fall back to ADC (Shield-BE)
i2c = pyb.I2C(1)
i2c.init()
_has_fuel_gauge = 112 in i2c.scan()
if _has_fuel_gauge:
    i2c.mem_write(0b00010000, 112, 0)

leds = [pyb.LED(i) for i in range(1,5)]
# poweroff on button press
def pwrcb(e):
    micropython.schedule(poweroff, 0)

# callback scheduled from the interrupt
def poweroff(_):
    # make sure it disables power no matter what
    try:
        for led in leds:
            led.toggle()
        # stop battery management
        if _has_fuel_gauge and 112 in i2c.scan():
            i2c.mem_write(0, 112, 0)
        # sync filesystem
        os.sync()
        time.sleep_ms(300)
    finally:
        # disable power
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
pyb.usb_mode(None)
os.dupterm(None,0)
os.dupterm(None,1)

# inject version and battery monitor into platform module
import platform
platform.version = version
platform.bootloader_locked = True
platform.build_type = "disco"
if _has_fuel_gauge:
    platform.i2c = i2c
else:
    # Shield-BE: ADC-based battery measurement (no STC3100 fuel gauge)
    try:
        platform.bat_adc = pyb.ADC(pyb.Pin("A7", pyb.Pin.IN))
        platform.chg_state_pin = pyb.Pin("H6", pyb.Pin.IN, pyb.Pin.PULL_UP)
    except Exception as e:
        print("Shield-BE battery setup failed:", e)
