# boot.py -- run on boot-up for Shield-BE (Budget Edition)
# can run arbitrary Python, but best to keep it minimal
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

# inject version and battery ADC into platform module
import platform
platform.version = version
platform.bootloader_locked = True
platform.build_type = "disco"

# ---------------------------------------------------------------------------
# Shield-BE battery voltage measurement via ADC
#
# The BAT_MEAS net is connected to the SC_AUX2 pin (PA3, ADC1_IN3).
# SC_AUX2 is unused as a smartcard signal; it was repurposed here as ADC.
#
# Resistor divider (Q303 P-MOSFET disconnects it when powered off):
#   R309 = 100 kΩ  (upper: BATT_P → ADC pin)
#   R310 = 150 kΩ  (lower: ADC pin → GND)
#   V_BATT = V_ADC × (100k + 150k) / 150k = V_ADC × 5/3
#
# CHG_STATE is the TP4056 CHRG open-drain output (LOW = charging,
# HIGH/float = not charging / charge complete).  R313 (100 kΩ) pulls it high.
# Set chg_pin below once the MCU GPIO connected to CHG_STATE is confirmed
# from the interface schematic / hardware bring-up.
# ---------------------------------------------------------------------------

# Battery voltage ADC on PA3 (ADC1_IN3)
platform.adc = pyb.ADC(pyb.Pin('A3'))

# Charging state GPIO – update 'TODO_CHG_PIN' to the correct MCU pin name
# once confirmed from the stm32f469i-disco-interface schematic.
# Example: platform.chg_pin = pyb.Pin('A8', pyb.Pin.IN, pyb.Pin.PULL_UP)
platform.chg_pin = None  # TODO: set to CHG_STATE MCU pin
