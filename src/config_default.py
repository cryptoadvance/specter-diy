import sys
import os

# Precisa concordar com platform.py. A forma antiga, sys.platform != "pyboard",
# classificava qualquer alvo novo como simulador -- no ESP32 isso fazia o
# config tentar criar "./fs" numa placa.
simulator = sys.platform in ("linux", "darwin")

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
