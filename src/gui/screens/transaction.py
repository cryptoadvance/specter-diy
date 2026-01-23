import lvgl as lv
from .prompt import Prompt
from ..common import add_label, format_addr
from ..decorators import on_release


class TransactionScreen(Prompt):
    def __init__(self, title, meta):
        self.default_asset = meta.get("default_asset", "BTC")
        send_amount = sum(
            [out["value"] for out in meta["outputs"] if not out["change"]]
        )
        super().__init__(title, "")

        obj = self.message # for alignments

        enable_inputs = len([k for k in meta["inputs"] if k.get("sighash", "")]) > 0
        # if there is at least one unknown value (liquid)
        enable_inputs = enable_inputs or (-1 in [out["value"] for out in meta["outputs"]])
        enable_inputs = enable_inputs or meta.get("issuance", False) or meta.get("reissuance", False)

        lbl = add_label("Show detailed information                      ", scr=self)
        lbl.align_to(obj, lv.ALIGN.CENTER, 0, 0)
        self.details_sw = lv.switch(self)
        self.details_sw.align_to(obj, lv.ALIGN.CENTER, 130, 0)
        self.details_sw.add_event_cb(on_release(self.toggle_details), lv.EVENT.ALL, None)
        if enable_inputs:
            self.details_sw.add_state(lv.STATE.CHECKED)

        # change page a bit
        self.page.set_pos(0, lbl.get_y()+20)
        self.page.set_size(480, 800-130-lbl.get_y())

        # LVGL 9.x: lv.page replaced with scrollable lv.obj
        self.page2 = lv.obj(self)
        self.page2.set_pos(self.page.get_x(), self.page.get_y())
        self.page2.set_size(self.page.get_width(), self.page.get_height())

        # LVGL 9.x: define styles
        style = lv.style_t()
        style.init()
        style.set_text_font(lv.font_montserrat_28)

        style_primary = lv.style_t()
        style_primary.init()
        style_primary.set_text_font(lv.font_montserrat_22)

        style_secondary = lv.style_t()
        style_secondary.init()
        style_secondary.set_text_color(lv.color_hex(0x999999))
        style_secondary.set_text_font(lv.font_montserrat_22)

        style_warning = lv.style_t()
        style_warning.init()
        style_warning.set_text_color(lv.color_hex(0xFF9A00))
        style_warning.set_text_font(lv.font_montserrat_22)

        self.style = style
        self.style_secondary = style_secondary
        self.style_warning = style_warning

        num_change_outputs = 0
        for out in meta["outputs"]:
            # first only show destination addresses
            if out["change"] and not out.get("warning", ""):
                num_change_outputs += 1
                continue
            obj = self.show_output(out, obj)

        if meta.get("fee"):
            if send_amount > 0:
                fee_percent = meta["fee"] * 100 / send_amount
                fee_txt = "%d satoshi (%.2f%%)" % (meta["fee"], fee_percent)
            # back to wallet
            else:
                fee_txt = "%d satoshi" % (meta["fee"])
            fee = add_label("Fee: " + fee_txt, scr=self.page)
            fee.add_style(style, lv.PART.MAIN)
            fee.align_to(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

            obj = fee

        if "warnings" in meta and len(meta["warnings"]) > 0:
            text = "WARNING!\n" + "\n".join(meta["warnings"])
            self.warning = add_label(text, scr=self.page)
            self.warning.add_style(style_warning, lv.PART.MAIN)
            self.warning.align_to(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        lbl = add_label("%d INPUTS" % len(meta["inputs"]), scr=self.page2)
        lbl.align(lv.ALIGN.TOP_MID, 0, 30)
        obj = lbl
        for i, inp in enumerate(meta["inputs"]):
            idxlbl = lv.label(self.page2)
            idxlbl.set_text("%d:" % i)
            idxlbl.align_to(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            idxlbl.set_x(30)
            lbl = lv.label(self.page2)
            lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
            lbl.set_width(380)
            valuetxt = "???" if inp["value"] == -1 else "%.8f" % (inp["value"]/1e8)
            lbl.set_text("%s %s from %s" % (valuetxt, inp.get("asset", self.default_asset), inp.get("label", "Unknown wallet")))
            lbl.align_to(idxlbl, lv.ALIGN.TOP_LEFT, 0, 0)
            lbl.set_x(60)

            if inp.get("sighash", ""):
                shlbl = lv.label(self.page2)
                shlbl.set_long_mode(lv.label.LONG_MODE.WRAP)
                shlbl.set_width(380)
                shlbl.set_text(inp.get("sighash", ""))
                shlbl.align_to(lbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
                shlbl.set_x(60)
                shlbl.add_style(style_warning, lv.PART.MAIN)
                lbl = shlbl
            obj = lbl

        lbl = add_label("%d OUTPUTS" % len(meta["outputs"]), scr=self.page2)
        lbl.align(lv.ALIGN.TOP_MID, 0, 0)
        lbl.set_y(obj.get_y() + obj.get_height() + 30)
        for i, out in enumerate(meta["outputs"]):
            idxlbl = lv.label(self.page2)
            idxlbl.set_text("%d:" % i)
            idxlbl.align_to(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            idxlbl.set_x(30)
            lbl = lv.label(self.page2)
            lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
            lbl.set_width(380)
            valuetxt = "???" if out["value"] == -1 else "%.8f" % (out["value"]/1e8)
            lbl.set_text("%s %s to %s" % (valuetxt, out.get("asset", self.default_asset), out.get("label", "")))
            lbl.align_to(idxlbl, lv.ALIGN.TOP_LEFT, 0, 0)
            lbl.set_x(60)

            addrlbl = lv.label(self.page2)
            addrlbl.set_long_mode(lv.label.LONG_MODE.WRAP)
            addrlbl.set_width(380)
            addrlbl.set_text(format_addr(out["address"], words=4))
            addrlbl.align_to(lbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
            addrlbl.set_x(60)
            if out.get("label", ""):
                addrlbl.add_style(style_secondary, lv.PART.MAIN)
            else:
                addrlbl.add_style(style_primary, lv.PART.MAIN)
            lbl = addrlbl
            if "warning" in out:
                text = out["warning"]
                warning = add_label(text, scr=self.page2)
                warning.set_style_text_align(lv.TEXT_ALIGN.LEFT, 0)
                warning.set_width(380)
                warning.add_style(self.style_warning, lv.PART.MAIN)
                warning.align_to(addrlbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 10)
                warning.set_x(60)
                lbl = warning

        if meta.get("fee"):
            idxlbl = lv.label(self.page2)
            idxlbl.set_text("Fee:  " + fee_txt)
            idxlbl.align_to(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            idxlbl.set_x(30)

        self.toggle_details()

    def toggle_details(self):
        if self.details_sw.has_state(lv.STATE.CHECKED):
            self.page2.remove_flag(lv.obj.FLAG.HIDDEN)
            self.page.add_flag(lv.obj.FLAG.HIDDEN)
        else:
            self.page2.add_flag(lv.obj.FLAG.HIDDEN)
            self.page.remove_flag(lv.obj.FLAG.HIDDEN)

    def show_output(self, out, obj):
        # show output
        valuetxt = "???" if out["value"] == -1 else "%.8f" % (out["value"]/1e8)
        lbl = add_label(
            "%s %s to" % (valuetxt, out.get("asset", self.default_asset)), style="title", scr=self.page
        )
        lbl.align_to(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        obj = lbl
        if out.get("label", ""):
            lbl = add_label(out["label"], style="title", scr=self.page)
            lbl.align_to(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            obj = lbl
        if out.get("label", ""):
            txt = format_addr(out["address"], words=4)
        else:
            txt = format_addr(out["address"])
        addr = add_label(txt, scr=self.page)
        if out.get("label", ""):
            addr.add_style(self.style_secondary, lv.PART.MAIN)
        else:
            addr.add_style(self.style, lv.PART.MAIN)
        addr.align_to(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        obj = addr
        if "warning" in out:
            text = "WARNING! %s" % out["warning"]
            warning = add_label(text, scr=self.page)
            warning.add_style(self.style_warning, lv.PART.MAIN)
            warning.align_to(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            obj = warning
        return obj