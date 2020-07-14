import lvgl as lv
from .screen import Screen
from ..common import add_label, add_button
from ..decorators import on_release

class Alert(Screen):
    def __init__(self, title, message, button_text=(lv.SYMBOL.LEFT+" Back"), note=None):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        obj = self.title
        if note is not None:
            self.note = add_label(note, scr=self, style="hint")
            self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
            obj = self.note
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.message = add_label(message, scr=self.page)
        self.page.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)

        self.close_button = add_button(scr=self, 
                                callback=on_release(self.release))

        self.close_label = lv.label(self.close_button)
        self.close_label.set_text(button_text)
