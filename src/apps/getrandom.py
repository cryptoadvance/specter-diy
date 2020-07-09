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
    async def process_host_command(self, prefix, stream, gui, popup):
        """
        If command with one of the prefixes is received
        it will be passed to this method.
        Should return a stream (file, BytesIO etc).
        """
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
        return BytesIO(hexlify(get_random_bytes(num_bytes)))
