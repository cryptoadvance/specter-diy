import lvgl as lv
from .prompt import Prompt
from ..common import add_label, format_addr


class TransactionScreen(Prompt):
    def __init__(self, title, meta):
        send_amount = sum(
            [out["value"] for out in meta["outputs"] if not out["change"]]
        )
        super().__init__(title, "verify transaction and confirm")

        style = lv.style_t()
        lv.style_copy(style, self.message.get_style(0))
        style.text.font = lv.font_roboto_mono_28

        style_secondary = lv.style_t()
        lv.style_copy(style_secondary, self.message.get_style(0))
        style_secondary.text.color = lv.color_hex(0x999999)
        style_secondary.text.font = lv.font_roboto_mono_22

        style_warning = lv.style_t()
        lv.style_copy(style_warning, self.message.get_style(0))
        style_warning.text.color = lv.color_hex(0xFF9A00)

        self.style = style
        self.style_secondary = style_secondary
        self.style_warning = style_warning

        obj = self.message
        for out in meta["outputs"]:
            # first only show destination addresses
            if out["change"]:
                continue
            obj = self.show_output(out, obj)

        if send_amount > 0:
            fee_percent = meta["fee"] * 100 / send_amount
            fee = add_label(
                "Fee: %d satoshi (%.2f%%)" % (meta["fee"], fee_percent), scr=self.page
            )
        # back to wallet
        else:
            fee = add_label("Fee: %d satoshi" % (meta["fee"]), scr=self.page)
        fee.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        obj = add_label("Change outputs", scr=self.page)
        obj.align(fee, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        for out in meta["outputs"]:
            # now show change
            if not out["change"]:
                continue
            obj = self.show_output(out, obj)

        # warning label for address gap limit
        if "warnings" in meta and len(meta["warnings"]) > 0:
            text = "WARNING!\n" + "\n".join(meta["warnings"])
            self.warning = add_label(text, scr=self.page)
            self.warning.set_style(0, style_warning)
            self.warning.align(fee, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

    def show_output(self, out, obj):
        # show output
        lbl = add_label(
            "%.8f BTC to" % (out["value"] / 1e8), style="title", scr=self.page
        )
        lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        obj = lbl
        # if there is no label but it's a change with warning
        if "label" not in out and out["change"]:
            out["label"] = "Change"
        if "label" in out:
            lbl = add_label("wallet "+out["label"], style="title", scr=self.page)
            lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            obj = lbl
        if "label" in out:
            txt = format_addr(out["address"], words=4)
        else:
            txt = format_addr(out["address"])
        addr = add_label(txt, scr=self.page)
        if "label" in out:
            addr.set_style(0, self.style_secondary)
        else:
            addr.set_style(0, self.style)
        addr.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        obj = addr
        if "warning" in out:
            text = "WARNING! %s" % out["warning"]
            warning = add_label(text, scr=self.page)
            warning.set_style(0, self.style_warning)
            warning.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            obj = warning
        return obj