# detect if it's a hardware device or linuxport
try:
    import pyb
    simulator = False
except:
    simulator = True

# path to store #reckless entropy
if simulator:
    storage_root = "../userdata"
else:
    storage_root = "/flash/userdata"
