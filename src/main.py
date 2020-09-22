from specter import Specter
from gui.specter import SpecterGUI
from keystore import FlashKeyStore
from hosts import SDHost, QRHost, USBHost
import platform
import sys
from helpers import load_apps

def main(apps=None, network='test', keystore_cls=FlashKeyStore):
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
    keystore = keystore_cls(keystore_path)

    # loading apps
    if apps is None:
        apps = load_apps()

    # make Specter instance
    settings_path = platform.fpath("/flash")
    specter = Specter(gui=gui,
                      keystore=keystore,
                      hosts=hosts,
                      apps=apps,
                      settings_path=settings_path,
                      network=network)
    specter.start()


if __name__ == '__main__':
    main()
