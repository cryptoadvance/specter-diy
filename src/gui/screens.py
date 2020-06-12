import lvgl as lv
from .common import *
from .decorators import *
import rng
import asyncio

class Screen(lv.obj):
    def __init__(self):
        super().__init__()
        self.waiting = True
        self._value = None

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

class PinScreen(Screen):
    def __init__(self, title="Enter your PIN code", note=None, get_word=None):
        super().__init__()
        self.title = add_label(title, scr=self, y=PADDING, style="title")
        if note is not None:
            lbl = add_label(note, scr=self, style="hint")
            lbl.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 180)
        self.get_word = get_word
        if get_word is not None:
            self.words = add_label(get_word(b""), scr=self)
            self.words.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 210)
        btnm = lv.btnm(self)
        # shuffle numbers to make sure 
        # no constant fingerprints left on screen
        buttons = ["%d" % i for i in range(0,10)]
        btnmap = []
        for j in range(3):
            for i in range(3):
                v = rng.get_random_bytes(1)[0] % len(buttons)
                btnmap.append(buttons.pop(v))
            btnmap.append("\n")
        btnmap = btnmap+[lv.SYMBOL.CLOSE, buttons.pop(), lv.SYMBOL.OK, ""]
        btnm.set_map(btnmap)
        btnm.set_width(HOR_RES)
        btnm.set_height(HOR_RES)
        btnm.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        # remove feedback on press to avoid sidechannels
        btnm.set_style(lv.btnm.STYLE.BTN_PR,btnm.get_style(lv.btnm.STYLE.BTN_REL))

        self.pin = lv.ta(self)
        self.pin.set_text("")
        self.pin.set_pwd_mode(True)
        style = lv.style_t()
        lv.style_copy(style, styles["theme"].style.ta.oneline)
        style.text.font = lv.font_roboto_28
        style.text.color = lv.color_hex(0xffffff)
        style.text.letter_space = 15
        self.pin.set_style(lv.label.STYLE.MAIN, style)
        self.pin.set_width(HOR_RES-2*PADDING)
        self.pin.set_x(PADDING)
        self.pin.set_y(PADDING+50)
        self.pin.set_cursor_type(lv.CURSOR.HIDDEN)
        self.pin.set_one_line(True)
        self.pin.set_text_align(lv.label.ALIGN.CENTER)
        self.pin.set_pwd_show_time(0)
        self.pin.align(btnm, lv.ALIGN.OUT_TOP_MID, 0, -150)

        btnm.set_event_cb(self.cb);

    def reset(self):
        self.pin.set_text("")
        if self.get_word is not None:
            self.words.set_text(self.get_word(b""))

    @feed_rng
    def cb(self, obj, event):
        if event == lv.EVENT.RELEASED:
            c = obj.get_active_btn_text()
            if c is None:
                return
            if c == lv.SYMBOL.CLOSE:
                self.reset()
            elif c == lv.SYMBOL.OK:
                self.release()
            else:
                self.pin.add_text(c)
                # add new anti-phishing word
                if self.get_word is not None:
                    cur_words = self.words.get_text()
                    cur_words += " "+self.get_word(self.pin.get_text())
                    self.words.set_text(cur_words)


    def get_value(self):
        return self.pin.get_text()

class MenuScreen(Screen):
    def __init__(self, buttons=[], 
                 title="What do you want to do?", note=None,
                 y0=100, last=None
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
