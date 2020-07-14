"""Bitcoin-related screens"""
import lvgl as lv
from gui.common import PADDING
from gui.decorators import on_release
from gui.screens.qralert import QRAlert

class XPubScreen(QRAlert):
    def __init__(self,
                 xpub,
                 slip132 = None,
                 prefix = None,
                 title="Your master public key", 
                 qr_width=None,
                 button_text="Close"):
        message = xpub
        if slip132 is not None:
            message = slip132
        if prefix is not None:
            message = prefix+message
        super().__init__(title, message, message)
        self.xpub = xpub
        self.prefix = prefix
        self.slip132 = slip132

        if prefix is not None:
            lbl = lv.label(self)
            lbl.set_text("Show derivation path")
            lbl.set_pos(2*PADDING, 580)
            self.prefix_switch = lv.sw(self)
            self.prefix_switch.on(lv.ANIM.OFF)
            self.prefix_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if slip132 is not None:
            lbl = lv.label(self)
            lbl.set_text("Use SLIP-132")
            lbl.set_pos(2*PADDING, 640)
            self.slip_switch = lv.sw(self)
            self.slip_switch.on(lv.ANIM.OFF)
            self.slip_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if prefix is not None:
            self.prefix_switch.set_event_cb(on_release(self.toggle_event))
        if slip132 is not None:
            self.slip_switch.set_event_cb(on_release(self.toggle_event))

    def toggle_event(self):
        msg = self.xpub
        if self.slip132 is not None and self.slip_switch.get_state():
            msg = self.slip132
        if self.prefix is not None and self.prefix_switch.get_state():
            msg = self.prefix+msg
        self.message.set_text(msg)
        self.qr.set_text(msg)
