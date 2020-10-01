import lvgl as lv
import asyncio
from ..common import styles, HOR_RES


class Screen(lv.obj):
    network = "test"
    COLORS = {
        "main": lv.color_hex(0xFF9A00),
        "test": lv.color_hex(0x00F100),
        "regtest": lv.color_hex(0x00CAF1),
        "signet": lv.color_hex(0xBD10E0),
    }

    def __init__(self):
        super().__init__()
        self.waiting = True
        self._value = None

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
