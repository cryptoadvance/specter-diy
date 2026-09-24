import lvgl as lv
from .screen import Screen
from ..common import add_label, add_button
from ..decorators import on_release


class AdvancedAlert(Screen):
    def __init__(
        self,
        title,
        messages,
        button_text=(lv.SYMBOL.LEFT + " Back"),
        note=None,
        subtitle=None,
    ):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        obj = self.title
        if subtitle is not None:
            self.subtitle = add_label(subtitle, scr=self)
            self.subtitle.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
            obj = self.subtitle
        if note is not None:
            self.note = add_label(note, scr=self, style="hint")
            self.note.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 5)
            obj = self.note
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.page.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 12)

        self.labels = []
        prev = None
        for text, style in messages:
            lbl = add_label(text, scr=self.page, style=style)
            lbl.set_align(lv.label.ALIGN.LEFT)
            if prev is None:
                lbl.align(self.page, lv.ALIGN.IN_TOP_MID, 0, 0)
            else:
                lbl.align(prev, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
            self.labels.append(lbl)
            prev = lbl

        if button_text is not None:
            self.close_button = add_button(scr=self, callback=on_release(self.release))

            self.close_label = lv.label(self.close_button)
            self.close_label.set_text(button_text)

            page_height = self.close_button.get_y() - self.page.get_y() - 12
            if page_height > 0:
                self.page.set_height(page_height)
