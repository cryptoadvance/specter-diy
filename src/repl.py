
if __name__ == '__main__':
    import platform

    # uncomment these lines if you want to use another folder for user data
    # platform.storage_root = platform.storage_root.replace("userdata", "testdata")

    # uncomment these lines to disable usb communication with the wallet and use it for REPL
    # platform.USB_ENABLED = False
    # usb = pyb.USB_VCP()
    # os.dupterm(usb, 1)

    import main as specter

    specter.main(blocking=False)