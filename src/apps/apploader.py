from app import BaseApp, AppError
from io import BytesIO
from binascii import unhexlify
from bitcoin import ec, compact
import hashlib
# use signmessage instead?
from helpers import tagged_hash
import platform
from gui.screens import Alert, Prompt

class App(BaseApp):
    """Allows to query random bytes from on-board TRNG."""

    prefixes = [b"importapp"]
    # private key is b"1"*32
    pubkey = ec.PublicKey.parse(unhexlify("036930f46dd0b16d866d59d1054aa63298b357499cd1862ef16f3f55f1cafceb82"))

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
        if prefix not in self.prefixes:
            # WTF? It's not our data...
            raise AppError("Prefix is not valid: %s" % prefix.decode())
        num_sigs = compact.read_from(stream)
        assert num_sigs == 1
        sigs = []
        for i in range(num_sigs):
            l = compact.read_from(stream)
            assert l < 74 # 72? 2+(32+2)+(32+3)
            sigs.append(ec.Signature.parse(stream.read(l)))
        l = compact.read_from(stream)
        h = hashlib.sha256()
        c = 0
        while c < l:
            b = stream.read(min(l-c, 100))
            h.update(b)
            c += len(b)
        hsh = h.digest()
        hh = tagged_hash("diyapp", hsh)
        if not self.pubkey.verify(sigs[0], hh):
            raise AppError("Invalid signature")
        # rewind
        stream.seek(-l, 1)
        if not await show_fn(Prompt("Install an app?", "\n\nThe signatures looks ok.")):
            return
        with open(platform.fpath("/flash/libs/extra_apps/mod1.mpy"), "wb") as f:
            c = 0
            while c < l:
                c += f.write(stream.read(min(l-c, 100)))
        if await show_fn(Prompt("Success!", "\n\nApp is verified and loaded!\n\nReboot the device to make it active?")):
            platform.reboot()