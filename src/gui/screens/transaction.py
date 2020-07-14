import lvgl as lv
from .prompt import Prompt
from ..common import add_label, format_addr

class TransactionScreen(Prompt):
    def __init__(self, wallet_name, meta):
        send_amount = sum([out["value"] for out in meta["outputs"] if not out["change"]])
        send_amount += meta["fee"]
        send_btc = send_amount/1e8
        title = "Spending %.8f BTC\nfrom wallet \"%s\"" % (
                        send_btc, wallet_name
                )
        super().__init__(title, "verify transaction and confirm")

        style = lv.style_t()
        lv.style_copy(style, self.message.get_style(0))
        style.text.font = lv.font_roboto_mono_28

        obj = self.message
        for out in meta["outputs"]:
            if not out["change"]:
                lbl = add_label("%.8f BTC to" % (out["value"]/1e8), 
                                style="title", scr=self)
                lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
                addr = add_label(format_addr(out["address"]), scr=self)
                addr.set_style(0, style)
                addr.align(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
                obj = addr

        fee_percent = meta["fee"]*100/(send_amount-meta["fee"])
        fee = add_label("Fee: %d satoshi (%.2f%%)" % (
                    meta["fee"], fee_percent), scr=self)
        fee.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

        # warning label for address gap limit
        if "warnings" in meta and len(meta["warnings"]) > 0:
            text = "WARNING!\n"+"\n".join(meta["warnings"])
            self.warning = add_label(text, scr=self)
            style = lv.style_t()
            lv.style_copy(style, self.message.get_style(0))
            style.text.color = lv.color_hex(0xFF9A00)
            self.warning.set_style(0, style)
            self.warning.align(fee, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
        
