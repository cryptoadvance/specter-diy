import lvgl as lv
import qrcode
import math
import gc
import asyncio

qr_style = lv.style_t()
qr_style.body.main_color = lv.color_hex(0xffffff)
qr_style.body.grad_color = lv.color_hex(0xffffff)
qr_style.body.opa = 255
qr_style.text.opa = 255
qr_style.text.color = lv.color_hex(0)
qr_style.text.line_space = 0
qr_style.text.letter_space = 0

class QRCode(lv.obj):
    RATE = 200 # ms
    FRAME_SIZE = 300
    MIN_SIZE = 300
    MAX_SIZE = 850
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label = lv.label(self)
        self._text = "Text"
        self.label.set_long_mode(lv.label.LONG.BREAK)
        self.label.set_align(lv.label.ALIGN.CENTER)

        self.note = lv.label(self)
        style = lv.style_t()
        lv.style_copy(style, qr_style)
        style.text.font = lv.font_roboto_16
        style.text.color = lv.color_hex(0x192432)
        self.note.set_style(0, style)
        self.note.set_text("")
        self.note.set_align(lv.label.ALIGN.CENTER)

        self.set_text(self._text)
        self.task = asyncio.create_task(self.animate())
        self.set_event_cb(self.cb)

    async def animate(self):
        while True:
            if self.idx is not None:
                self.set_frame()
                self.idx = (self.idx+1) % self.frame_num
            await asyncio.sleep_ms(self.RATE)

    def cb(self, obj, event):
        if event == lv.EVENT.DELETE:
            self.task.cancel()
        if event == lv.EVENT.RELEASED:
            # nothing to do here
            if len(self._text) <= self.MIN_SIZE or len(self._text) > self.MAX_SIZE:
                return
            if self.idx is None:
                self.idx = 0
                self.set_frame()
            else:
                self.idx = None
                self._set_text(self._text)
                self.note.set_text("Click to animate")
                self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

    def set_text(self, text="Text"):
        if self._text != text:
            print("QR on screen:", text)
        self._text = text
        self.idx = None
        self.frame_num = math.ceil(len(self._text)/self.FRAME_SIZE)
        self.frame_size = math.ceil(len(self._text) / self.frame_num)
        # if too large - we have to animate -> set first frame
        if len(self._text) > self.MAX_SIZE:
            self.idx = 0
            self.set_frame()
        else:
            self._set_text(text)
        if len(text) > self.MIN_SIZE and len(text) <= self.MAX_SIZE:
            self.note.set_text("Click to animate")
            self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        else:
            self.note.set_text("")

    def set_frame(self):
        prefix = "p%dof%d " % (self.idx+1, self.frame_num)
        offset = self.frame_size*self.idx
        self._set_text(prefix+self._text[offset:offset+self.frame_size])
        self.note.set_text("Part %d of %d. Click to stop." % (self.idx+1, self.frame_num))
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

    def _set_text(self, text):
        qr = qrcode.encode_to_string(text).strip()
        size = int(math.sqrt(len(qr))) # + 4 clear space on every side
        width = self.get_width()
        scale = width//size
        sizes = range(1,10)
        fontsize = [s for s in sizes if s < scale or s == 1][-1]
        font = getattr(lv, "square%d" % fontsize)
        style = lv.style_t()
        lv.style_copy(style, qr_style)
        style.text.font = font
        style.body.radius = fontsize
        self.set_style(style)
        self.label.set_text(qr)
        self.label.align(self, lv.ALIGN.CENTER, 0, 0)
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        del qr
        gc.collect()

    def get_real_text(self):
        return self.label.get_text()

    def get_text(self):
        return self._text
    
    def set_size(self, size):
        self.label.set_size(size, size)
        super().set_size(size, size)
        self.set_text(self._text)
        self.set_width(self.get_height())
