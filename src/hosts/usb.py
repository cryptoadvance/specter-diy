from io import BytesIO
from .core import Host, HostError
import sys
from bitcoin.bip32 import parse_path
from bitcoin import ec, psbt
from binascii import hexlify, unhexlify, b2a_base64, a2b_base64
import pyb, asyncio
import platform
from rng import get_random_bytes

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
        self.f = None

    def init(self):
        # doesn't work if it was enabled and then disabled
        if self.usb is None:
            self.usb = pyb.USB_VCP()
            self.usb.init(flow=(pyb.USB_VCP.RTS | pyb.USB_VCP.CTS))

    async def enable(self):
        # cleanup first
        self.cleanup()
        if self.usb is not None:
            self.usb.read()
        return await super().enable()

    def cleanup(self):
        if self.f is not None:
            self.f.close()
            self.f = None
        platform.delete_recursively(self.path)

    async def process_command(self, stream):
        if self.manager == None:
            raise HostError("Device is busy")
        # all commands are pretty short
        b = stream.read(20)
        # if empty command - return \r\n back
        if len(b) == 0:
            return self.respond(b"")
        # find space
        prefix = b.split(b' ')[0]
        # point to the beginning of the data
        if b' ' in b:
            stream.seek(len(prefix)+1)
        else:
            stream.seek(0)
        # get device fingerprint, data is ignored
        if prefix == b"fingerprint":
            self.respond(hexlify(self.manager.get_fingerprint()))
        # get xpub, 
        # data: derivation path in human-readable form like m/44h/1h/0
        elif prefix == b"xpub":
            try:
                path = stream.read().strip()
                # convert to list of indexes
                path = parse_path(path.decode())
            except:
                raise HostError("Invalid path: \"%s\"" % path.decode())
            # get xpub
            xpub = self.manager.get_xpub(path)
            # send back as base58
            self.respond(xpub.to_base58().encode())
        # sign authenticated transaction
        # data: b64_psbt
        elif prefix == b"sign":
            await self.sign_psbt(stream)
        # set device label
        elif prefix == b"set_label":
            label = stream.read().decode()
            self.manager.set_label(label)
            self.respond(label.encode())
        # load mnemonic to the card
        elif prefix == b"load_mnemonic":
            mnemonic = stream.read().decode().strip()
            self.manager.load_mnemonic(mnemonic)
            self.respond(mnemonic)
        elif prefix == b"showaddr":
            arr = stream.read().split(b' ')
            redeem_script = None
            if len(arr) == 2:
                script_type, path = arr
            elif len(arr) == 3:
                script_type, path, redeem_script = arr
            else:
                raise HostError("Too many arguments")
            paths = path.split(b",")
            if len(paths) == 0:
                raise HostError("Invalid path argument")
            res = await self.manager.showaddr(paths, script_type, redeem_script)
            self.respond(res)
        # get 32 bytes of randomness in hex
        elif prefix == b"getrandom":
            num_bytes = 32
            try:
                num_bytes = int(stream.read().decode().strip())
            except:
                pass
            if num_bytes < 0:
                raise HostError("Seriously? %d bytes? No..." % num_bytes)
            if num_bytes > 10000:
                raise HostError("Sorry, 10k bytes max.")
            while num_bytes > 32:
                self.usb.write(hexlify(get_random_bytes(32)))
                num_bytes -= 32
            self.respond(hexlify(get_random_bytes(num_bytes)).decode())
        else:
            print("USB got:", prefix, stream.read())
            raise HostError("Unknown command: \"%s\"" % prefix.decode())

    async def sign_psbt(self, stream):
        # decode to file
        with open(self.path+"/psbt", "wb") as f:
            chunk = bytearray(4)
            l = stream.readinto(chunk)
            while l > 0:
                f.write(a2b_base64(chunk[:l]))
                l = stream.readinto(chunk)
        # reopen to read
        with open(self.path+"/psbt", "rb") as f:
            # ask the manager to sign transaction
            # if tx is not ok - it will raise an error
            psbt = await self.manager.sign_psbt(f, remote=True)
            if psbt is None:
                self.respond(b'error: User cancelled')
        # serialize, convert to base64, send back
        raw_tx_stream = BytesIO(psbt.serialize())
        # convert to base64 in chunks
        chunk = bytearray(3)
        l = raw_tx_stream.readinto(chunk)
        while l > 0:
            self.usb.write(b2a_base64(chunk[:l]).strip())
            l = raw_tx_stream.readinto(chunk)
        # add EOL
        self.respond(b'')

    def respond(self, data):
        self.usb.write(data)
        self.usb.write("\r\n")

    def read_to_file(self):
        """
        Keeps reading from usb to ramdisk until EOL found.
        Returns None if line is not complete,
        filename with data if line is read
        """
        # trying to read something
        res = self.usb.read(64)
        # if we didn't get anything - return
        if res is None or len(res) == 0:
            return
        # check if we already have something
        # if not - create new file on the ramdisk
        if self.f is None:
            self.f = open(self.path+"/data", "wb")
        # check if we dont have EOL in the data
        if b"\n" not in res and b"\r" not in res:
            self.f.write(res)
            return
        # if we do - there is a command
        # both \r, \n or \r\n should work:
        for eol in [b"\r\n", b"\r", b"\n"]:
            # check if we have two EOL at once
            # this means the host wants to start over
            # like \n\n or \r\n\r\n or \r\r
            if eol*2 in res:
                arr = res.split(eol*2)
                # cleanup and start over
                self.cleanup()
                self.f = open(self.path+"/data", "wb")
                # this is the part we care about
                res = arr[-1]
                # if command is not complete yet
                # we write and return
                if eol not in res:
                    self.f.write(res)
                    return
            if eol in res:
                arr = res.split(eol)
                break
        # only one command at a time is allowed,
        # throw everything else away
        self.f.write(arr[0])
        # close file
        self.f.close()
        self.f = None
        return self.path+"/data"

    async def update(self):
        if self.manager == None:
            return await asyncio.sleep_ms(100)
        if self.usb is None:
            return await asyncio.sleep_ms(100)
        if not platform.usb_connected():
            return await asyncio.sleep_ms(100)
        res = self.read_to_file()
        # if we got a filename - line is ready
        if res is not None:
            # first send the host that we are processing data
            self.usb.write(self.ACK)
            # open again for reading and try to process content
            try:
                with open(self.path+"/data", "rb") as f:
                    await self.process_command(f)
            # if we fail with host error - tell the host why we failed
            except HostError as e:
                self.respond(b"error: %s" % e)
                sys.print_exception(e)
            # for all other exceptions - send back generic message
            except Exception as e:
                self.respond(b"error: Unknown error")
                sys.print_exception(e)
            self.cleanup()

        # wait a bit
        await asyncio.sleep_ms(10)

