from app import BaseApp
import platform
from .manager import WalletManager

class WalletsApp(BaseApp):
    # This is a dummy app that can switch between Bitcoin and Liquid wallet managers
    ManagerApp = WalletManager

    # button = "Wallets"
    # prefixes = [b"addwallet", b"sign", b"showaddr", b"listwallets"]
    # name = "wallets"

    def __init__(self, path):
        self.root_path = path
        platform.maybe_mkdir(path)
        self.path = None
        self.manager = self.ManagerApp(self.root_path)
        # self.button = self.manager.button
        # self.prefixes = self.manager.prefixes
        # self.name = self.manager.name

    @property
    def button(self):
        return self.manager.button

    @property
    def prefixes(self):
        return self.manager.prefixes

    @property
    def name(self):
        return self.manager.name

    def init(self, keystore, network, *args, **kwargs):
        """Loads or creates default wallets for new keystore or network"""
        super().init(keystore, network, *args, **kwargs)
        return self.manager.init(keystore, network, *args, **kwargs)

    async def menu(self, *args, **kwargs):
        return await self.manager.menu(*args, **kwargs)

    def can_process(self, *args, **kwargs):
        return self.manager.can_process(*args, **kwargs)
        
    async def process_host_command(self, *args, **kwargs):
        return await self.manager.process_host_command(*args, **kwargs)

    def wipe(self):
        return self.manager.wipe()
