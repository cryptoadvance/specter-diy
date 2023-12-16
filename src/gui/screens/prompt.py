import lvgl as lv
from .screen import Screen
from ..common import add_label, add_button_pair
from ..decorators import on_release, cb_with_args


class Prompt(Screen):
    def __init__(self, title="Are you sure?", message="Make a choice",
                 confirm_text="Confirm", cancel_text="Cancel", note=None, warning=None):
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
        self.icon = lv.label(self)

        (self.cancel_button, self.confirm_button) = add_button_pair(
            cancel_text,
            on_release(cb_with_args(self.set_value, False)),
            confirm_text,
            on_release(cb_with_args(self.set_value, True)),
            scr=self,
        )

        if warning:
            self.warning = add_label(warning, scr=self, style="warning")
            self.icon.set_text(lv.SYMBOL.WARNING)
            
            # Align warning text
            y_pos = self.cancel_button.get_y() - 60 # above the buttons
            x_pos = self.get_width() // 2 - self.warning.get_width() // 2 # in the center of the prompt
            self.warning.set_pos(x_pos, y_pos)
            
            # Align warning icon to the left of the title
            self.icon.align(self.title, lv.ALIGN.IN_LEFT_MID, 90, 0)

