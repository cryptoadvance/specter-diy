from .core import Host, HostError
from platform import fpath
from binascii import unhexlify, a2b_base64, b2a_base64
import os
from io import BytesIO

class SDHost(Host):
    """
    SDHost class.
    Manages communication with SD card:
    - loading unsigned transaction and authentications
    - saving signed transaction to the card
    """
    def __init__(self, path=fpath("/sd")):
        super().__init__()
        self.path = path
        self.button = "Load from SD card"
        self.tx_fname = "vault.psbt.unsigned"
        self.auth_prefix = "authorization."

    async def get_data(self):
        """
        Loads psbt transaction and tx authentications
        from the SD card.
        Returns a tuple: 
        - byte stream with psbt transaction in binary form and 
        - list of authentications, also in binary streams
        Files on the SD card should be: 
        - base64 encoded psbt in vault.psbt.unsigned file
        - hex-encoded ECDSA der-encoded signatures in authorization.N
          where N is any number
        """
        # checking size of transaction
        try:
            size = os.stat("%s/%s" % (self.path, self.tx_fname))[6]
        except:
            raise HostError("Failed to find\n%s\nfile on the SD card" % self.tx_fname)

        # loading transaction and decoding in pieces
        # - saves memory for large txs
        raw_tx = BytesIO()
        with open("%s/%s" % (self.path, self.tx_fname), "rb") as f:
            for i in range(size//4):
                b64chunk = f.read(4).strip() # remove "\n etc"
                try:
                    raw_tx.write(a2b_base64(b64chunk))
                except:
                    raise HostError("Invalid base64-encoded transaction size!")
        # reset pointer
        raw_tx.seek(0)

        # loading authorizations
        sigs = []
        for file, *_ in os.ilistdir(self.path):
            if file.startswith(self.auth_prefix):
                with open("%s/%s" % (self.path, file), "rb") as f:
                    sigs.append(BytesIO(unhexlify(f.read())))
        return raw_tx, sigs

    async def send_data(self, tx, suffix=""):
        """
        Saves transaction in base64 encoding to SD card
        as vault.psbt.signed.<suffix> file
        Returns a success message to display
        """
        with open("%s/vault.psbt.signed.%s" % (self.path, suffix), "wb") as f:
            raw = BytesIO(tx.serialize())
            while True:
                chunk = raw.read(3)
                f.write(b2a_base64(chunk).strip())
                if len(chunk) < 3:
                    break
        # TODO: refactor using self.manager
        return "Transaction was saved to\n\nvault.psbt.signed.%s\n\nfile" % suffix
