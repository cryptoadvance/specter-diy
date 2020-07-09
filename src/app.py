"""Base app that Specter can run"""
from errors import BaseError
from platform import maybe_mkdir, delete_recursively

class BaseApp:
    # set text of a button here and a callback if you want to have 
    # a GUI-triggered events - it will create a menu button
    # on the main screen
    button = None
    # prefixes for commands that this app recognizes
    # should be byte sequences, no spaces i.e. b"appcommand"
    prefixes = []
    # button = ("My App menu item", callback name)
    def __init__(self, path:str):
        """path is the folder where this app should store data"""
        maybe_mkdir(path)
        self.path = path

    def init(self, keystore, network:str='test'):
        """
        This method is called when new key is loaded
        or a different network is selected.
        """
        self.keystore = keystore
        self.network = network

    def wipe(self):
        """
        Delete all the contents of the app
        including the app folder itself.
        """
        delete_recursively(self.path, include_self=True)

class AppError(BaseError):
    NAME = "Application error"
