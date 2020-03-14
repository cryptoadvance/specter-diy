import lvgl as lv
import qrcode
import math
import gc
import micropython
from .common import styles
from math import ceil
from platform import simulator
if not simulator:
    import pyb

qr_style = lv.style_t()
qr_style.body.main_color = lv.color_hex(0xffffff)
qr_style.body.grad_color = lv.color_hex(0xffffff)
qr_style.body.opa = 255
qr_style.text.opa = 255
qr_style.text.color = lv.color_hex(0)
qr_style.text.line_space = 0
qr_style.text.letter_space = 0

QR_PADDING = const(40)

def add_qrcode(text, y=QR_PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if scr is None:
        scr = lv.scr_act()
    if width is None:
        width = 300
    qr = QRCode(width, scr)
    qr.set_text(text)
    return qr

class QrA:
    """
    Example of animated qr: p1of3 payload
    """
    timeout = False
    animate_ptr = None
    isQRplaying = False
    isQRtoobig = False
    timer = None
    indx = []
    payload = []
    abort = False

    @staticmethod
    def header():
        if len(QrA.indx) != 2 or not QrA.isQRplaying:
            return ""
        return "p" + str(QrA.indx[0]+1) + "of" + str(QrA.indx[1]+1) + " "

    @staticmethod
    def indx_to_str():
        return "Part: " + str(QrA.indx[0]+1) + " / " + str(QrA.indx[1]+1)

    @staticmethod
    def average_chunk_size(msg_size, max_chunk_size):
        number_of_chunks = ceil(msg_size / max_chunk_size)
        return ceil(msg_size / number_of_chunks)

    @staticmethod
    def init(animate):
        QrA.clean()
        QrA.animate_ptr = animate

    @staticmethod
    def run():
        def QrAtimeout(tim):
            QrA.timeout = True
        QrA.timer = pyb.Timer(1, freq=3)
        QrA.timer.callback(QrAtimeout)

    @staticmethod
    def qr_cb(obj, event):
        if event == lv.EVENT.RELEASED:
            if QrA.isQRtoobig:
                QrA.isQRplaying = True
            else:
                QrA.isQRplaying = not QrA.isQRplaying

    @staticmethod
    def handle():
        # call in main loop
        if QrA.abort:
            if QrA.timer:
                QrA.timer.deinit()
                QrA.timeout = False
            QrA.isQRplaying = False
            QrA.abort = False
        elif QrA.timeout == True:
            QrA.timeout = False
            QrA.animate_ptr()

    @staticmethod
    def pending(text = None):
        if text == None:
            return QrA.indx != []
        return text in QrA.payload or text == "".join(QrA.payload)

    @staticmethod
    def clean():
        QrA.isQRplaying = False
        QrA.indx = []
        QrA.payload = []

    @staticmethod
    def stop():
        # call in event handler of the popup close
        QrA.abort = True

class QRCode(lv.cont):
    # max number of bytes to be QR encoded
    MAX_SIZE = const(300)

    def __init__(self, size, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = "txt"
        self.text_prev = "txt_prev"

        # We have a container that parents a label (QR code)
        self.set_auto_realign(True)
        self.align_origo(None, lv.ALIGN.CENTER, 0, 0)
        self.set_layout(lv.LAYOUT.OFF)

        # label which holds the QR code
        self.lbl = lv.label(self)
        self.lbl.set_long_mode(lv.label.LONG.BREAK)
        self.lbl.set_align(lv.label.ALIGN.CENTER)
        self.size = size
        self.max_size = None

        # in case the QR is animatable our container also parents a tip label
        self.cont = lv.cont(self)
        self.lbl_indx = lv.label(self.cont)
        self.lbl_indx.set_text('')
        self.cont.set_fit(lv.FIT.TIGHT)
        self.set_fit(lv.FIT.TIGHT)
        self.isQRbig = False
        self.animation_tip = True

        QrA.init(self.next)
        self.set_event_cb(QrA.qr_cb)

    def is_qr_big(self, message):
        QrA.isQRtoobig = len(message) >= 850
        q = len(message)/QRCode.MAX_SIZE
        if q > 1.0:
            return True
        return False

    def next(self):
        QrA.indx[0] += 1
        if QrA.indx[0] > QrA.indx[1]:
            QrA.indx[0] = 0
        if QrA.isQRplaying == True:
            self.set_text(QrA.payload[QrA.indx[0]])
        else:
            qr = "".join(QrA.payload)
            if self.get_text() != qr:
                self.set_text(qr)

    def set_text(self, text):
        if QrA.pending(text):
            if QrA.isQRplaying:
                self._text = text
            else:
                self._text = "".join(QrA.payload)
        else:
            if self.is_qr_big(text):
                self.isQRbig = True
                n = QrA.average_chunk_size(len(text), QRCode.MAX_SIZE)
                QrA.payload = [text[i:i+n] for i in range(0, len(text), n)]
                QrA.indx = [0, len(QrA.payload)-1]
                if QrA.isQRtoobig:
                    self._text = QrA.payload[QrA.indx[0]]
                    QrA.isQRplaying = True
                else:
                    self._text = text
                QrA.run()
            else:
                self.isQRbig = False
                self.isQRtoobig = False
                self._text = text
                QrA.abort = True

        if text != self.text_prev:
	        print("QR on screen:", QrA.header() + self._text)
        self.text_prev = text

        self.lbl.set_size(self.size, self.size)
        if QrA.isQRplaying:
            if self.max_size:
                self.lbl.set_size(self.max_size, self.max_size)

        qr = qrcode.encode_to_string(QrA.header() + self._text)
        size = int(math.sqrt(len(qr))) # + 4 clear space on every side
        width = self.lbl.get_width()
        scale = round(width/size)
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
        self.lbl.set_style(lv.label.STYLE.MAIN, style)
        self.lbl.set_body_draw(True)
        self.lbl.set_text(qr)
        del qr
        gc.collect()

        # apply the padding of the qr label to the container, otherwise it gets lost
        style2 = lv.style_t()
        style2.body.padding.top = pad
        style2.body.padding.left = pad
        style2.body.padding.right = pad
        style2.body.padding.bottom = pad-fontsize
        self.set_style(lv.label.STYLE.MAIN, style2)

        if self.isQRbig:
            style_tip = lv.style_t()
            lv.style_copy(style_tip, styles["theme"].style.ta.oneline)
            style_tip.text.font = lv.font_roboto_mono_16
            self.lbl_indx.set_style(lv.label.STYLE.MAIN, style_tip)

            if QrA.isQRplaying:
                self.animation_tip = False
            if self.animation_tip:
                tip_text = "Tip: tap to animate"
            else:
                tip_text = "" 
            self.lbl_indx.set_text(tip_text)

        self.lbl.set_width(self.lbl.get_height())
        if not self.isQRbig:
            self.cont.set_fit(lv.FIT.TIGHT)
            self.set_fit(lv.FIT.TIGHT)
        elif not QrA.isQRplaying:
            self.max_size = self.lbl.get_height()
            self.cont.align_origo(self.lbl, lv.ALIGN.OUT_TOP_MID, 0, -35)

    def get_real_text(self):
        return super().get_text()

    def get_text(self):
        return self._text
