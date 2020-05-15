import lvgl as lv
from .common import *
from .decorators import *
from .components import add_qrcode

# global popups array
# we use it in close_all_popups()
popups = []

# pop-up screens

class Popup(lv.obj):
    def __init__(self, close_callback=None):
        super().__init__()
        self.old_screen = lv.scr_act()
        self.close_callback = close_callback
        # add back button
        self.close_button = add_button(scr=self, 
                                       callback=on_release(self.close)
                                       )

        self.close_label = lv.label(self.close_button)
        self.close_label.set_text("OK") #lv.SYMBOL.LEFT+" Back")

        # activate the screen
        lv.scr_load(self)
        popups.append(self)

    def close(self):
        # activate old screen
        lv.scr_load(self.old_screen)
        if self.close_callback is not None:
            self.close_callback()
        popups.remove(self)
        # delete this screen
        self.del_async()

class Alert(Popup):
    def __init__(self,
                 title="Alert!", 
                 message="Something happened", 
                 close_callback=None):

        super().__init__(close_callback)
        self.title = add_label(title, scr=self, style="title")
        self.page = lv.page(lv.scr_act())
        self.page.set_size(480, 550)
        self.message = add_label(message, scr=self.page)
        self.message.set_recolor(True)
        self.page.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

class Prompt(Alert):
    def __init__(self, title="Are you sure?", message="Make a choice", 
                        confirm_callback=None, close_callback=None):
        super().__init__(title, message, close_callback)

        w = (HOR_RES-3*PADDING)//2
        self.close_button.set_width(w)
        self.close_label.set_text("Cancel")

        self.confirm_button = add_button(callback=on_release(self.confirm), scr=self)
        self.confirm_button.set_width(w)
        self.confirm_button.set_x(HOR_RES//2+PADDING//2)
        self.confirm_callback = confirm_callback
        self.confirm_label = lv.label(self.confirm_button)
        self.confirm_label.set_text("Confirm")

    def confirm(self):
        # a hack to call confirm callback
        self.close_callback = self.confirm_callback
        self.close()

class QRAlert(Alert):
    def __init__(self,
                 title="QR Alert!", 
                 qr_message="QR code of something",
                 message="Something happened", 
                 close_callback=None, qr_width=None):
        super().__init__(title, message, close_callback)
        self.qr = add_qrcode(qr_message, scr=self, width=qr_width)
        self.qr.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 25)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

# one-liners

def close_all_popups():
    for p in reversed(popups):
        p.close()

def alert(title, message, callback=None):
    return Alert(title, message, close_callback=callback)

def prompt(title, message, ok=None, cancel=None):
    return Prompt(title, message, confirm_callback=ok, close_callback=cancel)

def format_addr(addr, letters=6, separator=" "):
    extra = ""
    if len(addr) % letters > 0:
        extra = " "*(letters-(len(addr) % letters))
    return separator.join([addr[i:i+letters] for i in range(0, len(addr), letters)])+extra

def prompt_tx(title, data, ok=None, cancel=None):
    message = ""
    scr = prompt(title, message, ok=ok, cancel=cancel)
    obj = scr.message
    obj.set_y(0)
    style = lv.style_t()
    lv.style_copy(style, scr.message.get_style(0))
    style.text.font = lv.font_roboto_mono_28

    for out in data["send_outputs"]:
        addr = format_addr(
                    format_addr(
                        out["address"], letters=6, separator=" "
                    ), 
                    letters=21, separator="\n"
                )
        lbl = add_label("%u sat ( %g BTC ) to" % (out["value"], out["value"]/1e8), scr=scr)
        lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
        addrlbl = add_label(addr, scr=scr)
        addrlbl.set_style(0, style)
        addrlbl.align(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
        obj = addrlbl

    lbl = lv.label(scr)
    lbl.set_text("Fee: %u satoshi - %.1f" % (data["fee"], 100*data["fee"]/data["spending"]) + "%")
    lbl.align(obj, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

    if "warning" in data:
        lbl_w = lv.label(scr)
        lbl_w.set_recolor(True)
        lbl_w.set_text(data["warning"])
        lbl_w.set_align(lv.label.ALIGN.CENTER)
        lbl_w.align(lbl, lv.ALIGN.OUT_BOTTOM_MID, 0, 70)

    return scr

def error(message):
    alert("Error!", message)

def qr_alert(title, message, message_text=None, callback=None, ok_text="OK", width=None):
    scr = QRAlert(title, message, message_text, callback, qr_width=width)
    scr.close_label.set_text(ok_text)
    return scr

def show_xpub(name, xpub, slip132=None, prefix=None, callback=None):
    if slip132 is not None:
        msg = slip132
    else:
        msg = xpub
    if prefix is not None:
        msg = prefix+msg
    scr = qr_alert(name, msg, msg, callback)
    style = lv.style_t()
    lv.style_copy(style, scr.message.get_style(0))
    style.text.font = lv.font_roboto_mono_22
    scr.message.set_style(0, style)

    if prefix is not None:
        lbl = lv.label(scr)
        lbl.set_text("Show derivation path")
        lbl.set_pos(2*PADDING, 590)
        prefix_switch = lv.sw(scr)
        prefix_switch.on(lv.ANIM.OFF)
        prefix_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

    if slip132 is not None:
        lbl = lv.label(scr)
        lbl.set_text("Use SLIP-132")
        lbl.set_pos(2*PADDING, 640)
        slip_switch = lv.sw(scr)
        slip_switch.on(lv.ANIM.OFF)
        slip_switch.align(lbl, lv.ALIGN.OUT_LEFT_MID, 350, 0)

    def cb():
        msg = xpub
        if slip132 is not None and slip_switch.get_state():
            msg = slip132
        if prefix is not None and prefix_switch.get_state():
            msg = prefix+msg
        scr.message.set_text(msg)
        scr.qr.set_text(msg)

    if prefix is not None:
        prefix_switch.set_event_cb(on_release(cb))
    if slip132 is not None:
        slip_switch.set_event_cb(on_release(cb))

def show_mnemonic(mnemonic):
    alert("Your recovery phrase:", "")
    add_mnemonic_table(mnemonic, y=100)

def show_wallet(wallet, delete_cb=None):
    idx = 0
    addr = wallet.address(idx)
    # dirty hack: add \n at the end to increase title size 
    #             to skip realigning of the qr code
    scr = qr_alert("Wallet \"%s\"\n" % wallet.name,
                             "bitcoin:"+addr, format_addr(addr),
                             ok_text="Close", width=250)
    style = lv.style_t()
    lv.style_copy(style, scr.message.get_style(0))
    style.text.font = lv.font_roboto_mono_22
    scr.message.set_style(0, style)

    lbl = add_label("Receiving address #%d" % (idx+1), y=80)
    def cb_update(delta):
        idx = int(lbl.get_text().split("#")[1])-1
        if idx+delta >= 0:
            idx += delta
        addr = wallet.address(idx)
        scr.message.set_text(format_addr(addr))
        scr.qr.set_text("bitcoin:"+addr)
        lbl.set_text("Receiving address #%d" % (idx+1))
        if idx > 0:
            prv.set_state(lv.btn.STATE.REL)
        else:
            prv.set_state(lv.btn.STATE.INA)
    def cb_next():
        cb_update(1)
    def cb_prev():
        cb_update(-1)
    def cb_del():
        scr.close()
        delete_cb(wallet)
    delbtn = add_button("Delete wallet", on_release(cb_del), y=610)
    prv, nxt = add_button_pair("Previous", on_release(cb_prev),
                               "Next", on_release(cb_next),
                               y=520)
    prv.set_state(lv.btn.STATE.INA)

def show_settings(config, save_callback):
    def cb():
        new_config = {"usb": usb_switch.get_state(), "developer": dev_switch.get_state()}
        save_callback(new_config)

    scr = Prompt("Device settings", "", confirm_callback=cb)
    scr.confirm_label.set_text("Save & Reboot")
    usb_label = add_label("USB communication", 120, scr=scr)
    usb_hint = add_label("If USB is enabled the device will be able to talk to your computer. This increases attack surface but sometimes makes it more convenient to use.", 160, scr=scr, style="hint")
    usb_switch = lv.sw(scr)
    usb_switch.align(usb_hint, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
    lbl = add_label(" OFF                              ON  ")
    lbl.align(usb_switch, lv.ALIGN.CENTER, 0, 0)
    if config["usb"]:
        usb_switch.on(lv.ANIM.OFF)

    dev_label = add_label("Developer mode", 320, scr=scr)
    dev_hint = add_label("In developer mode internal flash will be mounted to your computer so you could edit files, but your secrets will be visible as well. Also enables interactive shell through miniUSB port.", 360, scr=scr, style="hint")
    dev_switch = lv.sw(scr)
    dev_switch.align(dev_hint, lv.ALIGN.OUT_BOTTOM_MID, 0, 20)
    lbl = add_label(" OFF                              ON  ")
    lbl.align(dev_switch, lv.ALIGN.CENTER, 0, 0)
    if config["developer"]:
        dev_switch.on(lv.ANIM.OFF)
