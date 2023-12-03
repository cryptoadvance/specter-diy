from keystore.ram import RAMKeyStore
from app import BaseApp
from apps.wallets import App as WalletsApp
import platform

TEST_DIR = "testdir"

def check_sigs(psbt1, psbt2):
    return [inp.partial_sigs for inp in psbt1.inputs] == [inp.partial_sigs for inp in psbt2.inputs]

def clear_testdir():
    try:
        platform.delete_recursively(TEST_DIR, include_self=True)
    except:
        pass

def show_loader(*args, **kwargs):
    """Dummy show_loader function that does nothing"""
    pass

async def show(*args, **kwargs):
    """Dummy show function that always cancels (returns None)"""
    return None

async def communicate(*args, **kwargs):
    """Dummy cross-app comunicate function that always cancels"""
    return None

def get_keystore(mnemonic="ability "*11+"acid", password=""):
    """Returns a dummy keystore"""
    platform.maybe_mkdir(TEST_DIR)
    platform.maybe_mkdir(TEST_DIR+"/keystore")
    ks = RAMKeyStore()
    ks.path = TEST_DIR+"/keystore"
    ks.show_loader = show_loader
    ks.show = show
    ks.load_secret(ks.path)
    ks.initialized = True
    ks._unlock("1234")
    ks.set_mnemonic(mnemonic, password)
    return ks

def get_wallets_app(keystore, network):
    platform.maybe_mkdir(TEST_DIR)
    platform.maybe_mkdir(TEST_DIR+"/wallets")
    platform.maybe_mkdir(TEST_DIR+"/tmp")
    BaseApp.tempdir = TEST_DIR+"/tmp"
    wapp = WalletsApp(TEST_DIR+"/wallets")
    wapp.init(keystore, network, show_loader, communicate)
    return wapp
