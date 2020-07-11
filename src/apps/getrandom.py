"""
Demo of a single-file app extending Specter functionality.
This app allows to query random bytes from on-board TRNG.
"""
from app import BaseApp, AppError
from io import BytesIO
from binascii import hexlify
from rng import get_random_bytes

# Should be called App if you use a single file
class App(BaseApp):
    """Allows to query random bytes from on-board TRNG."""
    prefixes = [b"getrandom"]
    async def process_host_command(self, stream, show_fn):
        """
        If command with one of the prefixes is received
        it will be passed to this method.
        Should return a tuple: 
        - stream (file, BytesIO etc) 
        - meta object with title and note
        """
        # reads prefix from the stream (until first space)
        prefix = self.get_prefix(stream)
        if prefix != b"getrandom":
            # WTF? It's not our data...
            raise AppError("Prefix is not valid: %s" % prefix.decode())
        # by default we return 32 bytes
        num_bytes = 32
        try:
            num_bytes = int(stream.read().decode().strip())
        except:
            pass
        if num_bytes < 0:
            raise AppError("Seriously? %d bytes? No..." % num_bytes)
        if num_bytes > 1000:
            raise AppError("Sorry, 1k bytes max.")
        obj = {
            "title": "Here is your entropy",
            "note": "%d bytes" % num_bytes
        }
        return BytesIO(hexlify(get_random_bytes(num_bytes))), obj
