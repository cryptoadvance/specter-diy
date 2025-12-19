"""A keyboard with a hint when you press it"""
import lvgl as lv
from ..decorators import feed_touch
from .theme import styles


class HintKeyboard(lv.buttonmatrix):
    def __init__(self, scr, *args, **kwargs):
        super().__init__(scr, *args, **kwargs)
        self.hint = lv.button(scr)
        self.hint.set_size(50, 60)
        self.hint_lbl = lv.label(self.hint)
        self.hint_lbl.set_text(" ")
        self.hint_lbl.add_style(styles["title"], 0)
        self.hint_lbl.set_size(50, 60)
        self.hint.add_flag(lv.obj.FLAG.HIDDEN)
        self.callback = None
        super().add_event_cb(self.cb, lv.EVENT.ALL, None)

    def set_event_cb(self, callback):
        self.callback = callback

    def get_event_cb(self):
        return self.callback

    def cb(self, event):
        code = event.get_code()
        obj = event.get_target()
        if code == lv.EVENT.PRESSING:
            feed_touch()
            c = obj.get_selected_button_text()
            if c is not None and len(c) <= 2:
                self.hint.clear_flag(lv.obj.FLAG.HIDDEN)
                self.hint_lbl.set_text(c)
                indev = lv.indev_active()
                point = indev.get_point()
                self.hint.set_pos(point.x - 25, point.y - 130)

        elif code == lv.EVENT.RELEASED:
            self.hint.add_flag(lv.obj.FLAG.HIDDEN)

        if self.callback is not None:
            self.callback(obj, code)
