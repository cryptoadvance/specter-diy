import sys
import os

simulator = sys.platform != "pyboard"

# to overwrite these settings create a config.py file

if simulator:
    if len(sys.argv) > 1:
        storage_root = sys.argv[1]
    else:
        storage_root = "./fs"
    try:
        os.mkdir(storage_root)
    except:
        pass

else:
    storage_root = ""

# pin that triggers QR code
# if command mode failed
QRSCANNER_TRIGGER = "D2"
