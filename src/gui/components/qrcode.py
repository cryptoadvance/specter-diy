import lvgl as lv
import lvqr
import qrcode
import math
import gc
import asyncio
import platform

qr_style = lv.style_t()
qr_style.body.main_color = lv.color_hex(0xFFFFFF)
qr_style.body.grad_color = lv.color_hex(0xFFFFFF)
qr_style.body.opa = 255
qr_style.text.opa = 255
qr_style.text.color = lv.color_hex(0)
qr_style.text.line_space = 0
qr_style.text.letter_space = 0
qr_style.body.radius = 10


class QRCode(lv.obj):
    RATE = 500  # ms
    FRAME_SIZE = 300
    MIN_SIZE = 300
    MAX_SIZE = 850

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style = lv.style_t()
        lv.style_copy(style, qr_style)
        style.text.font = lv.font_roboto_16
        style.text.color = lv.color_hex(0x192432)

        self.qr = lvqr.QRCode(self)
        self._text = "Text"
        self.desired_frame_size = self.FRAME_SIZE
        # self.label.set_long_mode(lv.label.LONG.BREAK)
        # self.label.set_align(lv.label.ALIGN.CENTER)
        self.controls = lv.obj(self)
        self.controls.set_style(lv.style_transp_tight)
        self.controls.set_size(240, 40)
        self.controls.set_y(740)
        self.plus = lv.btn(self.controls)
        lbl = lv.label(self.plus)
        lbl.set_text(lv.SYMBOL.PLUS)
        self.plus.set_size(40, 40)
        self.plus.align(self.controls, lv.ALIGN.IN_RIGHT_MID, 0, 0)
        self.plus.set_event_cb(self.on_plus)

        self.minus = lv.btn(self.controls)
        lbl = lv.label(self.minus)
        lbl.set_text(lv.SYMBOL.MINUS)
        self.minus.set_size(40, 40)
        self.minus.align(self.controls, lv.ALIGN.IN_LEFT_MID, 0, 0)
        self.minus.set_event_cb(self.on_minus)

        lbl = lv.label(self.controls)
        lbl.set_text("Frame density")
        lbl.set_style(0, style)
        lbl.set_align(lv.label.ALIGN.CENTER)
        lbl.align(self.controls, lv.ALIGN.CENTER, 0, 0)

        self.controls.set_hidden(True)

        self._original_size = None
        self._press_start = None

        self.note = lv.label(self)
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
                self.idx = (self.idx + 1) % self.frame_num
            await asyncio.sleep_ms(self.RATE)

    def on_plus(self, obj, event):
        # check event
        if event == lv.EVENT.RELEASED:
            self.desired_frame_size = int(self.desired_frame_size*1.2)
            self.set_text(self._text, set_first_frame=True)

    def on_minus(self, obj, event):
        # check event
        if event == lv.EVENT.RELEASED:
            self.desired_frame_size = int(self.desired_frame_size/1.2)
            self.set_text(self._text, set_first_frame=True)

    def cb(self, obj, event):
        # check event
        if event == lv.EVENT.DELETE:
            self.task.cancel()
        elif event == lv.EVENT.PRESSED:
            # get coords
            point = lv.point_t()
            indev = lv.indev_get_act()
            lv.indev_get_point(indev, point)
            self._press_start = point
        elif event == lv.EVENT.RELEASED:
            if len(self._text) <= self.MIN_SIZE or len(self._text) > self.MAX_SIZE:
                self.toggle_fullscreen()
                return
            point = lv.point_t()
            indev = lv.indev_get_act()
            lv.indev_get_point(indev, point)
            # if swipe
            if (
                abs(self._press_start.x - point.x) + abs(self._press_start.y - point.y)
                > 100
            ):
                self.toggle_fullscreen()
                return
            if self.idx is None:
                self.idx = 0
                self.set_frame()
            else:
                self.idx = None
                self._set_text(self._text)
            self.update_note()

    def toggle_fullscreen(self):
        if self._original_size is None:
            self._original_size = (
                self.get_x(),
                self.get_y(),
                self.get_width(),
                self.get_height(),
            )
        if self.is_fullscreen:
            x, y, width, height = self._original_size
        else:
            x, y, width, height = 0, 0, 480, 800
        self.move_foreground()
        self.set_pos(x, y)
        super().set_size(width, height)
        self.qr.set_size(width-10)
        self.qr.align(self, lv.ALIGN.CENTER, 0, 0)
        self.update_note()

    @property
    def is_fullscreen(self):
        if self._original_size is None:
            return False
        # check height is original
        return self._original_size[3] != self.get_height()

    def update_note(self):
        if self.is_fullscreen:
            if len(self._text) > self.MIN_SIZE and len(self._text) <= self.MAX_SIZE:
                self.note.set_text("Click to animate, swipe to shrink.")
            else:
                self.note.set_text("Click to shrink.")
        else:
            if len(self._text) > self.MIN_SIZE and len(self._text) <= self.MAX_SIZE:
                self.note.set_text("Click to animate, swipe to expand.")
            else:
                self.note.set_text("Click to expand")
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        self.controls.set_hidden((not self.is_fullscreen) or (self.idx is None))
        self.controls.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, -100)

    def set_text(self, text="Text", set_first_frame=False):
        if platform.simulator and self._text != text:
            print("QR on screen:", text)
        self._text = text
        self.idx = None
        if text.startswith("UR:BYTES/"):
            payload = text.split("/")[-1]
        else:
            payload = text
        self.frame_num = math.ceil(len(payload) / self.desired_frame_size)
        self.frame_size = math.ceil(len(payload) / self.frame_num)
        # if too large - we have to animate -> set first frame
        if len(self._text) > self.MAX_SIZE or set_first_frame:
            self.idx = 0
            self.set_frame()
        else:
            self._set_text(text)
        self.update_note()

    def set_frame(self):
        if self._text.startswith("UR:BYTES/"):
            arr = self._text.split("/")
            payload = arr[-1]
            prefix = arr[0] + "/%dOF%d/" % (self.idx + 1, self.frame_num)
            prefix += arr[1] + "/"
        else:
            payload = self._text
            prefix = "p%dof%d " % (self.idx + 1, self.frame_num)
        offset = self.frame_size * self.idx
        self._set_text(prefix + payload[offset : offset + self.frame_size])
        note = "Part %d of %d." % (self.idx + 1, self.frame_num)
        if len(self._text) <= self.MAX_SIZE:
            note += " Click to stop."
        else:
            if self.is_fullscreen:
                note += " Click to shrink."
            else:
                note += " Click to expand."
        self.note.set_text(note)
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        self.controls.set_hidden((not self.is_fullscreen) or (self.idx is None))

    def _set_text(self, text):
        # one bcur frame doesn't require checksum
        if text.startswith("UR:BYTES/") and text.count("/") == 2:
            text = "UR:BYTES/" + text.split("/")[-1]
        self.set_style(qr_style)
        self.qr.set_text(text)
        self.qr.align(self, lv.ALIGN.CENTER, 0, 0)
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

    def get_real_text(self):
        return self.qr.get_text()

    def get_text(self):
        return self._text

    def set_size(self, size):
        self.qr.set_size(size)
        super().set_size(size, size)
        self.set_text(self._text)
        self.set_width(self.get_height())
