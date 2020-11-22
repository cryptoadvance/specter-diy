import lvgl as lv

class Modal(lv.obj):
    """mbox with semi-transparent background"""
    def __init__(self, parent, *args, **kwargs):
        # Create a base object for the modal background
        super().__init__(parent, *args, **kwargs)

        # Create a full-screen background
        modal_style = lv.style_t()
        lv.style_copy(modal_style, lv.style_plain_color)
        # Set the background's style
        modal_style.body.main_color = modal_style.body.grad_color = lv.color_make(0,0,0)
        modal_style.body.opa = lv.OPA._50

        self.set_style(modal_style)
        self.set_pos(0, 0)
        self.set_size(parent.get_width(), parent.get_height())

        self.mbox = lv.mbox(self)
        self.mbox.set_width(400)
        self.mbox.align(None, lv.ALIGN.IN_TOP_MID, 0, 200)

    def set_text(self, text):
        self.mbox.set_text(text)
