from specter import Specter
from gui.specter import SpecterGUI
from keystore import FlashKeyStore
from hosts import SDHost, QRHost, USBHost
from wallets import WalletManager
import platform

def main():
    # define hosts - USB, QR, SDCard
    hosts = [
        QRHost(),
        SDHost(),
    ]
    if platform.USB_ENABLED:
        hosts.append(USBHost())
    # define GUI
    gui = SpecterGUI()

    # folder where keystore will store it's data
    keystore_path = platform.fpath("/flash/keystore")
    # define KeyStore
    keystore = FlashKeyStore(keystore_path)
    # define WalletManager, requires keystore
    # to authenticate wallet files
    wallets_path = platform.fpath("/qspi/wallets")
    wallet_manager = WalletManager(wallets_path)

    # make Specter instance
    settings_path = platform.fpath("/flash")
    specter = Specter(gui=gui, 
                      wallet_manager=wallet_manager,
                      keystore=keystore,
                      hosts=hosts,
                      settings_path=settings_path)
    specter.start()

if __name__ == '__main__':
    main()