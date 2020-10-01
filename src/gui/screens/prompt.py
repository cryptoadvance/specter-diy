import lvgl as lv
from .screen import Screen
from ..common import add_label, add_button_pair
from ..decorators import on_release, cb_with_args


class Prompt(Screen):
    def __init__(self, title="Are you sure?", message="Make a choice"):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.message = add_label(message, scr=self.page)
        self.page.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)

        (self.cancel_button, self.confirm_button) = add_button_pair(
            "Cancel",
            on_release(cb_with_args(self.set_value, False)),
            "Confirm",
            on_release(cb_with_args(self.set_value, True)),
            scr=self,
        )
