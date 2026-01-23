"""Bitcoin-related screens"""
import lvgl as lv
from gui.common import PADDING, styles, add_button_pair
from gui.decorators import on_release
from gui.screens.qralert import QRAlert


class XPubScreen(QRAlert):
    CREATE_WALLET = 0x01 # command to create a wallet
    def __init__(
        self,
        xpub,
        slip132=None,
        prefix=None,
        title="Your master public key",
        qr_width=None,
        button_text="Close"
    ):
        message = xpub
        if slip132 is not None:
            message = slip132
        if prefix is not None:
            message = prefix + message
        super().__init__(title, message, message, qr_width=320)
        self.message.add_style(styles["small"], lv.PART.MAIN)
        self.xpub = xpub
        self.prefix = prefix
        self.slip132 = slip132

        if prefix is not None:
            lbl = lv.label(self)
            lbl.set_text("Show derivation path")
            lbl.set_pos(2 * PADDING, 500)
            self.prefix_switch = lv.switch(self)
            self.prefix_switch.add_state(lv.STATE.CHECKED)
            self.prefix_switch.align_to(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if slip132 is not None:
            lbl = lv.label(self)
            lbl.set_text("Use SLIP-132")
            lbl.set_pos(2 * PADDING, 560)
            self.slip_switch = lv.switch(self)
            self.slip_switch.add_state(lv.STATE.CHECKED)
            self.slip_switch.align_to(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if prefix is not None:
            self.prefix_switch.add_event_cb(on_release(self.toggle_event), lv.EVENT.ALL, None)
        if slip132 is not None:
            self.slip_switch.add_event_cb(on_release(self.toggle_event), lv.EVENT.ALL, None)
        add_button_pair(
            lv.SYMBOL.SAVE + " Save to SD", on_release(self.save_to_sd),
            lv.SYMBOL.PLUS + " Create wallet", on_release(self.create_wallet),
            y=610, scr=self,
        )

    def save_to_sd(self):
        """
        Returns the xpub in the form we want to save
        (canonical / slip39, with or without derivation)
        """
        self.set_value(self.message.get_text())

    def create_wallet(self):
        self.set_value(self.CREATE_WALLET)

    def toggle_event(self):
        msg = self.xpub
        if self.slip132 is not None and self.slip_switch.has_state(lv.STATE.CHECKED):
            msg = self.slip132
        if self.prefix is not None and self.prefix_switch.has_state(lv.STATE.CHECKED):
            msg = self.prefix + msg
        self.message.set_text(msg)
        self.qr.set_text(msg)
