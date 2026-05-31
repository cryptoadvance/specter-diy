import lvgl as lv
import lvqr
import asyncio
import platform

from qrencoder import QREncoder

DEBUG_QR_PAYLOADS = False

qr_style = lv.style_t()
qr_style.init()
qr_style.set_bg_color(lv.color_hex(0xFFFFFF))
qr_style.set_bg_grad_color(lv.color_hex(0xFFFFFF))
qr_style.set_bg_opa(255)
qr_style.set_text_opa(255)
qr_style.set_text_color(lv.color_hex(0))
qr_style.set_text_line_space(0)
qr_style.set_text_letter_space(0)
qr_style.set_radius(10)

# Transparent style (replacement for lv.style_transp_tight)
style_transp = lv.style_t()
style_transp.init()
style_transp.set_bg_opa(0)
style_transp.set_border_width(0)
style_transp.set_outline_width(0)
style_transp.set_shadow_width(0)
style_transp.set_radius(0)
style_transp.set_pad_all(0)

qr_btn_style = lv.style_t()
qr_btn_style.init()
qr_btn_style.set_bg_color(lv.color_hex(0x506072))
qr_btn_style.set_bg_opa(255)
qr_btn_style.set_border_width(0)
qr_btn_style.set_outline_width(0)
qr_btn_style.set_shadow_width(0)
qr_btn_style.set_radius(10)
qr_btn_style.set_pad_all(0)

qr_btn_pressed_style = lv.style_t()
qr_btn_pressed_style.init()
qr_btn_pressed_style.set_bg_color(lv.color_hex(0x405062))
qr_btn_pressed_style.set_bg_opa(255)
qr_btn_pressed_style.set_border_width(0)
qr_btn_pressed_style.set_outline_width(0)
qr_btn_pressed_style.set_shadow_width(0)
qr_btn_pressed_style.set_radius(10)
qr_btn_pressed_style.set_pad_all(0)

qr_btn_label_style = lv.style_t()
qr_btn_label_style.init()
qr_btn_label_style.set_text_color(lv.color_hex(0xFFFFFF))
qr_btn_label_style.set_text_font(lv.font_montserrat_28)

QR_SIZES = [17, 32, 53, 78, 106, 154, 192, 230, 271, 367, 458, 586, 718, 858]
BTNSIZE = 70
QR_INSET = 43
QR_NOTE_Y = 0
QR_FULLSCREEN_INSET = 15

def center_label(lbl):
    lbl.update_layout()
    lbl.center()

class QRCode(lv.obj):
    """QR widget with a square-only set_size(size) compatibility method.

    Unlike lv.obj.set_size(width, height), set_size() accepts one dimension.
    """

    RATE = 500  # ms
    FRAME_SIZE = 300
    QR_VERSION = 10
    MIN_SIZE = 300
    MAX_SIZE = QR_SIZES[-1]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style = lv.style_t()
        style.init()
        style.set_bg_color(lv.color_hex(0xFFFFFF))
        style.set_bg_opa(255)
        style.set_text_font(lv.font_montserrat_16)
        style.set_text_color(lv.color_hex(0x192432))
        note_style = lv.style_t()
        note_style.init()
        note_style.set_bg_color(lv.color_hex(0xFFFFFF))
        note_style.set_bg_opa(255)
        note_style.set_text_font(lv.font_montserrat_16)
        note_style.set_text_color(lv.color_hex(0x192432))

        self.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.remove_flag(lv.obj.FLAG.SCROLLABLE)

        self.encoder = None
        self._autoplay = True

        self.qr = lvqr.QRCode(self)
        self.qr.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.qr.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self._text = "Text"
        self._qr_text = None
        self._version_range = None
        self._qr_inset = QR_INSET
        self._fixed_size = False
        self.version = self.QR_VERSION

        self._original_size = None
        self._fullscreen = False
        self._box_width = self.MIN_SIZE
        self._box_height = self.MIN_SIZE
        self._press_start = None

        self.text_style = style
        self.note_style = note_style
        self.spacing_style = None
        self.create_density_controls(style)
        self.create_playback_controls(style)

        self.note = lv.label(self)
        self.note.add_style(self.note_style, 0)
        self.note.set_text("")
        self.note.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        self.set_text(self._text)
        self.task = asyncio.create_task(self.animate())
        self.add_event_cb(self.cb, lv.EVENT.ALL, None)

        self._spacing = 0

    @property
    def spacing(self):
        return self._spacing

    @spacing.setter
    def spacing(self, spacing):
        sp_style = lv.style_t()
        sp_style.init()
        sp_style.set_border_width(spacing)
        self.qr.add_style(sp_style, 0)
        self.spacing_style = sp_style
        self._spacing = spacing

    def _set_hidden(self, obj, hidden):
        if hidden:
            obj.add_flag(lv.obj.FLAG.HIDDEN)
        else:
            obj.remove_flag(lv.obj.FLAG.HIDDEN)

    def _create_icon_button(self, parent, text, callback):
        btn = lv.button(parent)
        btn.set_size(BTNSIZE, BTNSIZE)
        btn.add_style(qr_btn_style, 0)
        btn.add_style(qr_btn_pressed_style, lv.STATE.PRESSED)
        btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
        btn.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        lbl = lv.label(btn)
        lbl.set_text(text)
        lbl.add_style(qr_btn_label_style, 0)
        center_label(lbl)
        btn.add_event_cb(callback, lv.EVENT.CLICKED, None)
        return btn, lbl

    def create_playback_controls(self, style):
        self.playback = lv.obj(self)
        self.playback.add_style(style_transp, 0)
        self.playback.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.playback.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.playback.set_size(480, BTNSIZE)
        self.playback.set_y(640)

        nextbtn, lbl = self._create_icon_button(self.playback, lv.SYMBOL.NEXT, self.on_next)
        nextbtn.align_to(self.playback, lv.ALIGN.CENTER, 144, 0)

        prevbtn, lbl = self._create_icon_button(self.playback, lv.SYMBOL.PREV, self.on_prev)
        prevbtn.align_to(self.playback, lv.ALIGN.CENTER, -144, 0)

        pausebtn, self.pauselbl = self._create_icon_button(self.playback, lv.SYMBOL.PAUSE, self.on_pause)
        pausebtn.align_to(self.playback, lv.ALIGN.CENTER, 48, 0)

        stopbtn, lbl = self._create_icon_button(self.playback, lv.SYMBOL.STOP, self.on_stop)
        stopbtn.align_to(self.playback, lv.ALIGN.CENTER, -48, 0)

        self.play, lbl = self._create_icon_button(self, lv.SYMBOL.PLAY, self.on_play)
        self.play.align(lv.ALIGN.BOTTOM_MID, 0, -150)
        self._set_hidden(self.play, False)

        self._set_hidden(self.playback, True)

    def create_density_controls(self, style):
        self.controls = lv.obj(self)
        self.controls.add_style(style_transp, 0)
        self.controls.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.controls.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.controls.set_size(480, BTNSIZE)
        self.controls.set_y(740)
        plus, lbl = self._create_icon_button(self.controls, lv.SYMBOL.PLUS, self.on_plus)
        plus.align_to(self.controls, lv.ALIGN.CENTER, 144, 0)

        minus, lbl = self._create_icon_button(self.controls, lv.SYMBOL.MINUS, self.on_minus)
        minus.align_to(self.controls, lv.ALIGN.CENTER, -144, 0)

        lbl = lv.label(self.controls)
        lbl.set_text("QR code density")
        lbl.add_style(style, 0)
        lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        lbl.align_to(self.controls, lv.ALIGN.CENTER, 0, 0)

        self._set_hidden(self.controls, True)

    async def animate(self):
        while True:
            if self.idx is not None:
                self.set_frame()
                if self._autoplay:
                    self.idx += 1
                if not (self.encoder and self.encoder.is_infinite):
                    self.idx = self.idx % self.frame_num
            await asyncio.sleep_ms(self.RATE)

    def on_plus(self, event):
        if (self.version + 1) < len(QR_SIZES):
            self.version += 1
            if self.idx is not None:
                self.idx = 0
            if self.encoder:
                self.encoder.part_len = QR_SIZES[self.version]
                self.frame_num = len(self.encoder)

    def on_minus(self, event):
        if self.version > 0:
            self.version -= 1
            if self.idx is not None:
                self.idx = 0
            if self.encoder:
                self.encoder.part_len = QR_SIZES[self.version]
                self.frame_num = len(self.encoder)

    def on_pause(self, event):
        self._autoplay = not self._autoplay
        self.pauselbl.set_text(lv.SYMBOL.PAUSE if self._autoplay else lv.SYMBOL.PLAY)
        center_label(self.pauselbl)

    def on_stop(self, event):
        if not self._text: # can't stop
            return
        self.idx = None
        self._set_text(self._text)
        self.check_controls()

    def on_play(self, event):
        self.idx = 0
        self.set_frame()
        self.check_controls()

    def on_next(self, event):
        self.idx = (self.idx + 1) % self.frame_num
        self.set_frame()

    def on_prev(self, event):
        self.idx = (self.idx + self.frame_num - 1) % self.frame_num
        self.set_frame()

    def cb(self, event):
        # check event
        code = event.get_code()
        if code == lv.EVENT.DELETE:
            if self.task is not None:
                task = self.task
                self.task = None
                task.cancel()
        elif code == lv.EVENT.CLICKED:
            self.toggle_fullscreen()

    def toggle_fullscreen(self):
        if self._original_size is None:
            self._original_size = (
                self.get_x(),
                self.get_y(),
                self._box_width,
                self._box_height,
            )
        if self.is_fullscreen:
            x, y, width, height = self._original_size
            self._fullscreen = False
        else:
            x, y, width, height = 0, 0, 480, 800
            self._fullscreen = True
        self.move_foreground()
        self.set_pos(x, y)
        self._box_width = width
        self._box_height = height
        super().set_size(width, height)
        self._resize_qr()
        self.update_note()

    @property
    def is_fullscreen(self):
        return self._fullscreen

    def _qr_size(self):
        if self.is_fullscreen:
            return min(self._box_width, self._box_height) - 2 * QR_FULLSCREEN_INSET
        return min(self._box_width, self._box_height) - 2 * self._qr_inset

    def _resize_qr(self):
        self.qr.set_size(self._qr_size())
        if self._qr_text is not None:
            self._set_text(self._qr_text)
        self._align_qr()

    def _align_qr(self):
        if self.is_fullscreen:
            self.qr.align(lv.ALIGN.CENTER, 0, -100 if self._box_height == 800 else 0)
        else:
            self.qr.align(lv.ALIGN.TOP_MID, 0, self._qr_inset - 15)

    def _align_note(self):
        self.note.align(lv.ALIGN.BOTTOM_MID, 0, 0 if self.is_fullscreen else QR_NOTE_Y)

    def update_note(self):
        if self.is_fullscreen:
            self.note.set_text("Click to shrink.")
        else:
            self.note.set_text("Click to expand%s." % (" and control" if self.encoder else ""))
        self._align_note()
        self.controls.align(lv.ALIGN.BOTTOM_MID, 0, -40)
        self.playback.align(lv.ALIGN.BOTTOM_MID, 0, -150)
        self.play.align(lv.ALIGN.BOTTOM_MID, 0, -150)
        self.check_controls()

    def set_text(self, text="Text", set_first_frame=False):
        if DEBUG_QR_PAYLOADS and platform.simulator and self._text != text:
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
            if self.encoder.is_infinite:
                note = ""
            else:
                frameCount = len(self.encoder)
                currentFrame = self.idx + 1
                note = "Part %d of %d." % (currentFrame, frameCount)
        else:
            self._set_text(self._text)
            note = ""
        if self.is_fullscreen:
            note += " Click to shrink."
        else:
            note += " Click to expand%s." % (" and control" if self.encoder else "")
        self.note.set_text(note)
        self._align_note()
        self.check_controls()

    def check_controls(self):
        self._set_hidden(self.controls, (not self.is_fullscreen) or (self.idx is None) or (self.encoder is None))
        self._set_hidden(self.playback, (not self.is_fullscreen) or (self.idx is None))
        self._set_hidden(self.play, (not self.is_fullscreen) or (self.idx is not None) or (self.encoder is None))

    def set_version_range(self, min_ver=0, max_ver=0):
        self._version_range = None if min_ver == 0 and max_ver == 0 else (min_ver, max_ver)
        self.qr.set_version_range(min_ver, max_ver)

    def set_qr_inset(self, inset=QR_INSET):
        self._qr_inset = inset
        self._resize_qr()

    def set_fixed_size(self, enable=False):
        self._fixed_size = enable
        self.qr.set_fixed_size(enable)

    def _set_text(self, text):
        # one bcur frame doesn't require checksum
        payload_changed = self._qr_text != text
        self._qr_text = text
        self.add_style(qr_style, 0)
        self.qr.set_fixed_size(self._fixed_size)
        if self._version_range is not None:
            self.qr.set_version_range(self._version_range[0], self._version_range[1])
        elif payload_changed:
            self.qr.clear_version_range()
        res = self.qr.set_text(text)
        if self.encoder is None and res and self._version_range is None:
            self.qr.lock_selected_version()
        self._align_qr()
        self._align_note()

    def get_real_text(self):
        return self.qr.get_text()

    def get_text(self):
        return self._text

    def set_size(self, size):
        self._box_width = size
        self._box_height = size
        super().set_size(size, size)
        self._resize_qr()
        self.set_text(self.encoder or self._text)
