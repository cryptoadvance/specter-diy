# boot.py for Shield-BE (Budget Edition)
# Configures ADC-based battery level measurement via the BAT_MEAS circuit:
#   BATT_P -> Q303 (AO3401A P-FET, enabled by Q302/PWR_HOLD2)
#           -> voltage divider R309=100k / R310=150k -> BAT_MEAS
# BAT_MEAS = VBAT * 0.6  (divider ratio 150/250)
# The P-FET is on whenever PWR_HOLD2 is high (i.e. the device is running),
# so no extra enable step is needed before reading the ADC.
#
# CHG_STATE from TP4056 charger: LOW = charging, HIGH/floating = complete.
#
# Pin assignments, confirmed from the Shield-BE/discovery-board connector map:
#   BAT_MEAS / SC_AUX2  -- J203 pin 2 -- PA7 (ADC-capable)
#   CHG_STATE           -- J203 pin 3 -- PH6
BAT_MEAS_PIN = "A7"
CHG_STATE_PIN = "H6"

import pyb, os, micropython, time
import sys

# Clean sys.path from qspi
# Shouldn't happen in production, but just in case.
for p in sys.path:
    if "qspi" in p:
        sys.path.remove(p)

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

version = "<version:tag10>0101000199</version:tag10>"

leds = [pyb.LED(i) for i in range(1, 5)]

# poweroff on button press
def pwrcb(e):
    micropython.schedule(poweroff, 0)

# callback scheduled from the interrupt
def poweroff(_):
    # make sure it disables power no matter what
    try:
        for led in leds:
            led.toggle()
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

# disable USB at start
pyb.usb_mode(None)
os.dupterm(None, 0)
os.dupterm(None, 1)

# inject version into platform module
import platform
platform.version = version
platform.bootloader_locked = True
platform.build_type = "disco"

# Set up ADC-based battery measurement.
# No I2C fuel gauge (STC3100) is present on Shield-BE.
try:
    platform.bat_adc = pyb.ADC(pyb.Pin(BAT_MEAS_PIN, pyb.Pin.IN))
    # PULL_UP ensures CHG_STATE reads HIGH (complete) when no charger is connected
    platform.chg_state_pin = pyb.Pin(CHG_STATE_PIN, pyb.Pin.IN, pyb.Pin.PULL_UP)
except Exception as e:
    print("Shield-BE battery setup failed:", e)
