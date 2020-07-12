from io import BytesIO
from .core import Host, HostError
import sys, pyb, asyncio
import platform

class USBHost(Host):
    """
    USBHost class.
    Manages USB communication with the host.
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
            if platform.simulator:
                print("Connect to 127.0.0.1:8789 to do USB communication")

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
        # rewind
        stream.seek(0)
        # res should be a stream as well
        res = await self.manager.process_host_request(stream)
        if res is None:
            self.respond(b'error: User cancelled')
        else:
            stream, meta = res
            # loop until we read everything
            chunk = stream.read(32)
            while len(chunk)>0:
                self.usb.write(chunk)
                chunk = stream.read(32)
            self.respond(b"")

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

