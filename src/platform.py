# detect if it's a hardware device or linuxport
import sys, os
simulator = (sys.platform != 'pyboard')

# path to store #reckless entropy
if simulator:
    storage_root = "../userdata"
else:
    storage_root = "/flash/userdata"

USB_ENABLED = False
DEV_ENABLED = False

try:
    s = os.stat("%s/%s" % (storage_root, "USB_ENABLED"))
    USB_ENABLED = True
except:
    pass

try:
    s = os.stat("%s/%s" % (storage_root, "DEV_ENABLED"))
    DEV_ENABLED = True
except:
    pass