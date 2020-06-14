"""GUI components used as widgets on different screens"""
import lvgl as lv
import qrcode
import math
import gc
from .decorators import feed_touch

styles = {}

qr_style = lv.style_t()
qr_style.body.main_color = lv.color_hex(0xffffff)
qr_style.body.grad_color = lv.color_hex(0xffffff)
qr_style.body.opa = 255
qr_style.text.opa = 255
qr_style.text.color = lv.color_hex(0)
qr_style.text.line_space = 0
qr_style.text.letter_space = 0

class QRCode(lv.label):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = "Text"
        self.set_long_mode(lv.label.LONG.BREAK)
        self.set_align(lv.label.ALIGN.CENTER)
        self.set_text(self._text)
    
    def set_text(self, text="Text"):
        if self._text != text:
            print("QR on screen:", text)
        self._text = text
        qr = qrcode.encode_to_string(text)
        size = int(math.sqrt(len(qr))) # + 4 clear space on every side
        width = self.get_width()
        scale = width//size
        sizes = range(1,10)
        fontsize = [s for s in sizes if s < scale or s == 1][-1]
        font = getattr(lv, "square%d" % fontsize)
        style = lv.style_t()
        lv.style_copy(style, qr_style)
        style.text.font = font
        pad = 4*fontsize
        style.body.radius = fontsize
        style.body.padding.top = pad
        style.body.padding.left = pad
        style.body.padding.right = pad
        style.body.padding.bottom = pad-fontsize # there is \n at the end
        self.set_style(lv.label.STYLE.MAIN, style)
        self.set_body_draw(True)
        super().set_text(qr)
        del qr
        gc.collect()
    
    def get_real_text(self):
        return super().get_text()

    def get_text(self):
        return self._text
    
    def set_size(self, size):
        super().set_size(size, size)
        self.set_text(self._text)
        super().set_width(super().get_height())

class MnemonicTable(lv.table):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.words = [""]
        # styles
        cell_style = lv.style_t()
        lv.style_copy(cell_style, styles["theme"].style.label.prim)
        cell_style.body.opa = 0
        cell_style.text.font = lv.font_roboto_22

        num_style = lv.style_t()
        lv.style_copy(num_style, cell_style)
        num_style.text.opa = lv.OPA._40

        self.set_col_cnt(4)
        self.set_row_cnt(12)
        self.set_col_width(0, 50)
        self.set_col_width(2, 50)
        self.set_col_width(1, 150)
        self.set_col_width(3, 150)

        self.set_style(lv.page.STYLE.BG, cell_style)
        self.set_style(lv.table.STYLE.CELL1, cell_style)
        self.set_style(lv.table.STYLE.CELL2, num_style)

        for i in range(12):
            self.set_cell_value(i, 0, "%d" % (i+1))
            self.set_cell_value(i, 2, "%d" % (i+13))
            self.set_cell_type(i, 0, lv.table.STYLE.CELL2)
            self.set_cell_type(i, 2, lv.table.STYLE.CELL2)

    def set_mnemonic(self, mnemonic:str):
        self.words = mnemonic.split()
        self.update()

    def update(self):
        for i in range(24):
            row = i%12
            col = 1+2*(i//12)
            if i < len(self.words):
                self.set_cell_value(row, col, self.words[i])
            else:
                self.set_cell_value(row, col, "")

    def get_mnemonic(self) -> str:
        return " ".join(self.words)

    def get_last_word(self) -> str:
        if len(self.words) == 0:
            return ""
        else:
            return self.words[-1]

    def del_char(self):
        if len(self.words) == 0:
            return
        if len(self.words[-1]) == 0:
            self.words = self.words[:-1]
        else:
            self.words[-1] = self.words[-1][:-1]
        self.update()

    def autocomplete_word(self, word):
        if len(self.words) == 0:
            self.words.append(word)
        else:
            self.words[-1] = word
        self.words.append("")
        self.update()

    def add_char(self, c):
        if len(self.words) == 0:
            self.words.append(c)
        else:
            self.words[-1] += c
        self.update()

class HintKeyboard(lv.btnm):
    def __init__(self, scr, *args, **kwargs):
        super().__init__(scr, *args, **kwargs)
        self.hint = lv.btn(scr)
        self.hint.set_size(50,60)
        self.hint_lbl = lv.label(self.hint)
        self.hint_lbl.set_text(" ")
        self.hint_lbl.set_style(0, styles["title"])
        self.hint_lbl.set_size(50,60)
        self.hint.set_hidden(True)
        self.callback = None
        super().set_event_cb(self.cb)

    def set_event_cb(self, callback):
        self.callback = callback

    def get_event_cb(self):
        return self.callback

    def cb(self, obj, event):
        if event == lv.EVENT.PRESSING:
            feed_touch()
            c = obj.get_active_btn_text()
            if c is not None and len(c)<=2:
                self.hint.set_hidden(False)
                self.hint_lbl.set_text(c)
                point = lv.point_t()
                indev = lv.indev_get_act()
                lv.indev_get_point(indev, point)
                self.hint.set_pos(point.x-25, point.y-130)

        elif event == lv.EVENT.RELEASED:
            self.hint.set_hidden(True)

        if self.callback is not None:
            self.callback(obj, event)

