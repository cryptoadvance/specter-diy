
class WalletManager:
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """
    def __init__(self, keystore):
        self.keystore = keystore
