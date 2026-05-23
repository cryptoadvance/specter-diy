"""A keyboard with a hint when you press it"""
import lvgl as lv
from ..decorators import feed_touch
from .theme import styles


class ButtonMatrix(lv.buttonmatrix):
    class CTRL:
        TGL_ENABLE = lv.buttonmatrix.CTRL.CHECKABLE
        TGL_STATE = lv.buttonmatrix.CTRL.CHECKED
        INACTIVE = lv.buttonmatrix.CTRL.DISABLED

    def __init__(self, scr, *args, **kwargs):
        super().__init__(scr, *args, **kwargs)
        self.callback = None
        super().add_event_cb(self._event_cb, lv.EVENT.ALL, None)

    def set_event_cb(self, callback):
        self.callback = callback

    def get_event_cb(self):
        return self.callback

    def get_active_btn(self):
        return self.get_selected_button()

    def get_active_btn_text(self):
        btn = self.get_active_btn()
        if btn == lv.BUTTONMATRIX_BUTTON_NONE:
            return None
        return self.get_button_text(btn)

    def get_selected_button_text(self):
        return self.get_active_btn_text()

    def set_btn_ctrl(self, btn, ctrl):
        self.set_button_ctrl(btn, ctrl)

    def clear_btn_ctrl(self, btn, ctrl):
        self.clear_button_ctrl(btn, ctrl)

    def get_btn_ctrl(self, btn, ctrl):
        return self.has_button_ctrl(btn, ctrl)

    def set_hidden(self, hidden):
        if hidden:
            self.add_flag(lv.obj.FLAG.HIDDEN)
        else:
            self.remove_flag(lv.obj.FLAG.HIDDEN)

    def get_hidden(self):
        return self.has_flag(lv.obj.FLAG.HIDDEN)

    def handle_event(self, obj, code):
        pass

    def _event_cb(self, event):
        code = event.get_code()
        if code == lv.EVENT.PRESSING:
            feed_touch()
        self.handle_event(self, code)
        if self.callback is not None:
            self.callback(self, code)


class HintKeyboard(ButtonMatrix):
    def __init__(self, scr, *args, **kwargs):
        super().__init__(scr, *args, **kwargs)
        self.hint = lv.button(scr)
        self.hint.set_size(50, 60)
        self.hint_lbl = lv.label(self.hint)
        self.hint_lbl.set_text(" ")
        self.hint_lbl.add_style(styles["title"], 0)
        self.hint_lbl.set_size(50, 60)
        self.hint.add_flag(lv.obj.FLAG.HIDDEN)

    def handle_event(self, obj, code):
        if code == lv.EVENT.PRESSING:
            c = self.get_selected_button_text()
            if c is not None and len(c) <= 2:
                self.hint.remove_flag(lv.obj.FLAG.HIDDEN)
                self.hint_lbl.set_text(c)
                indev = lv.indev_active()
                if indev:
                    point = lv.point_t()
                    indev.get_point(point)
                    self.hint.set_pos(point.x - 25, point.y - 130)

        elif code == lv.EVENT.RELEASED:
            self.hint.add_flag(lv.obj.FLAG.HIDDEN)
