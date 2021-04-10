import lvgl as lv
from .prompt import Prompt
from ..common import add_label, format_addr
from ..decorators import on_release


class TransactionScreen(Prompt):
    def __init__(self, title, meta):
        send_amount = sum(
            [out["value"] for out in meta["outputs"] if not out["change"]]
        )
        super().__init__(title, "")

        obj = self.message # for alignments

        enable_inputs = len([k for k in meta["inputs"] if k.get("sighash", "ALL") != "ALL"]) > 0

        lbl = add_label("Show detailed information                      ", scr=self)
        lbl.align(obj, lv.ALIGN.CENTER, 0, 0)
        self.details_sw = lv.sw(self)
        self.details_sw.align(obj, lv.ALIGN.CENTER, 130, 0)
        self.details_sw.set_event_cb(on_release(self.toggle_details))
        if enable_inputs:
            self.details_sw.on(lv.ANIM.OFF)

        # change page a bit
        self.page.set_pos(0, lbl.get_y()+20)
        self.page.set_size(480, 800-130-lbl.get_y())

        self.page2 = lv.page(self)
        self.page2.set_pos(self.page.get_x(), self.page.get_y())
        self.page2.set_size(self.page.get_width(), self.page.get_height())

        # define styles
        style = lv.style_t()
        lv.style_copy(style, self.message.get_style(0))
        style.text.font = lv.font_roboto_mono_28

        style_primary = lv.style_t()
        lv.style_copy(style_primary, self.message.get_style(0))
        style_primary.text.font = lv.font_roboto_mono_22

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

        num_change_outputs = 0
        for out in meta["outputs"]:
            # first only show destination addresses
            if out["change"]:
                num_change_outputs += 1
                continue
            obj = self.show_output(out, obj)

        if send_amount > 0:
            fee_percent = meta["fee"] * 100 / send_amount
            fee_txt = "%d satoshi (%.2f%%)" % (meta["fee"], fee_percent)
        # back to wallet
        else:
            fee_txt = "%d satoshi" % (meta["fee"])
        fee = add_label("Fee: " + fee_txt, scr=self.page)
        fee.set_style(0, style)
        fee.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        obj = fee

        # warning label for address gap limit
        if "warnings" in meta and len(meta["warnings"]) > 0:
            text = "WARNING!\n" + "\n".join(meta["warnings"])
            self.warning = add_label(text, scr=self.page)
            self.warning.set_style(0, style_warning)
            self.warning.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        lbl = add_label("%d INPUTS" % len(meta["inputs"]), scr=self.page2)
        lbl.align(self.page2, lv.ALIGN.IN_TOP_MID, 0, 30)
        obj = lbl
        for i, inp in enumerate(meta["inputs"]):
            idxlbl = lv.label(self.page2)
            idxlbl.set_text("%d:" % i)
            idxlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            idxlbl.set_x(30)
            lbl = lv.label(self.page2)
            lbl.set_long_mode(lv.label.LONG.BREAK)
            lbl.set_width(380)
            lbl.set_text("%.8f %s from %s" % (inp["value"]/1e8, inp["asset"] or "???", inp["label"]))
            lbl.align(idxlbl, lv.ALIGN.IN_TOP_LEFT, 0, 0)
            lbl.set_x(60)

            if inp["sighash"] != "ALL":
                shlbl = lv.label(self.page2)
                shlbl.set_long_mode(lv.label.LONG.BREAK)
                shlbl.set_width(380)
                shlbl.set_text(inp["sighash"])
                shlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
                shlbl.set_x(60)
                shlbl.set_style(0, style_warning)
                lbl = shlbl
            obj = lbl

        lbl = add_label("%d OUTPUTS" % len(meta["outputs"]), scr=self.page2)
        lbl.align(self.page2, lv.ALIGN.IN_TOP_MID, 0, 0)
        lbl.set_y(obj.get_y() + obj.get_height() + 30)
        for i, out in enumerate(meta["outputs"]):
            idxlbl = lv.label(self.page2)
            idxlbl.set_text("%d:" % i)
            idxlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            idxlbl.set_x(30)
            lbl = lv.label(self.page2)
            lbl.set_long_mode(lv.label.LONG.BREAK)
            lbl.set_width(380)
            lbl.set_text("%.8f %s to %s" % (out["value"]/1e8, out["asset"] or "???", out.get("label", "")))
            lbl.align(idxlbl, lv.ALIGN.IN_TOP_LEFT, 0, 0)
            lbl.set_x(60)

            addrlbl = lv.label(self.page2)
            addrlbl.set_long_mode(lv.label.LONG.BREAK)
            addrlbl.set_width(380)
            addrlbl.set_text(format_addr(out["address"], words=4))
            addrlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
            addrlbl.set_x(60)
            if "label" in out:
                addrlbl.set_style(0, style_secondary)
            else:
                addrlbl.set_style(0, style_primary)
            lbl = addrlbl

        idxlbl = lv.label(self.page2)
        idxlbl.set_text("Fee:  " + fee_txt)
        idxlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        idxlbl.set_x(30)

        self.toggle_details()

    def toggle_details(self):
        if self.details_sw.get_state():
            self.page2.set_hidden(False)
            self.page.set_hidden(True)
        else:
            self.page2.set_hidden(True)
            self.page.set_hidden(False)

    def show_output(self, out, obj):
        # show output
        lbl = add_label(
            "%.8f %s to" % (out["value"] / 1e8, out["asset"] or "???"), style="title", scr=self.page
        )
        lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        obj = lbl
        # if there is no label but it's a change with warning
        if "label" not in out and out["change"]:
            out["label"] = "Change"
        if "label" in out:
            lbl = add_label(out["label"], style="title", scr=self.page)
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