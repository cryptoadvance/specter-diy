import lvgl as lv

class Modal(lv.obj):
    """msgbox with semi-transparent background"""
    def __init__(self, parent, *args, **kwargs):
        # Create a base object for the modal background
        super().__init__(parent, *args, **kwargs)

        # LVGL 9.x: Create style for semi-transparent background
        modal_style = lv.style_t()
        modal_style.init()
        modal_style.set_bg_color(lv.color_make(0, 0, 0))
        modal_style.set_bg_opa(lv.OPA._50)

        self.add_style(modal_style, lv.PART.MAIN)
        self.set_pos(0, 0)
        self.set_size(parent.get_width(), parent.get_height())

        # LVGL 9.x: msgbox API changed - create simple container with label
        self.mbox = lv.obj(self)
        self.mbox.set_width(400)
        self.mbox.set_height(lv.SIZE_CONTENT)
        self.mbox.align(lv.ALIGN.TOP_MID, 0, 200)

        self.mbox_label = lv.label(self.mbox)
        self.mbox_label.set_width(380)
        self.mbox_label.center()

    def set_text(self, text):
        self.mbox_label.set_text(text)
