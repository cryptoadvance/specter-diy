from platform import maybe_mkdir, delete_recursively
from binascii import hexlify
from bitcoin.networks import NETWORKS
from .wallet import WalletError, Wallet
import os

class WalletManager:
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """
    WALLETS = [
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
        self.wallets = self.load_wallets()
        if len(self.wallets) == 0:
            w = self.create_default_wallet(path=self.path+"/0")
            self.wallets.append(w)

    @classmethod
    def register(cls, walletcls):
        """Registers an additional wallet class"""
        # check if it's already there
        if walletcls in cls.WALLETS:
            return
        cls.WALLETS.append(walletcls)

    def load_wallets(self):
        """Loads all wallets from path"""
        # get ids of the wallets - every wallet is stored in a numeric folder
        wallet_ids = sorted([int(f[0]) for f in os.ilistdir(self.path) \
                    if f[0].isdigit() and f[1] == 0x4000])
        return [self.load_wallet(self.path+("/%d" % wid)) for wid in wallet_ids]

    def load_wallet(self, path):
        """Loads a wallet with particular id"""
        w = None
        # going through all wallet classes and trying to load
        # first we verify descriptor sig in the folder
        for walletcls in self.WALLETS:
            try:
                # pass path and key for verification
                pub = self.keystore.idkey.get_public_key()
                w = walletcls.from_path(path, pub)
            except Exception as e:
                pass
        # if we failed to load -> delete folder and throw an error
        if w is None:
            delete_recursively(path, include_self=True)
            raise WalletError("Can't load wallet from %s" % path)
        return w

    def create_default_wallet(self, path):
        """Creates default p2wpkh wallet with name `Default`"""
        der = "m/84h/%dh/0h" % NETWORKS[self.network]["bip32"]
        xpub = self.keystore.get_xpub(der)
        desc = "Default&wpkh([%s%s]%s)" % (
            hexlify(self.keystore.fingerprint).decode(), 
            der[1:],
            xpub.to_base58(NETWORKS[self.network]["xpub"])
        )
        w = Wallet.parse(desc, path)
        # pass idkey to sign data
        w.save(self.keystore.idkey)

    def wipe(self):
        """Deletes all wallets info"""
        self.wallets = []
        self.path = None
        delete_recursively(self.root_path)