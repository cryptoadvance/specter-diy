"""A keyboard with a hint when you press it"""
import lvgl as lv
from ..decorators import feed_touch
from .theme import styles


class HintKeyboard(lv.btnm):
    def __init__(self, scr, *args, **kwargs):
        super().__init__(scr, *args, **kwargs)
        self.hint = lv.btn(scr)
        self.hint.set_size(50, 60)
        self.hint_lbl = lv.label(self.hint)
        self.hint_lbl.set_text(" ")
        self.hint_lbl.set_style(0, styles["title"])
        self.hint_lbl.set_size(50, 60)
        self.hint.set_hidden(True)
        self.callback = None
        super().set_event_cb(self.cb)

    def set_event_cb(self, callback):
        self.callback = callback

    def get_event_cb(self):
        return self.callback

    def cb(self, obj, event):
        if event == lv.EVENT.PRESSING:
            feed_touch()
            c = obj.get_active_btn_text()
            if c is not None and len(c) <= 2:
                self.hint.set_hidden(False)
                self.hint_lbl.set_text(c)
                point = lv.point_t()
                indev = lv.indev_get_act()
                lv.indev_get_point(indev, point)
                self.hint.set_pos(point.x - 25, point.y - 130)

        elif event == lv.EVENT.RELEASED:
            self.hint.set_hidden(True)

        if self.callback is not None:
            self.callback(obj, event)
