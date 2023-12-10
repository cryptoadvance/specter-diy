import lvgl as lv
from gui.common import add_label, add_button, HOR_RES, format_addr
from gui.decorators import on_release
from gui.screens import QRAlert, Prompt, Alert
from .commands import DELETE, EDIT, MENU


class WalletScreen(QRAlert):
    def __init__(self, wallet, network, idx=None, branch_index=0):
        self.wallet = wallet
        self.network = network
        self.idx = wallet.unused_recv
        addr, gap = wallet.get_address(
            self.idx,
            network=network,
            branch_index=branch_index,
        )
        super().__init__(
            "    " + wallet.name + "  #708092 " + lv.SYMBOL.EDIT,
            format_addr(addr, words=4),
            "bitcoin:" + addr,
            qr_width=350,
        )
        self.title.set_recolor(True)
        self.title.set_click(True)
        self.title.set_event_cb(on_release(self.rename))
        self.policy = add_label(wallet.policy, y=55, style="hint", scr=self)

        style = lv.style_t()
        lv.style_copy(style, self.message.get_style(0))
        style.text.font = lv.font_roboto_mono_22
        self.message.set_style(0, style)

        # index
        self.branch_index = branch_index
        self.note = add_label(
            "%s address #%d" % (self.prefix, self.idx), y=80, style="hint", scr=self
        )
        self.qr.align(self.note, lv.ALIGN.OUT_BOTTOM_MID, 0, 15)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 15)

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
        self.nxt.set_x(HOR_RES - 70)

        self.menubtn = add_button(
            lv.SYMBOL.SETTINGS + " Settings", on_release(self.show_menu), scr=self
        )
        self.menubtn.align(self.close_button, lv.ALIGN.OUT_TOP_MID, 0, -20)

        if idx is not None:
            self.idx = idx
            self.update_address()

    @property
    def prefix(self):
        if self.branch_index == 0:
            return "Receiving"
        elif self.branch_index == 1:
            return "Change"
        return "Branch %d" % self.branch_index    

    def rename(self):
        self.set_value(EDIT)

    def show_menu(self):
        self.set_value(MENU)

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
        self.show_loader(title="Deriving address...")
        if self.idx > 0:
            self.prv.set_state(lv.btn.STATE.REL)
        else:
            self.prv.set_state(lv.btn.STATE.INA)
        addr, gap = self.wallet.get_address(
            self.idx, network=self.network, branch_index=self.branch_index
        )
        note = "%s address #%d" % (self.prefix, self.idx)
        self.note.set_text(note)
        self.message.set_text(format_addr(addr, words=4))
        self.qr.set_text("bitcoin:" + addr)

        if self.idx > gap:
            self.warning.set_text(
                "This address exceeds the gap limit.\n"
                "Your watching wallet may not track balance "
                "received to it!"
            )
        elif self.idx < self.wallet.unused_recv:
            self.warning.set_text(
                "This address may have been used before.\n"
                "Reusing it would diminish your privacy!"
            )
        else:
            self.warning.set_text("")
        self.hide_loader()

# micropython doesn't support mixins :(
def _build_screen(scr, policy, keys):
    scr.policy = add_label("Policy: " + policy, y=75, scr=scr)

    # check if we need slip132 switch
    need_slip132_switch = any(
        k["canonical"] != k["slip132"]
        for k in keys
    )
    if need_slip132_switch:
        lbl = lv.label(scr)
        lbl.set_text("Canonical xpub                     SLIP-132             ")
        lbl.align(scr.policy, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        scr.slip_switch = lv.sw(scr)
        scr.slip_switch.align(lbl, lv.ALIGN.CENTER, 0, 0)
        scr.slip_switch.set_event_cb(on_release(scr.fill_message))
    else:
        scr.slip_switch = None

    scr.page.align(
        scr.policy,
        lv.ALIGN.OUT_BOTTOM_MID,
        0,
        30 + 40*int(need_slip132_switch)
    )
    scr.message.set_recolor(True)
    scr.page.set_height(500)

def _fill_message(keys, is_complex, use_slip132=False):
    msg = ""
    arg = "slip132" if use_slip132 else "canonical"
    for i, k in enumerate(keys):
        alias = "" if not is_complex else " (%s)" % chr(65+i)
        kstr = str(k[arg]).replace("]","]\n")
        if k["mine"]:
            msg += "#7ED321 My key%s: #\n%s\n\n" % (alias, kstr)
        elif k["is_nums"]:
            msg += "#00CAF1 NUMS key%s: #\nNobody knows private key\n\n" % alias
        elif k["is_private"]:
            msg += "#F51E2D Private key%s: #\n%s\n\n" % (alias, kstr)
        else:
            msg += "#F5A623 External key%s:\n# %s\n\n" % (alias, kstr)
    return msg


class ConfirmWalletScreen(Prompt):
    def __init__(self, name, policy, keys, is_complex=True):
        super().__init__('Add wallet "%s"?' % name, "")
        _build_screen(self, policy, keys)
        self.is_complex = is_complex
        self.keys = keys
        self.fill_message()

    @property
    def use_slip132(self):
        return self.slip_switch.get_state() if self.slip_switch is not None else False

    def fill_message(self):
        msg = _fill_message(self.keys, self.is_complex, self.use_slip132)
        self.message.set_text(msg)


class WalletInfoScreen(Alert):
    def __init__(self, name, policy, keys, is_complex=True):
        super().__init__(name, "")
        _build_screen(self, policy, keys)
        self.is_complex = is_complex
        self.keys = keys
        self.fill_message()

    @property
    def use_slip132(self):
        return self.slip_switch.get_state() if self.slip_switch is not None else False

    def fill_message(self):
        msg = _fill_message(self.keys, self.is_complex, self.use_slip132)
        self.message.set_text(msg)
