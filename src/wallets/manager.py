from platform import maybe_mkdir, delete_recursively
from binascii import hexlify
from bitcoin.networks import NETWORKS

class WalletError(Exception):
    pass

class WalletManager:
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """
    def __init__(self, path):
        self.root_path = path
        maybe_mkdir(path)
        self.path = None

    def init(self, keystore, network='test'):
        """Loads or creates default wallets for new keystore or network"""
        self.keystore = keystore
        path = self.root_path+"/"+hexlify(self.keystore.fingerprint).decode()
        maybe_mkdir(path)
        if network not in NETWORKS:
            raise WalletError("Invalid network")
        self.network = network
        path += "/"+network
        maybe_mkdir(path)

    def wipe(self):
        delete_recursively(self.root_path)