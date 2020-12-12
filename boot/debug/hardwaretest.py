from gui.specter import SpecterGUI
from gui.screens.screen import Screen
import lvgl as lv
import asyncio
from platform import delete_recursively, fpath, mount_sdram
from hosts import QRHost
from keystore.javacard.applets.memorycard import MemoryCardApplet
from keystore.javacard.util import get_connection

class HardwareTest:
    def __init__(self):
        self.rampath = mount_sdram()
        self.gui = SpecterGUI()
        Screen.COLORS["none"] = lv.color_hex(0xeeeeee)
        Screen.network = "none"
        self.qr = None

    def start(self):
        self.gui.start(dark=False)
        asyncio.run(self.main())

    async def main(self):
        buttons = [
            (1, "Wipe the device storage"),
            (2, "Configure QR code scanner"),
            (3, "Scan something"),
            (4, "Test smartcard"),
        ]
        while True:
            res = await self.gui.menu(buttons,
                        title="Factory test",
                        note="This firmware is used to test electrical connections between the discovery board and other components.\nIt can also erase the content of the internal storage\n(factory reset).")
            if res == 1:
                conf = await self.gui.prompt("Wipe the device?",
                        "This will delete everything from internal storage.")
                if conf:
                    await self.wipe()
            elif res == 2:
                if self.qr is None:
                    self.qr = QRHost(self.rampath+"/qr")
                    self.qr.init()
                    self.qr.start(self)
                if self.qr.is_configured:
                    await self.gui.alert("Success!", "QR code scanner is configured")
                else:
                    await self.gui.alert("Fail...", "Something went wrong. Maybe reboot and try again...")
            elif res == 3:
                if self.qr is None:
                    self.qr = QRHost(self.rampath+"/qr")
                    self.qr.init()
                    self.qr.start(self)
                await self.qr.enable()
                s = await self.qr.get_data()
                if s:
                    data = s.read().decode()
                    await self.gui.alert("Here's what we scanned:", data)
            else:
                conn = get_connection()
                if not conn.isCardInserted():
                    await self.gui.alert("Card is not present!",
                        "Smartcard is not inserted")
                else:
                    try:
                        conn.connect(conn.T1_protocol)
                    except:
                        pass
                    try:
                        app = MemoryCardApplet(conn)
                        app.open_secure_channel()
                        print(app.get_pin_status())
                        if app.is_pin_set:
                            await self.gui.alert("Smartcard works!", "Pin is set")
                        else:
                            await self.gui.alert("Smartcard works!", "Pin is not set")
                    except Exception as e:
                        await self.gui.alert("Something went wrong...",
                            "We got an exception: %r" % e)
            await asyncio.sleep_ms(30)

    async def host_exception_handler(self, e):
        pass

    async def wipe(self):
        try:
            delete_recursively(fpath("/flash"))
            delete_recursively(fpath("/qspi"))
            await self.gui.alert("Success!", "All the content is deleted.")
        except Exception as e:
            await self.gui.alert("Fail!", "Something bad happened:\n"+str(e))


if __name__ == '__main__':
    HardwareTest().start()