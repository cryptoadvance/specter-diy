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

        enable_inputs = len([k for k in meta["inputs"] if k["sighash"] != "ALL"]) > 0

        lbl = add_label("Show input details                         ", scr=self)
        lbl.align(obj, lv.ALIGN.CENTER, 0, 0)
        self.details_sw = lv.sw(self)
        self.details_sw.align(obj, lv.ALIGN.CENTER, 100, 0)
        self.details_sw.set_event_cb(on_release(self.toggle_details))
        if enable_inputs:
            self.details_sw.toggle(True)

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

        self.input_label = add_label("", scr=self.page)
        self.inputs_text = "%d inputs" % len(meta["inputs"])
        for i, inp in enumerate(meta["inputs"]):
            self.inputs_text += "\n\nInput %d: %.8f BTC from \"%s\"%s" % (i, inp["value"]/1e8, inp["label"], "" if inp["sighash"] == "ALL" else ("\n( SIGHASH %s )" % inp["sighash"]))
        self.inputs_text += "\n___________________________________________"
        self.input_label.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        obj = self.input_label

        self.objs = []
        num_change_outputs = 0
        for out in meta["outputs"]:
            # first only show destination addresses
            if out["change"]:
                num_change_outputs += 1
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
        self.objs.append(fee)

        obj = fee

        if num_change_outputs > 0:
            obj = add_label("Change outputs:", scr=self.page, style="title")
            obj.align(fee, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            self.objs.append(obj)
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
            self.warning.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
            self.objs.append(self.warning)

        self.toggle_details()

    def toggle_details(self):
        if self.details_sw.get_state():
            self.input_label.set_text(self.inputs_text)
            for obj in self.objs:
                obj.set_y(obj.get_y()+self.input_label.get_height()+30)
        else:
            h = self.input_label.get_height()
            self.input_label.set_text("")
            for obj in self.objs:
                obj.set_y(obj.get_y()-h-30)

    def show_output(self, out, obj):
        # show output
        lbl = add_label(
            "%.8f BTC to" % (out["value"] / 1e8), style="title", scr=self.page
        )
        lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 30)
        self.objs.append(lbl)
        obj = lbl
        # if there is no label but it's a change with warning
        if "label" not in out and out["change"]:
            out["label"] = "Change"
        if "label" in out:
            lbl = add_label(out["label"], style="title", scr=self.page)
            lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            self.objs.append(lbl)
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
        self.objs.append(addr)
        obj = addr
        if "warning" in out:
            text = "WARNING! %s" % out["warning"]
            warning = add_label(text, scr=self.page)
            warning.set_style(0, self.style_warning)
            warning.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
            self.objs.append(warning)
            obj = warning
        return obj