"""Bitcoin-related screens"""
import lvgl as lv
from ..common import add_label, add_button, HOR_RES, format_addr
from ..decorators import on_release
from .qralert import QRAlert

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
            lbl.set_pos(2*PADDING, 540)
            self.prefix_switch = lv.sw(self)
            self.prefix_switch.on(lv.ANIM.OFF)
            self.prefix_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

        if slip132 is not None:
            lbl = lv.label(self)
            lbl.set_text("Use SLIP-132")
            lbl.set_pos(2*PADDING, 590)
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

class WalletScreen(QRAlert):
    def __init__(self, wallet, network):
        self.wallet = wallet
        self.network = network
        self.idx = wallet.unused_recv
        addr, gap = wallet.get_address(self.idx, network=network)
        super().__init__(wallet.name, format_addr(addr, words=4), "bitcoin:"+addr)

        style = lv.style_t()
        lv.style_copy(style, self.message.get_style(0))
        style.text.font = lv.font_roboto_mono_22
        self.message.set_style(0, style)

        # index
        self.note = add_label("Receiving address #%d" % self.idx, y=55, style="hint", scr=self)
        self.qr.align(self.note, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

        # warning label for address gap limit
        self.warning = add_label("", scr=self)
        self.warning.align(self.message, lv.ALIGN.OUT_BOTTOM_MID, 0, 15)
        style = lv.style_t()
        lv.style_copy(style, self.note.get_style(0))
        style.text.color = lv.color_hex(0xFF9A00)
        self.warning.set_style(0, style)
        
        # delbtn = add_button("Delete wallet", on_release(cb_del), y=610)
        self.prv = add_button(lv.SYMBOL.LEFT, on_release(self.prev), scr=self)
        self.nxt = add_button(lv.SYMBOL.RIGHT, on_release(self.next), scr=self)
        if self.idx <= 0:
            self.prv.set_state(lv.btn.STATE.INA)
        self.prv.set_width(70)
        self.prv.align(self.qr, lv.ALIGN.OUT_LEFT_MID, -20, 0)
        self.prv.set_x(0)
        self.nxt.set_width(70)
        self.nxt.align(self.qr, lv.ALIGN.OUT_RIGHT_MID, 20, 0)
        self.nxt.set_x(HOR_RES-70)

    def next(self):
        self.idx += 1
        self.update_address()

    def prev(self):
        if self.idx == 0:
            return
        self.idx -= 1
        self.update_address()

    def update_address(self):
        if self.idx > 0:
            self.prv.set_state(lv.btn.STATE.REL)
        else:
            self.prv.set_state(lv.btn.STATE.INA)
        addr, gap = self.wallet.get_address(self.idx, network=self.network)
        note = "Receiving address #%d" % (self.idx)
        self.note.set_text(note)
        self.message.set_text(format_addr(addr, words=4))
        self.qr.set_text("bitcoin:"+addr)

        if self.idx > gap:
            self.warning.set_text("This address exceeds the gap limit.\n"
                            "Your watching wallet may not track balance "
                            "received to it!")
        elif self.idx < self.wallet.unused_recv:
            self.warning.set_text("This address may have been used before.\n"
                           "Reusing it would diminish your privacy!")
        else:
            self.warning.set_text("")
