# detect if it's a hardware device or linuxport
import sys, os, pyb
simulator = (sys.platform != 'pyboard')

class CriticalErrorWipeImmediately(Exception):
    """
    This exception should be raised when device needs to be wiped
    because something terrible happened
    """
    pass

def maybe_mkdir(path):
    try:
        os.mkdir(path)
    except:
        pass

# path to store #reckless entropy
if simulator:
    storage_root = "../fs"
    # create folders for simulator
    maybe_mkdir(storage_root)
    maybe_mkdir("%s/flash"%storage_root)
    maybe_mkdir("%s/qspi"%storage_root)
    maybe_mkdir("%s/sd"%storage_root)
else:
    storage_root = ""

def mount_sdram():
    path = "%s/ramdisk"%storage_root
    if simulator:
        # not a real RAM on simulator
        maybe_mkdir(path)
        # cleanup
        delete_recursively(path)
    else:
        import sdram
        sdram.init()
        bdev = sdram.RAMDevice(512)
        os.VfsFat.mkfs(bdev)
        os.mount(bdev, path)
    return path

def sync():
    try:
        os.sync()
    except:
        pass

def fpath(fname):
    """A small function to avoid % storage_root everywhere"""
    return "%s%s" % (storage_root, fname)

def file_exists(fname:str)->bool:
    try:
        with open(fname, "rb") as f:
            pass
        return True
    except:
        return False

def delete_recursively(path, include_self=False):
    # remove trailing slash
    path = path.rstrip("/")
    files = os.ilistdir(path)
    for _file in files:
        if _file[0] in [".",".."]:
            continue
        f = "%s/%s" % (path, _file[0])
        # regular file
        if _file[1] == 0x8000:
            os.remove(f)
        # directory
        elif _file[1] == 0x4000:
            delete_recursively(f)
            os.rmdir(f)

    files = os.ilistdir(path)
    num_of_files = sum(1 for _ in files)
    if (num_of_files == 2 and simulator) or num_of_files == 0:
        """
        Directory is empty - it contains exactly 2 directories -
        current directory and parent directory (unix) or
        0 directories (stm32)
        """
        if include_self:
            os.rmdir(path)
        return True
    raise RuntimeError("Failed to delete folder %s" % path)

stlk = pyb.UART('YB',9600)

def set_usb_mode(dev=False, usb=False):
    if simulator:
        print("dev:", dev, ", usb:", usb)
    # first set to None
    pyb.usb_mode(None)
    # now get correct mode
    if usb and not dev:
        pyb.usb_mode("VCP")
    elif usb and dev:
        pyb.usb_mode("VCP+MSC")
        if not simulator:
            # duplicate repl to stlink 
            # as usb is busy for communication
            os.dupterm(stlk,0)
            os.dupterm(None,1)
    elif not usb and dev:
        pyb.usb_mode("VCP+MSC")
        usb = pyb.USB_VCP()
        if not simulator:
            os.dupterm(None,0)
            os.dupterm(usb,1)
