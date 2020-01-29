import lvgl as lv
from .common import *
from .decorators import *

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
        self.message = add_label(message, scr=self)
        self.message.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

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
        self.qr.align(self.title, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)
        self.message.align(self.qr, lv.ALIGN.OUT_BOTTOM_MID, 0, 50)

# one-liners

def close_all_popups():
    for p in reversed(popups):
        p.close()

def alert(title, message, callback=None):
    return Alert(title, message, close_callback=callback)

def prompt(title, message, ok=None, cancel=None):
    return Prompt(title, message, confirm_callback=ok, close_callback=cancel)

def error(message):
    alert("Error!", message)

def qr_alert(title, message, message_text=None, callback=None, ok_text="OK", width=None):
    scr = QRAlert(title, message, message_text, callback, qr_width=width)
    scr.close_label.set_text(ok_text)
    return scr

def show_xpub(name, xpub, prefix=None, callback=None):
    msg = prefix+xpub
    scr = qr_alert(name, msg, msg, callback)
    # add checkbox
    if prefix is not None:
        def cb():
            txt = scr.message.get_text()
            if prefix in txt:
                txt = xpub
            else:
                txt = prefix+xpub
            scr.message.set_text(txt)
            scr.qr.set_text(txt)
        btn = add_button("Toggle derivation", on_release(cb), y=600)

def show_mnemonic(mnemonic):
    alert("Your recovery phrase:", "")
    add_mnemonic_table(mnemonic, y=100)

def show_wallet(wallet, delete_cb=None):
    idx = 0
    addr = wallet.address(idx)
    # dirty hack: add \n at the end to increase title size 
    #             to skip realigning of the qr code
    scr = qr_alert("Wallet \"%s\"\n" % wallet.name,
                             "bitcoin:"+addr, addr,
                             ok_text="Close", width=300)
    lbl = add_label("Receiving address #%d" % (idx+1), y=80)
    def cb_update(delta):
        idx = int(lbl.get_text().split("#")[1])
        if idx+delta >= 0:
            idx += delta
        addr = wallet.address(idx)
        scr.message.set_text(addr)
        scr.qr.set_text("bitcoin:"+addr)
        lbl.set_text("Receiving address #%d" % idx)
        if idx > 0:
            prv.set_state(lv.btn.STATE.REL)
        else:
            prv.set_state(lv.btn.STATE.INA)
    def cb_next():
        cb_update(1)
    def cb_prev():
        cb_update(-1)
    def cb_del():
        delete_cb(wallet)
        scr.close()
    delbtn = add_button("Delete wallet", on_release(cb_del), y=600)
    prv, nxt = add_button_pair("Previous", on_release(cb_prev),
                               "Next", on_release(cb_next),
                               y=500)
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


