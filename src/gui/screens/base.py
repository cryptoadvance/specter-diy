"""Base screens for inheritance etc"""
import lvgl as lv
from ..common import *
from ..decorators import *
import asyncio

class Screen(lv.obj):
    network = 'test'
    COLORS = {
        'main': lv.color_hex(0xFF9A00),
        'test': lv.color_hex(0x00F100),
        'regtest': lv.color_hex(0x00CAF1),
        'signet': lv.color_hex(0xBD10E0),
    }
    def __init__(self):
        super().__init__()
        self.waiting = True
        self._value = None

        if type(self).network in type(self).COLORS:
            self.topbar = lv.obj(self)
            s = lv.style_t()
            lv.style_copy(s, styles["theme"].style.btn.rel)
            s.body.main_color = type(self).COLORS[type(self).network]
            s.body.grad_color = type(self).COLORS[type(self).network]
            s.body.opa = 200
            s.body.radius = 0
            s.body.border.width = 0
            self.topbar.set_style(s)
            self.topbar.set_size(HOR_RES, 5)
            self.topbar.set_pos(0, 0)

    def release(self):
        self.waiting = False

    def get_value(self):
        """
        Redefine this function to get value entered by the user
        """
        return self._value

    def set_value(self, value):
        self._value = value
        self.release()

    async def result(self):
        self.waiting = True
        while self.waiting:
            await asyncio.sleep_ms(1)
        return self.get_value()

class MenuScreen(Screen):
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

class Alert(Screen):
    def __init__(self, title, message, button_text=(lv.SYMBOL.LEFT+" Back")):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.message = add_label(message, scr=self.page)
        self.page.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)

        self.close_button = add_button(scr=self, 
                                callback=on_release(self.release))

        self.close_label = lv.label(self.close_button)
        self.close_label.set_text(button_text)

class Prompt(Screen):
    def __init__(self, title="Are you sure?", message="Make a choice"):
        super().__init__()
        self.title = add_label(title, scr=self, style="title")
        self.page = lv.page(self)
        self.page.set_size(480, 600)
        self.message = add_label(message, scr=self.page)
        self.page.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)

        (self.cancel_button, 
         self.confirm_button) = add_button_pair(
                    "Cancel", on_release(cb_with_args(self.set_value,False)), 
                    "Confirm", on_release(cb_with_args(self.set_value,True)), 
                    scr=self)

class QRAlert(Alert):
    def __init__(self,
                 title="QR Alert!", 
                 message="Something happened", 
                 qr_message=None,
                 qr_width=None,
                 button_text="Close"):
        if qr_message is None:
            qr_message = message
        super().__init__(title, message, button_text)
        self.qr = add_qrcode(qr_message, scr=self, width=qr_width)
        self.qr.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
