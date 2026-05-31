import lvgl as lv
from .alert import Alert
from ..common import add_label


class Progress(Alert):
    """
    Shows progress with a spinner, also can show
    percentage of the progress or checkboxes for parts of QR code
    Use set_progress(float or list) to set progress
    """

    def __init__(self, title, message, button_text="Cancel"):
        super().__init__(title, message, button_text=button_text)
        self.spinner = lv.spinner(self)
        self.spinner.set_anim_params(1000, 200)
        self.spinner.align(lv.ALIGN.CENTER, 0, -150)
        self.message.align_to(self.spinner, lv.ALIGN.OUT_BOTTOM_MID, 0, 120)
        self.progress = add_label("", scr=self, style="title")
        self.progress.align_to(self.message, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        self.progress.set_recolor(True)

    def set_progress(self, val):
        txt = ""
        if isinstance(val, list):
            ok = "#00F100 " + lv.SYMBOL.OK + " # "
            no = "#FF9A00 " + lv.SYMBOL.CLOSE + " # "
            txt = " ".join([ok if e else no for e in val])
        elif val > 0:
            txt = "%d%%" % int(val * 100)
        self.progress.set_text(txt)
