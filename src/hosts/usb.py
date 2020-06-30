from io import BytesIO
from .core import Host, HostError
import sys
from bitcoin.bip32 import parse_path
from bitcoin import ec, psbt
from binascii import hexlify, unhexlify, b2a_base64, a2b_base64
import pyb, asyncio
import platform

class USBHost(Host):
    """
    USBHost class.
    Manages USB communication with the host:
    - commands can be triggered by the host
      - get xpub
      - get fingerprint
      - sign tx (requires user conf)
      - load seed
      - set label
    """
    ACK = b"ACK\r\n"
    RECOVERY_TIME   = 10

    def __init__(self, path):
        super().__init__(path)
        self.usb = None
        self.data = b""

    def init(self):
        # doesn't work if it was enabled and then disabled
        if self.usb is None:
            self.usb = pyb.USB_VCP()

    async def process_command(self, mv):
        if self.manager == None:
            return
        buf = BytesIO(mv)
        b = buf.read(20)
        # find space
        prefix = b.split(b' ')[0]
        # point to the beginning of the data
        if b' ' in b:
            buf.seek(len(prefix)+1)
        else:
            buf.seek(0)
        # get device fingerprint, data is ignored
        if prefix == b"fingerprint":
            self.respond(hexlify(self.manager.get_fingerprint()))
        # get xpub, 
        # data: derivation path in human-readable form like m/44h/1h/0
        elif prefix == b"xpub":
            try:
                path = buf.read().strip(b" /\r\n")
                # convert to list of indexes
                path = parse_path(path.decode())
            except:
                raise HostError("Invalid path: \"%s\"" % path.decode())
            # get xpub
            xpub = self.manager.get_xpub(path)
            # send back as base58
            self.respond(xpub.to_base58().encode())
        # sign authenticated transaction
        # data: b64_psbt auth0 auth1 ... (space-separated)
        elif prefix == b"signauth":
            # TODO: optimize to reduce memory footprint
            # read b64 psbt and decode
            raw_tx_stream = BytesIO()
            chunk = bytearray(4)
            while True:
                l = buf.readinto(chunk)
                if b' ' in chunk or l < 4:
                    # move back to the beginning
                    buf.seek(-l, 1)
                    break
                raw_tx_stream.write(a2b_base64(chunk))
            raw_tx_stream.seek(0)
            # next should be space
            if buf.read(1) != b' ':
                raise HostError("Missing authorizations")
            # parse authorization signatures: they are in hex
            sigs = []
            while True:
                siglen = buf.read(2)
                # if nothing is read - we are done
                if len(siglen) == 0:
                    break
                elif len(siglen) == 1:
                    raise HostError("Invalid auths len encoding")
                siglen = unhexlify(siglen)[0]
                # if len is zero - empty authorization
                if siglen == 0:
                    continue
                der = unhexlify(buf.read(siglen*2))
                if len(der) < siglen:
                    raise HostError("Invalid authorization len")
                sigs.append(BytesIO(der))
            # ask the manager to sign transaction
            # if tx is not ok - it will raise an error
            tx = await self.manager.sign_transaction(raw_tx_stream, sigs, remote=True)
            if tx is None:
                raise HostError("User cancelled")
            # serialize, convert to base64, send back
            raw_tx_stream = BytesIO(tx.serialize())
            # convert to base64 in chunks
            chunk = bytearray(3)
            while raw_tx_stream.readinto(chunk) > 0:
                self.usb.write(b2a_base64(chunk).strip())
            # add EOL
            self.respond(b'')
            return
        # set device label
        elif prefix == b"set_label":
            label = buf.read().decode()
            self.manager.set_label(label)
            self.respond(label.encode())
            return
        # load mnemonic to the card
        elif prefix == b"load_mnemonic":
            mnemonic = buf.read().decode().strip()
            self.manager.load_mnemonic(mnemonic)
            self.respond(mnemonic)
        else:
            print("USB got:", prefix, buf.read())
            raise HostError("Unknown command: \"%s\"" % prefix.decode())

    def respond(self, data):
        self.usb.write(data)
        self.usb.write("\r\n")

    # TODO: optimize for memory usage:
    #       store in constant buffer or qspi file if data is large
    async def process_data(self):
        arr = self.data.split(b"\r")
        self.data = b""
        for el in arr:
            if el.endswith(b"\n"):
                el = el[:-1]
            if len(el) > 0:
                try:
                    await self.process_command(memoryview(el))
                except Exception as e:
                    self.respond(b"error: %s" % e)
                    sys.print_exception(e)

    async def update(self):
        if self.manager == None:
            return await asyncio.sleep_ms(100)
        if self.usb is None:
            return await asyncio.sleep_ms(100)
        if not platform.usb_connected():
            return await asyncio.sleep_ms(100)
        res = self.usb.read()
        if res is not None and len(res) > 0:
            self.data += res
            # wait a bit
            await asyncio.sleep_ms(10)
            # ack, any packet should be 64 bytes long
            self.usb.write(self.ACK)
            print(res)
        # wait a bit
        await asyncio.sleep_ms(10)

