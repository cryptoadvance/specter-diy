import lvgl as lv
from .theme import styles

class Battery(lv.obj):
    VALUE = None
    CHARGING = None
    LEVELS = [
        (95, lv.SYMBOL.BATTERY_FULL,  "00D100"),
        (75, lv.SYMBOL.BATTERY_3,     "00D100"),
        (50, lv.SYMBOL.BATTERY_2,     "FF9A00"),
        (25, lv.SYMBOL.BATTERY_1,     "F10000"),
        (0,  lv.SYMBOL.BATTERY_EMPTY, "F10000"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make background transparent in LVGL 9.x
        self.set_style_bg_opa(0, 0)
        self.set_style_border_width(0, 0)
        self.set_style_pad_all(0, 0)
        self.level = lv.label(self)
        self.level.set_recolor(True)
        self.icon = lv.label(self)
        self.charge = lv.label(self)
        self.set_size(30, 20)
        # self.bar = lv.bar(self)
        self.update()

    def update(self):
        if self.VALUE is None:
            self.icon.set_text("")
            self.level.set_text("")
            self.charge.set_text("")
            return
        for v, icon, color in self.LEVELS:
            if self.VALUE >= v:
                if self.CHARGING:
                    self.level.set_text("#00D100 "+icon+" #")
                else:
                    self.level.set_text("#"+color+" "+icon+" #")
                break
        self.icon.set_text(lv.SYMBOL.BATTERY_EMPTY)
        if self.CHARGING:
            self.charge.set_text(lv.SYMBOL.CHARGE)
            self.charge.align_to(self.icon, lv.ALIGN.CENTER, 0, 0)
        else:
            self.charge.set_text("")
