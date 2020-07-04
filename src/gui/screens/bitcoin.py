"""Bitcoin-related screens"""
import lvgl as lv
from ..common import add_label, add_button, HOR_RES, format_addr, PADDING
from ..decorators import on_release
from .qralert import QRAlert
from ..commands import DELETE, EDIT
from .prompt import Prompt

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

class WalletScreen(QRAlert):
    def __init__(self, wallet, network, idx=None, change=False):
        self.wallet = wallet
        self.network = network
        self.idx = wallet.unused_recv
        addr, gap = wallet.get_address(self.idx, network=network, change=change)
        super().__init__("    "+wallet.name+"  #708092 "+lv.SYMBOL.EDIT, format_addr(addr, words=4), "bitcoin:"+addr)
        self.title.set_recolor(True)
        self.title.set_click(True)
        self.title.set_event_cb(on_release(self.rename))
        self.policy = add_label(wallet.policy, y=55, style="hint", scr=self)

        style = lv.style_t()
        lv.style_copy(style, self.message.get_style(0))
        style.text.font = lv.font_roboto_mono_22
        self.message.set_style(0, style)

        # index
        self.change = change
        prefix = "Change" if change else "Receiving"
        self.note = add_label("%s address #%d" % (prefix, self.idx), y=80, style="hint", scr=self)
        self.qr.align(self.note, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

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

        self.delbtn = add_button(lv.SYMBOL.TRASH+" Delete wallet", on_release(self.delwallet), scr=self)
        self.delbtn.align(self.close_button, lv.ALIGN.OUT_TOP_MID, 0, -20)
        style = lv.style_t()
        lv.style_copy(style, self.delbtn.get_style(lv.btn.STYLE.REL))
        style.body.main_color = lv.color_hex(0x951E2D)
        style.body.grad_color = lv.color_hex(0x951E2D)
        self.delbtn.set_style(lv.btn.STYLE.REL, style)

        if idx is not None:
            self.idx = idx
            self.update_address()

    def rename(self):
        self.set_value(EDIT)

    def delwallet(self):
        # TODO: ugly, 255 should go to some constant
        self.set_value(DELETE)

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
        addr, gap = self.wallet.get_address(self.idx, network=self.network, change=self.change)
        prefix = "Change" if self.change else "Receiving"
        note = "%s address #%d" % (prefix, self.idx)
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

class ConfirmWalletScreen(Prompt):
    def __init__(self, name, policy, keys):
        super().__init__("Add wallet \"%s\"?" % name, "")
        self.policy = add_label("Policy: " + policy, y=75, scr=self)
        self.page.align(self.policy, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        self.message.set_recolor(True)
        self.page.set_height(550)
        msg = ""
        for k in keys:
            if k["mine"]:
                msg += "#7ED321 My key: # %s\n\n" % k["key"]
            else:
                msg += "#F5A623 External key: # %s\n\n" % k["key"]
        self.message.set_text(msg)
