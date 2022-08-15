import lvgl as lv
import lvqr
import qrcode
import math
import gc
import asyncio
import platform

from io import BytesIO
from qrencoder import QREncoder

qr_style = lv.style_t()
qr_style.body.main_color = lv.color_hex(0xFFFFFF)
qr_style.body.grad_color = lv.color_hex(0xFFFFFF)
qr_style.body.opa = 255
qr_style.text.opa = 255
qr_style.text.color = lv.color_hex(0)
qr_style.text.line_space = 0
qr_style.text.letter_space = 0
qr_style.body.radius = 10

QR_SIZES = [17, 32, 53, 78, 106, 154, 192, 230, 271, 367, 458, 586, 718, 858]
BTNSIZE = 70

class QRCode(lv.obj):
    RATE = 500  # ms
    FRAME_SIZE = 300
    QR_VERSION = 10
    MIN_SIZE = 300
    MAX_SIZE = QR_SIZES[-1]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style = lv.style_t()
        lv.style_copy(style, qr_style)
        style.text.font = lv.font_roboto_16
        style.text.color = lv.color_hex(0x192432)

        self.encoder = None
        self._autoplay = True

        self.qr = lvqr.QRCode(self)
        self._text = "Text"
        self.version = self.QR_VERSION

        self._original_size = None
        self._press_start = None

        self.create_density_controls(style)
        self.create_playback_controls(style)

        self.note = lv.label(self)
        self.note.set_style(0, style)
        self.note.set_text("")
        self.note.set_align(lv.label.ALIGN.CENTER)

        self.set_text(self._text)
        self.task = asyncio.create_task(self.animate())
        self.set_event_cb(self.cb)


    def create_playback_controls(self, style):
        self.playback = lv.obj(self)
        self.playback.set_style(lv.style_transp_tight)
        self.playback.set_size(480, BTNSIZE)
        self.playback.set_y(640)

        nextbtn = lv.btn(self.playback)
        lbl = lv.label(nextbtn)
        lbl.set_text(lv.SYMBOL.NEXT)
        nextbtn.set_size(BTNSIZE, BTNSIZE)
        nextbtn.align(self.playback, lv.ALIGN.CENTER, 144, 0)
        nextbtn.set_event_cb(self.on_next)

        prevbtn = lv.btn(self.playback)
        lbl = lv.label(prevbtn)
        lbl.set_text(lv.SYMBOL.PREV)
        prevbtn.set_size(BTNSIZE, BTNSIZE)
        prevbtn.align(self.playback, lv.ALIGN.CENTER, -144, 0)
        prevbtn.set_event_cb(self.on_prev)

        pausebtn = lv.btn(self.playback)
        self.pauselbl = lv.label(pausebtn)
        self.pauselbl.set_text(lv.SYMBOL.PAUSE)
        pausebtn.set_size(BTNSIZE, BTNSIZE)
        pausebtn.align(self.playback, lv.ALIGN.CENTER, 48, 0)
        pausebtn.set_event_cb(self.on_pause)

        stopbtn = lv.btn(self.playback)
        lbl = lv.label(stopbtn)
        lbl.set_text(lv.SYMBOL.STOP)
        stopbtn.set_size(BTNSIZE, BTNSIZE)
        stopbtn.align(self.playback, lv.ALIGN.CENTER, -48, 0)
        stopbtn.set_event_cb(self.on_stop)

        self.play = lv.btn(self)
        lbl = lv.label(self.play)
        lbl.set_text(lv.SYMBOL.PLAY)
        self.play.set_size(BTNSIZE, BTNSIZE)
        self.play.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, -150)
        self.play.set_event_cb(self.on_play)
        self.play.set_hidden(False)

        self.playback.set_hidden(True)

    def create_density_controls(self, style):
        self.controls = lv.obj(self)
        self.controls.set_style(lv.style_transp_tight)
        self.controls.set_size(480, BTNSIZE)
        self.controls.set_y(740)
        plus = lv.btn(self.controls)
        lbl = lv.label(plus)
        lbl.set_text(lv.SYMBOL.PLUS)
        plus.set_size(BTNSIZE, BTNSIZE)
        plus.align(self.controls, lv.ALIGN.CENTER, 144, 0)
        plus.set_event_cb(self.on_plus)

        minus = lv.btn(self.controls)
        lbl = lv.label(minus)
        lbl.set_text(lv.SYMBOL.MINUS)
        minus.set_size(BTNSIZE, BTNSIZE)
        minus.align(self.controls, lv.ALIGN.CENTER, -144, 0)
        minus.set_event_cb(self.on_minus)

        lbl = lv.label(self.controls)
        lbl.set_text("QR code density")
        lbl.set_style(0, style)
        lbl.set_align(lv.label.ALIGN.CENTER)
        lbl.align(self.controls, lv.ALIGN.CENTER, 0, 0)

        self.controls.set_hidden(True)

    async def animate(self):
        while True:
            if self.idx is not None:
                self.set_frame()
                if self._autoplay:
                    self.idx += 1
                if not (self.encoder and self.encoder.is_infinite):
                    self.idx = self.idx % self.frame_num
            await asyncio.sleep_ms(self.RATE)

    def on_plus(self, obj, event):
        if event == lv.EVENT.RELEASED and (self.version + 1) < len(QR_SIZES):
            self.version += 1
            if self.idx is not None:
                self.idx = 0
            if self.encoder:
                self.encoder.part_len = QR_SIZES[self.version]
                self.frame_num = len(self.encoder)

    def on_minus(self, obj, event):
        if event == lv.EVENT.RELEASED and self.version > 0:
            self.version -= 1
            if self.idx is not None:
                self.idx = 0
            if self.encoder:
                self.encoder.part_len = QR_SIZES[self.version]
                self.frame_num = len(self.encoder)

    def on_pause(self, obj, event):
        if event == lv.EVENT.RELEASED:
            self._autoplay = not self._autoplay
            self.pauselbl.set_text(lv.SYMBOL.PAUSE if self._autoplay else lv.SYMBOL.PLAY)

    def on_stop(self, obj, event):
        if event == lv.EVENT.RELEASED:
            if not self._text: # can't stop
                return
            self.idx = None
            self._set_text(self._text)
            self.check_controls()

    def on_play(self, obj, event):
        if event == lv.EVENT.RELEASED:
            self.idx = 0
            self.set_frame()
            self.check_controls()

    def on_next(self, obj, event):
        if event == lv.EVENT.RELEASED:
            self.idx = (self.idx + 1) % self.frame_num
            self.set_frame()

    def on_prev(self, obj, event):
        if event == lv.EVENT.RELEASED:
            self.idx = (self.idx + self.frame_num - 1) % self.frame_num
            self.set_frame()

    def cb(self, obj, event):
        # check event
        if event == lv.EVENT.DELETE:
            self.task.cancel()
        elif event == lv.EVENT.RELEASED:
            self.toggle_fullscreen()

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
        self.qr.align(self, lv.ALIGN.CENTER, 0, -100 if height==800 else 0)
        self.update_note()

    @property
    def is_fullscreen(self):
        if self._original_size is None:
            return False
        # check height is original
        return self._original_size[3] != self.get_height()

    def update_note(self):
        if self.is_fullscreen:
            self.note.set_text("Click to shrink.")
        else:
            self.note.set_text("Click to expand%s." % (" and control" if self.encoder else ""))
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        self.controls.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, -40)
        self.playback.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, -150)
        self.play.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, -150)
        self.check_controls()

    def set_text(self, text="Text", set_first_frame=False):
        if platform.simulator and self._text != text:
            print("QR on screen:", text)
        self.encoder = None
        self._text = text
        if isinstance(text, QREncoder):
            self.encoder = text
            self._text = text.get_full(self.MAX_SIZE)
            self.frame_num = len(self.encoder)
            if not self._text: # we can't get full data in one QR
                self.idx = 0
                self.set_frame()
                self._autoplay = True
                return
        self.idx = None
        self._set_text(self._text)
        self.update_note()

    def set_frame(self):
        if self.encoder:
            payload = self.encoder[self.idx]
            self._set_text(payload)
            note = "Part %d of %d." % (self.idx + 1, len(self.encoder))
        else:
            self._set_text(self._text)
            note = ""
        if self.is_fullscreen:
            note += " Click to shrink."
        else:
            note += " Click to expand%s." % (" and control" if self.encoder else "")
        self.note.set_text(note)
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)
        self.check_controls()

    def check_controls(self):
        self.controls.set_hidden((not self.is_fullscreen) or (self.idx is None) or (self.encoder is None))
        self.playback.set_hidden((not self.is_fullscreen) or (self.idx is None))
        self.play.set_hidden((not self.is_fullscreen) or (self.idx is not None) or (self.encoder is None))

    def _set_text(self, text):
        # one bcur frame doesn't require checksum
        print(text)
        self.set_style(qr_style)
        self.qr.set_text(text)
        self.qr.align(self, lv.ALIGN.CENTER, 0, -100 if self.is_fullscreen else 0)
        self.note.align(self, lv.ALIGN.IN_BOTTOM_MID, 0, 0)

    def get_real_text(self):
        return self.qr.get_text()

    def get_text(self):
        return self._text

    def set_size(self, size):
        self.qr.set_size(size)
        super().set_size(size, size)
        self.set_text(self.encoder or self._text)
        self.set_width(self.get_height())
