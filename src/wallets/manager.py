import platform
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
        platform.maybe_mkdir(path)
        self.path = None
        self.wallets = []

    def init(self, keystore, network='test'):
        """Loads or creates default wallets for new keystore or network"""
        self.keystore = keystore
        # add fingerprint dir
        path = self.root_path+"/"+hexlify(self.keystore.fingerprint).decode()
        platform.maybe_mkdir(path)
        if network not in NETWORKS:
            raise WalletError("Invalid network")
        self.network = network
        # add network dir
        path += "/"+network
        platform.maybe_mkdir(path)
        self.path = path
        self.wallets = self.load_wallets()
        if self.wallets is None or len(self.wallets) == 0:
            w = self.create_default_wallet(path=self.path+"/0")
            self.wallets = [w]

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
                w = walletcls.from_path(path, self.keystore)
                # if fails - we continue, otherwise - we are done
                break
            except Exception as e:
                pass
        # if we failed to load -> delete folder and throw an error
        if w is None:
            platform.delete_recursively(path, include_self=True)
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
        # pass keystore to encrypt data
        w.save(self.keystore)
        platform.sync()
        return w

    def parse_wallet(self, desc):
        w = None
        # trying to find a correct wallet type
        for walletcls in self.WALLETS:
            try:
                w = walletcls.parse(desc)
                # if fails - we continue, otherwise - we are done
                break
            except Exception as e:
                pass
        if w is None:
            raise WalletError("Can't detect matching wallet type")
        if w.descriptor() in [ww.descriptor() for ww in self.wallets]:
            raise WalletError("Wallet with this descriptor already exists")
        return w

    def add_wallet(self, w):
        self.wallets.append(w)
        wallet_ids = sorted([int(f[0]) for f in os.ilistdir(self.path) \
                    if f[0].isdigit() and f[1] == 0x4000])
        newpath = self.path+("/%d" % (max(wallet_ids)+1))
        platform.maybe_mkdir(newpath)
        w.save(self.keystore, path=newpath)

    def delete_wallet(self, w):
        if w not in self.wallets:
            raise WalletError("Wallet not found")
        self.wallets.pop(self.wallets.index(w))
        w.wipe()

    def find_wallet_from_address(self, addr:str, idx:int, change=False):
        for w in self.wallets:
            a, gap = w.get_address(idx, self.network, change)
            if a == addr:
                return w
        raise WalletError("Can't find wallet owning address %s" % addr)

    def parse_psbt(self, psbt):
        """Detects a wallet for transaction and returns an object to display"""
        wallet = None
        # detect wallet for first input
        inp = psbt.inputs[0]
        for w in self.wallets:
            if w.owns(inp):
                wallet = w
        if wallet is None:
            raise WalletError("Wallet for this transaction is not found.\nWrong network?")
        # check that all other inputs that they belong
        # to the same wallet
        for inp in psbt.inputs[1:]:
            if not wallet.owns(inp):
                raise WalletError("Mixed inputs are not allowed")
        fee = sum([inp.witness_utxo.value for inp in psbt.inputs])
        fee -= sum([out.value for out in psbt.tx.vout])
        meta = {
            "outputs": [{
                "address": out.script_pubkey.address(NETWORKS[self.network]),
                "value": out.value,
                "change": False,
            } for out in psbt.tx.vout],
            "fee": fee,
            "warnings": [],
        }
        # check change outputs
        for i, out in enumerate(psbt.outputs):
            if wallet.owns(psbt_out=out, tx_out=psbt.tx.vout[i]):
                meta["outputs"][i]["change"] = True
        # check gap limits
        # ugly copy
        gaps = []+wallet.gaps
        # update gaps according to all inputs
        # because if input and output use the same branch (recv / change)
        # it's ok if both are larger than gap limit
        # but differ by less than gap limit
        # (i.e. old wallet is used)
        for inp in psbt.inputs:
            change, idx = wallet.get_derivation(inp)
            if gaps[change] < idx+type(wallet).GAP_LIMIT:
                gaps[change] = idx+type(wallet).GAP_LIMIT
        # check all outputs if index is ok
        for i, out in enumerate(psbt.outputs):
            if not meta["outputs"][i]["change"]:
                continue
            change, idx = wallet.get_derivation(out)
            # add warning if idx beyond gap
            if idx > gaps[change]:
                meta["warnings"].append("Change index %d is beyond the gap limit!" % idx)
                # one warning of this type is enough
                break
        return wallet, meta

    def wipe(self):
        """Deletes all wallets info"""
        self.wallets = []
        self.path = None
        platform.delete_recursively(self.root_path)