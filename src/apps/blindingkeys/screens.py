"""Bitcoin-related screens"""
import lvgl as lv
from gui.common import PADDING
from gui.decorators import on_release
from gui.screens.qralert import QRAlert


class BlindingKeysScreen(QRAlert):
    def __init__(
        self,
        xprv,
        xpub,
        prefix=None,
        title="Your blinding key",
        qr_width=None,
        button_text="Close",
    ):
        message = xprv
        if prefix is not None:
            message = prefix + message
        super().__init__(title, message, message, note="\n")
        self.xprv = xprv
        self.prefix = prefix
        self.xpub = xpub

        if prefix is not None:
            lbl = lv.label(self)
            lbl.set_text("Show derivation path")
            lbl.set_pos(2 * PADDING, 600)
            self.prefix_switch = lv.sw(self)
            self.prefix_switch.on(lv.ANIM.OFF)
            self.prefix_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        lbl = lv.label(self)
        lbl.set_text("Show blinding private key")
        lbl.set_pos(2 * PADDING, 650)
        self.prv_switch = lv.sw(self)
        self.prv_switch.on(lv.ANIM.OFF)
        self.prv_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if prefix is not None:
            self.prefix_switch.set_event_cb(on_release(self.toggle_event))
        self.prv_switch.set_event_cb(on_release(self.toggle_event))
        self.toggle_event()

    def toggle_event(self):
        if self.prv_switch.get_state():
            msg = self.xprv
            self.note.set_text("Blinding private key allow your software wallet\nto track your balance.")
        else:
            msg = self.xpub
            self.note.set_text("With blinding public key your software can\nonly generate addresses.")
        if self.prefix is not None and self.prefix_switch.get_state():
            msg = self.prefix + msg
        self.message.set_text(msg)
        self.qr.set_text(msg)
