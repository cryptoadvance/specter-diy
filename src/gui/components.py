import lvgl as lv
import qrcode
import math
import gc

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
