from specter import Specter
from gui.specter import SpecterGUI

from keystore.core import KeyStore
from keystore.sdcard import SDKeyStore
from keystore.memorycard import MemoryCard

from hosts import SDHost, QRHost, USBHost, Host
import platform
import sys
from helpers import load_apps
from app import BaseApp
import display

def main(apps=None, network="main", keystore_cls=None):
    """
    apps: list of apps to load
    network: default network to operate
    keystores: list of KeyStore classes that can be used
    """
    # Init display first as it also inits the SDRAM
    display.init(False)
    # create virtual file system /sdram
    # for temp untrusted data storage
    rampath = platform.mount_sdram()
    # define hosts - USB, QR, SDCard
    # each hosts gets it's own RAM folder for data
    Host.SETTINGS_DIR = platform.fpath("/qspi/hosts")
    Specter.SETTINGS_DIR = platform.fpath("/qspi/specter")
    hosts = [
        USBHost(rampath + "/usb"),
        QRHost(rampath + "/qr"),
        SDHost(rampath+"/sd"),
    ]
    # temp storage in RAM for host commands processing
    BaseApp.TEMPDIR = rampath+"/tmp"

    # define GUI
    if not platform.simulator:
        gui = SpecterGUI()
    else:
        # this GUI can simulate user actions for automated testing
        from gui.tcp_gui import TCPGUI
        gui = TCPGUI()

    # inject the folder where keystore stores it's data
    KeyStore.path = platform.fpath("/flash/keystore")
    # detect keystore to use
    if keystore_cls is not None:
        keystores = [keystore_cls]
    else:
        keystores = [
            MemoryCard,
            SDKeyStore,
        ]

    # loading apps
    if apps is None:
        apps = load_apps()

    # make Specter instance
    settings_path = platform.fpath("/flash")
    specter = Specter(
        gui=gui,
        keystores=keystores,
        hosts=hosts,
        apps=apps,
        settings_path=settings_path,
        network=network,
    )
    specter.start()


if __name__ == "__main__":
    main()
