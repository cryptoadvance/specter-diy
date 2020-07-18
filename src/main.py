from specter import Specter
from gui.specter import SpecterGUI
from keystore import FlashKeyStore
from hosts import SDHost, QRHost, USBHost
import platform


def load_apps(module='apps', whitelist=None, blacklist=None):
    mod = __import__(module)
    mods = mod.__all__
    apps = []
    if blacklist is not None:
        mods = [mod for mod in mods if mod not in blacklist]
    if whitelist is not None:
        mods = [mod for mod in mods if mod in whitelist]
    for modname in mods:
        appmod = __import__('%s.%s' % (module, modname))
        mod = getattr(appmod, modname)
        if hasattr(mod, 'App'):
            app = mod.App(platform.fpath("/qspi/%s" % modname))
            apps.append(app)
        else:
            print("Failed loading app:", modname)
    return apps


def main(apps=None, network='test'):
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
