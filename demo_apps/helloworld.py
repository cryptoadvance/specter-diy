"""
Demo of a single-file app extending Specter functionality.
This app returns hello to the host
"""
from app import BaseApp, AppError
from io import BytesIO
from binascii import hexlify
from gui.screens import Prompt
# Should be called App if you use a single file


class App(BaseApp):
    """Allows to query random bytes from on-board TRNG."""
    prefixes = [b"hello"]

    async def process_host_command(self, stream, show_screen):
        """
        If command with one of the prefixes is received
        it will be passed to this method.
        Should return a tuple: 
        - stream (file, BytesIO etc) 
        - meta object with title and note
        """
        # reads prefix from the stream (until first space)
        prefix = self.get_prefix(stream)
        if prefix != b"hello":
            # WTF? It's not our data...
            raise AppError("Prefix is not valid: %s" % prefix.decode())
        name = stream.read().decode()
        # ask the user if he really wants it
        # build a screen
        scr = Prompt("Say hello?", 
                     "Are you sure you want to say hello to\n\n%s?\n\n"
                     "Saying hello can compromise your security!"
                     % name)
        # show screen and wait for result
        res = await show_screen(scr)
        # check if he confirmed
        if not res:
            return
        obj = {
            "title": "Hello!",
        }
        d = b"Hello " + name.encode()
        return BytesIO(d), obj
