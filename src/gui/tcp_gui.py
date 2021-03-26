from .specter import SpecterGUI
import pyb
import json
import asyncio
import sys

class TCPGUI(SpecterGUI):
    """
    Simulated GUI for testing.
    User interaction can be provided over telnet on port 8787
    """
    def __init__(self, *args, **kwargs):
        self.tcp = pyb.UART('"S') # will be on port 8787
        super().__init__(*args, **kwargs)

    def start(self, *args, **kwargs):
        super().start(*args, **kwargs)
        asyncio.create_task(self.tcp_loop())

    async def tcp_loop(self):
        res = b""
        while True:
            await asyncio.sleep_ms(30)
            try:
                # trying to read something
                chunk = self.tcp.read(100)
                # if we didn't get anything - return
                if chunk is None:
                    continue
                res += chunk
                if b"\r" in res or b"\n" in res:
                    arr = res.replace(b"\r",b"\n").split(b"\n")
                    cmd = arr[0].decode()
                    if cmd == "quit":
                        print("QUIT!")
                        sys.exit(1)
                    res = b""
                    val = json.loads("[%s]" % cmd)[0]
                    if self.scr is not None:
                        self.scr.set_value(val)
            except Exception as e:
                print(e)
                res = b""

    async def open_popup(self, scr):
        try:
            self.tcp.write(b"%s\r\n" % type(scr).__name__)
        except:
            pass
        return await super().open_popup(scr)


    async def load_screen(self, scr):
        try:
            self.tcp.write(b"%s\r\n" % type(scr).__name__)
        except:
            pass
        return await super().load_screen(scr)
