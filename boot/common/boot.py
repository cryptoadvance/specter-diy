import pyb, os, micropython, time
import sys

try:
    import bootconf
except ImportError:
    class bootconf:
        VERSION = "<version:tag10>0101000199</version:tag10>"
        BOOTLOADER_LOCKED = True
        BUILD_TYPE = "disco"
        DISABLE_USB_AT_START = True
        MAIN_SCRIPT = None


STC3100_ADDR = 112
BAT_MEAS_PIN = "A7"
CHG_STATE_PIN = "H6"


# Clean sys.path from qspi
# Shouldn't happen in production, but just in case.
for p in list(sys.path):
    if "qspi" in p:
        sys.path.remove(p)


# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

version = bootconf.VERSION

fuel_gauge_i2c = None
fuel_gauge_active = False

leds = [pyb.LED(i) for i in range(1, 5)]


def setup_battery_monitor(platform):
    global fuel_gauge_i2c
    global fuel_gauge_active

    platform.i2c = None
    platform.bat_adc = None
    platform.chg_state_pin = None

    try:
        fuel_gauge_i2c = pyb.I2C(1)
        fuel_gauge_i2c.init()
        if STC3100_ADDR in fuel_gauge_i2c.scan():
            fuel_gauge_i2c.mem_write(0b00010000, STC3100_ADDR, 0)
            fuel_gauge_active = True
            platform.i2c = fuel_gauge_i2c
            return
    except Exception as e:
        print("Fuel gauge setup failed:", e)
        fuel_gauge_i2c = None

    try:
        platform.bat_adc = pyb.ADC(pyb.Pin(BAT_MEAS_PIN, pyb.Pin.IN))
        # PULL_UP ensures CHG_STATE reads HIGH (complete) when no charger is connected
        platform.chg_state_pin = pyb.Pin(CHG_STATE_PIN, pyb.Pin.IN, pyb.Pin.PULL_UP)
    except Exception as e:
        print("ADC battery setup failed:", e)


# poweroff on button press
def pwrcb(e):
    micropython.schedule(poweroff, 0)


# callback scheduled from the interrupt
def poweroff(_):
    # make sure it disables power no matter what
    try:
        for led in leds:
            led.toggle()
        if fuel_gauge_active and fuel_gauge_i2c is not None:
            fuel_gauge_i2c.mem_write(0, STC3100_ADDR, 0)
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


pyb.ExtInt(pyb.Pin("B1"), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

if bootconf.DISABLE_USB_AT_START:
    pyb.usb_mode(None)
    os.dupterm(None, 0)
    os.dupterm(None, 1)


import platform

platform.version = version
platform.bootloader_locked = bootconf.BOOTLOADER_LOCKED
platform.build_type = bootconf.BUILD_TYPE

setup_battery_monitor(platform)

if bootconf.MAIN_SCRIPT:
    pyb.main(bootconf.MAIN_SCRIPT)
