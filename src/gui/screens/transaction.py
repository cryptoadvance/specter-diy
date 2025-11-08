import lvgl as lv
import platform
from helpers import conv_time
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
        style_warning.text.font = lv.font_roboto_22

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
            fee.set_style(0, style)
            fee.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

            obj = fee

        if "warnings" in meta and len(meta["warnings"]) > 0:
            text = "WARNING!\n" + "\n".join(meta["warnings"])
            self.warning = add_label(text, scr=self.page)
            self.warning.set_style(0, style_warning)
            self.warning.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)

        verlbl = lv.label(self.page2)
        verlbl.set_text("Transaction Version: %d" % meta["tx_version"])
        verlbl.align(self.page2, lv.ALIGN.IN_TOP_LEFT, 0, 30)
        verlbl.set_x(30)
        locktime = meta["locktime"]
        if locktime <= 499999999:
            ltlbl = lv.label(self.page2)
            ltlbl.set_text("Locktime: %d (Block Height)" % locktime)
            ltlbl.align(verlbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
            obj = ltlbl
        else:
            ltlbl = lv.label(self.page2)
            ltlbl.set_text("Locktime: %d (Timestamp)" % locktime)
            ltlbl.align(verlbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
            mp_time = conv_time(locktime)
            ltdatelbl = lv.label(self.page2)
            ltdatelbl.set_text("%04d-%02d-%02d %02d:%02d:%02d UTC" % mp_time[:6])
            ltdatelbl.align(ltlbl, lv.ALIGN.OUT_BOTTOM_LEFT, 15, 5)
            obj = ltdatelbl
        meta_inputs_len = len(meta["inputs"])
        lbl = add_label("%d %s" % (meta_inputs_len, "INPUT" if meta_inputs_len == 1 else "INPUTS"), scr=self.page2)
        lbl.align(self.page2, lv.ALIGN.IN_TOP_MID, 0, 30)
        lbl.set_y(obj.get_y() + obj.get_height() + 30)
        obj = lbl
        for i, inp in enumerate(meta["inputs"]):
            idxlbl = lv.label(self.page2)
            idxlbl.set_text("%d:" % i)
            idxlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            idxlbl.set_x(30)
            lbl = lv.label(self.page2)
            lbl.set_long_mode(lv.label.LONG.BREAK)
            lbl.set_width(380)
            valuetxt = "???" if inp["value"] == -1 else "%.8f" % (inp["value"]/1e8)
            lbl.set_text("%s %s from %s" % (valuetxt, inp.get("asset", self.default_asset), inp.get("label", "Unknown wallet")))
            lbl.align(idxlbl, lv.ALIGN.IN_TOP_LEFT, 0, 0)
            lbl.set_x(60)

            if inp.get("sighash", ""):
                shlbl = lv.label(self.page2)
                shlbl.set_long_mode(lv.label.LONG.BREAK)
                shlbl.set_width(380)
                shlbl.set_text(inp.get("sighash", ""))
                shlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
                shlbl.set_x(60)
                shlbl.set_style(0, style_warning)
                lbl = shlbl
            obj = lbl

        meta_outputs_len = len(meta["outputs"])
        lbl = add_label("%d %s" % (len(meta["outputs"]), "OUTPUT" if meta_outputs_len == 1 else "OUTPUTS"), scr=self.page2)
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
            valuetxt = "???" if out["value"] == -1 else "%.8f" % (out["value"]/1e8)
            lbl.set_text("%s %s to %s" % (valuetxt, out.get("asset", self.default_asset), out.get("label", "")))
            lbl.align(idxlbl, lv.ALIGN.IN_TOP_LEFT, 0, 0)
            lbl.set_x(60)

            addrlbl = lv.label(self.page2)
            addrlbl.set_long_mode(lv.label.LONG.BREAK)
            addrlbl.set_width(380)
            addrlbl.set_text(format_addr(out["address"], words=4))
            addrlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
            addrlbl.set_x(60)
            if out.get("label", ""):
                addrlbl.set_style(0, style_secondary)
            else:
                addrlbl.set_style(0, style_primary)
            lbl = addrlbl
            if "warning" in out:
                text = out["warning"]
                warning = add_label(text, scr=self.page2)
                warning.set_align(lv.label.ALIGN.LEFT)
                warning.set_width(380)
                warning.set_style(0, self.style_warning)
                warning.align(addrlbl, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 10)
                warning.set_x(60)
                lbl = warning

        if meta.get("fee"):
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
        valuetxt = "???" if out["value"] == -1 else "%.8f" % (out["value"]/1e8)
        lbl = add_label(
            "%s %s to" % (valuetxt, out.get("asset", self.default_asset)), style="title", scr=self.page
        )
        lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        obj = lbl
        if out.get("label", ""):
            lbl = add_label(out["label"], style="title", scr=self.page)
            lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            obj = lbl
        if out.get("label", ""):
            txt = format_addr(out["address"], words=4)
        else:
            txt = format_addr(out["address"])
        addr = add_label(txt, scr=self.page)
        if out.get("label", ""):
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