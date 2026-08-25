import lvgl as lv

class Modal(lv.obj):
    """mbox with semi-transparent background"""
    def __init__(self, parent, *args, **kwargs):
        # Create a base object for the modal background
        super().__init__(parent, *args, **kwargs)

        # Create a full-screen background
        self.modal_style = lv.style_t()
        self.modal_style.init()
        self.modal_style.set_bg_color(lv.color_hex(0x000000))
        self.modal_style.set_bg_opa(lv.OPA._50)
        self.modal_style.set_border_width(0)
        self.modal_style.set_outline_width(0)
        self.modal_style.set_shadow_width(0)
        self.modal_style.set_radius(0)
        self.modal_style.set_pad_all(0)
        self.add_style(self.modal_style, 0)
        self.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.set_pos(0, 0)
        self.set_size(parent.get_width(), parent.get_height())

        self.mbox_style = lv.style_t()
        self.mbox_style.init()
        self.mbox_style.set_bg_opa(255)
        self.mbox_style.set_border_width(0)
        self.mbox_style.set_outline_width(0)
        self.mbox_style.set_shadow_width(0)
        self.mbox_style.set_pad_all(20)
        self.mbox_style.set_radius(8)

        self.mbox = lv.obj(self)
        self.mbox.set_width(400)
        self.mbox.add_style(self.mbox_style, 0)
        self.mbox.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.mbox.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.mbox.align(lv.ALIGN.TOP_MID, 0, 200)
        self.label = lv.label(self.mbox)
        self.label.set_width(360)
        self.label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.label.center()

    def set_text(self, text):
        self.label.set_text(text)
        self.mbox.set_height(self.label.get_height() + 40)
        self.label.center()
