import lvgl as lv
import asyncio
from ..common import styles, HOR_RES
from ..core import update
from ..components.modal import Modal
from ..components.battery import Battery

class Screen(lv.obj):
    network = "main"
    COLORS = {
        "main": lv.color_hex(0xFF9A00),
        "test": lv.color_hex(0x00F100),
        "regtest": lv.color_hex(0x00CAF1),
        "signet": lv.color_hex(0xBD10E0),
        "liquidv1": lv.color_hex(0x46B4A5),
        "elementsregtest": lv.color_hex(0x00CAF1),
    }
    mbox = None
    def __init__(self):
        super().__init__()
        self.waiting = True
        self._value = None
        self.battery = Battery(self)
        self.battery.align(self, lv.ALIGN.IN_TOP_RIGHT, -20, 10)

        if type(self).network in type(self).COLORS:
            self.topbar = lv.obj(self)
            s = lv.style_t()
            lv.style_copy(s, styles["theme"].style.btn.rel)
            s.body.main_color = type(self).COLORS[type(self).network]
            s.body.grad_color = type(self).COLORS[type(self).network]
            s.body.opa = 200
            s.body.radius = 0
            s.body.border.width = 0
            self.topbar.set_style(s)
            self.topbar.set_size(HOR_RES, 5)
            self.topbar.set_pos(0, 0)

    def release(self):
        self.waiting = False

    def get_value(self):
        """
        Redefine this function to get value entered by the user
        """
        return self._value

    def set_value(self, value):
        self._value = value
        self.release()

    async def result(self):
        self.waiting = True
        while self.waiting:
            await asyncio.sleep_ms(10)
        return self.get_value()

    def show_loader(self,
                    text="Please wait until the process is complete.",
                    title="Processing..."):
        if self.mbox is None:
            self.mbox = Modal(self)
        self.mbox.set_text("\n\n"+title+"\n\n"+text+"\n\n")
        # trigger update of the screen
        update()
        update()

    def hide_loader(self):
        if self.mbox is None:
            return
        self.mbox.del_async()
        self.mbox = None
        update()
