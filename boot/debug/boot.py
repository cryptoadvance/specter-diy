# boot.py -- run on boot-up
# can run arbitrary Python, but best to keep it minimal
import pyb, os

# power hold
pwr = pyb.Pin("B15", pyb.Pin.OUT)
pwr.on()

# poweroff on button press
pwrcb = lambda e: pwr.off()
pyb.ExtInt(pyb.Pin('B1'), pyb.ExtInt.IRQ_FALLING, pyb.Pin.PULL_NONE, pwrcb)

# configure usb from start if you want, 
# otherwise will be configured after PIN
# pyb.usb_mode("VCP+MSC") # debug mode without USB from start
# disable at start
# pyb.usb_mode(None)
# os.dupterm(None,0)
# os.dupterm(None,1)

# last 512 kB are used for secrets
FLASH_SIZE = 512*1024
# check and mount internal flash
if os.statvfs('/flash')==os.statvfs('/qspi'):
    os.umount('/flash')
    f = pyb.Flash()
    numblocks = f.ioctl(4,None)
    blocksize = f.ioctl(5,None) # 512
    size = numblocks*blocksize
    # we use last 512 kB
    start = numblocks*blocksize-FLASH_SIZE
    if start < 0:
        start = 0
    # try to mount
    try:
        os.mount(pyb.Flash(start=start), '/flash')
    # if fail - format and mount
    except:
        os.VfsFat.mkfs(pyb.Flash(start=start))
        os.mount(pyb.Flash(start=start), '/flash')

# uncomment to run some custom main:
# pyb.main("debug.py")