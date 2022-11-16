import lvgl as lv
from .screen import Screen
from ..common import add_label, add_button_pair
from ..decorators import on_release, cb_with_args


class Prompt(Screen):
    def __init__(self, title="Are you sure?", message="Make a choice",
                 confirm_text="Confirm", cancel_text="Cancel", note=None):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        if note is not None:
            self.note = add_label(note, scr=self, style="hint")
            self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
            obj = self.note
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.message = add_label(message, scr=self.page)
        self.page.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)

        (self.cancel_button, self.confirm_button) = add_button_pair(
            cancel_text,
            on_release(cb_with_args(self.set_value, False)),
            confirm_text,
            on_release(cb_with_args(self.set_value, True)),
            scr=self,
        )
