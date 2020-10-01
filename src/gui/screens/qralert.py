import lvgl as lv
from .alert import Alert
from ..common import add_qrcode


class QRAlert(Alert):
    def __init__(
        self,
        title="QR Alert!",
        message="Something happened",
        qr_message=None,
        qr_width=None,
        button_text="Close",
        note=None,
    ):
        if qr_message is None:
            qr_message = message
        super().__init__(title, message, button_text, note=note)
        self.qr = add_qrcode(qr_message, scr=self, width=qr_width)
        self.qr.align(self.page, lv.ALIGN.IN_TOP_MID, 0, 20)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
