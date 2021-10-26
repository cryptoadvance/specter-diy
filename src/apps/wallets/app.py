from app import BaseApp
import platform
from .manager import WalletManager
from .liquid.manager import LWalletManager
from helpers import is_liquid
import gc

class WalletsApp(BaseApp):
    # This is a dummy app that can switch between Bitcoin and Liquid wallet managers

    def __init__(self, path):
        self.root_path = path
        platform.maybe_mkdir(path)
        self.path = None
        self.manager = None

    @property
    def button(self):
        return self.manager.button if self.manager else None

    @property
    def prefixes(self):
        return self.manager.prefixes if self.manager else None

    @property
    def name(self):
        return self.manager.name if self.manager else None

    def init(self, keystore, network, *args, **kwargs):
        """Loads or creates default wallets for new keystore or network"""
        old_network = self.network if hasattr(self, "network") else None
        super().init(keystore, network, *args, **kwargs)
        # switching the network - use different wallet managers for liquid or btc
        if old_network is None or self.manager is None or is_liquid(old_network) != is_liquid(network):
            if is_liquid(network):
                self.manager = LWalletManager(self.root_path)
            else:
                self.manager = WalletManager(self.root_path)
        return self.manager.init(keystore, network, *args, **kwargs)

    async def menu(self, *args, **kwargs):
        return await self.manager.menu(*args, **kwargs)

    def can_process(self, *args, **kwargs):
        return self.manager.can_process(*args, **kwargs)
        
    async def process_host_command(self, *args, **kwargs):
        return await self.manager.process_host_command(*args, **kwargs)

    def wipe(self):
        return self.manager.wipe()
