import lvgl as lv
from .screen import Screen
from ..common import add_label, add_button
from ..decorators import on_release, cb_with_args

class Menu(Screen):
    def __init__(self, buttons=[], 
                 title="What do you want to do?", note=None,
                 y0=80, last=None
                 ):
        super().__init__()
        y = y0
        self.title = add_label(title, style="title", scr=self)
        if note is not None:
            self.note = add_label(note, style="hint", scr=self)
            self.note.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
            y += self.note.get_height()
        for value, text in buttons:
            if text is not None:
                if value is not None:
                    add_button(text, 
                        on_release(
                            cb_with_args(self.set_value, value)
                        ), y=y, scr=self)
                    y+=85
                else:
                    add_label(text.upper(), y=y+10, style="hint", scr=self)
                    y+=50
            else:
                y+=40
        if last is not None:
            self.add_back_button(*last)

    def add_back_button(self, value, text=None):
        if text is None:
            text = lv.SYMBOL.LEFT+" Back"
        add_button(text, 
                on_release(
                        cb_with_args(self.set_value, value)
                ), scr=self)
