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

    def __init__(self, path: str):
        """path is the folder where this app should store data"""
        maybe_mkdir(path)
        self.path = path

    def can_process(self, stream):
        """Checks if the app can process this stream"""
        prefix = self.get_prefix(stream)
        return prefix in self.prefixes

    def get_prefix(self, stream):
        """Gets prefix from the stream (first "word")"""
        prefix = stream.read(20)
        if b" " not in prefix:
            if len(prefix) < 20:
                return prefix
            stream.seek(0)
            return None
        prefix = prefix.split(b" ")[0]
        # point to the beginning of the data
        stream.seek(len(prefix) + 1)
        return prefix

    def init(self, keystore, network, show_loader):
        """
        This method is called when new key is loaded
        or a different network is selected.
        """
        self.keystore = keystore
        self.network = network
        self.show_loader = show_loader

    def wipe(self):
        """
        Delete all the contents of the app
        including the app folder itself.
        """
        delete_recursively(self.path, include_self=True)


class AppError(BaseError):
    NAME = "Application error"
