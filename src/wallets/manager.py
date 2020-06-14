from platform import maybe_mkdir, delete_recursively
from binascii import hexlify
from bitcoin.networks import NETWORKS
from .wallet import WalletError, Wallet

class WalletManager:
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """
    registered = [
        Wallet,
    ]
    def __init__(self, path):
        self.root_path = path
        maybe_mkdir(path)
        self.path = None
        self.wallets = []

    def init(self, keystore, network='test'):
        """Loads or creates default wallets for new keystore or network"""
        self.keystore = keystore
        # add fingerprint dir
        path = self.root_path+"/"+hexlify(self.keystore.fingerprint).decode()
        maybe_mkdir(path)
        if network not in NETWORKS:
            raise WalletError("Invalid network")
        self.network = network
        # add network dir
        path += "/"+network
        maybe_mkdir(path)
        self.path = path
        self.load_wallets()
        if len(self.wallets) == 0:
            w = self.create_default_wallet(path=self.path+"/0")
            self.wallets.append(w)
            print(w)

    @classmethod
    def register(cls, walletcls):
        """Registers an additional wallet class"""
        cls.registered.append(walletcls)

    def load_wallets(self):
        pass

    def create_default_wallet(self, path):
        der = "m/84h/%dh/0h" % NETWORKS[self.network]["bip32"]
        xpub = self.keystore.get_xpub(der)
        desc = "wpkh([%s%s]%s)" % (
            hexlify(self.keystore.fingerprint).decode(), 
            der[1:],
            xpub.to_base58(NETWORKS[self.network]["xpub"])
        )
        return Wallet.parse(desc, path)

    def wipe(self):
        self.wallets = []
        self.path = None
        delete_recursively(self.root_path)