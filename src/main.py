from specter import Specter
from gui.specter import SpecterGUI
from keystore import FlashKeyStore
from hosts import SDHost, QRHost, USBHost
import platform
from apps import __all__ as mods

def main():
    # create virtual file system /sdram
    # for temp untrusted data storage
    rampath = platform.mount_sdram()
    # define hosts - USB, QR, SDCard
    # each hosts gets it's own RAM folder for data
    hosts = [
        QRHost(rampath+"/qr"),
        USBHost(rampath+"/usb"),
        # SDHost(rampath+"/sd"), # not implemented yet
    ]
    # define GUI
    gui = SpecterGUI()

    # folder where keystore will store it's data
    keystore_path = platform.fpath("/flash/keystore")
    # define KeyStore
    keystore = FlashKeyStore(keystore_path)

    # loading apps
    applications = []
    for modname in mods:
        appmod = __import__('apps.%s' % modname)
        mod = getattr(appmod, modname)
        if hasattr(mod, 'App'):
            app = mod.App(platform.fpath("/qspi/%s" % modname))
            applications.append(app)
        else:
            print("Failed loading app:", modname)

    # make Specter instance
    settings_path = platform.fpath("/flash")
    specter = Specter(gui=gui, 
                      keystore=keystore,
                      hosts=hosts,
                      apps=applications,
                      settings_path=settings_path)
    specter.start()

if __name__ == '__main__':
    main()
