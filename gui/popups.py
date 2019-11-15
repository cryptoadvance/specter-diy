import lvgl as lv
from .common import *
from .decorators import *

# pop-up screens
def alert(title, message, callback=None):
    old_scr = lv.scr_act()
    scr = lv.obj()
    lv.scr_load(scr)
    add_label(title, style="title")
    add_label(message, y=PADDING+100)
    def cb(obj, event):
        if event == lv.EVENT.RELEASED:
            lv.scr_load(old_scr)
            if callback is not None:
                callback()
    add_button("OK", cb)

def prompt(title, message, ok=None, cancel=None, **kwargs):
    old_scr = lv.scr_act()
    scr = lv.obj()
    lv.scr_load(scr)
    add_label(title, style="title")
    add_label(message, y=PADDING+100)

    def cb_ok(obj, event):
        if event == lv.EVENT.RELEASED:
            lv.scr_load(old_scr)
            if ok is not None:
                ok(**kwargs)

    def cb_cancel(obj, event):
        if event == lv.EVENT.RELEASED:
            lv.scr_load(old_scr)
            if cancel is not None:
                cancel(**kwargs)

    add_button_pair(
            "Cancel", cb_cancel,
            "Confirm", cb_ok,
        )

def error(message):
    alert("Error!", message)

def qr_alert(title, message, message_text=None, callback=None, ok_text="OK"):
    old_scr = lv.scr_act()
    scr = lv.obj()
    lv.scr_load(scr)
    add_label(title, style="title")
    qrobj = add_qrcode(message, scr=scr, y=PADDING+100)
    msgobj = None
    if message_text is not None:
        y = qrobj.get_y()+qrobj.get_height()+20
        msg_obj = add_label(message_text, y=y)
    def cb(obj, event):
        if event == lv.EVENT.RELEASED:
            lv.scr_load(old_scr)
            qrobj.delete()
            gc.collect()
            if callback is not None:
                callback()
    add_button(ok_text, cb)
    # objects to manupulate if necessary
    return (qrobj, msg_obj)

def show_xpub(name, xpub, prefix=None, callback=None):
    msg = prefix+xpub
    qrobj, msgobj = qr_alert("Master "+name, msg, msg, callback)
    scr = lv.scr_act()
    # add checkbox
    if prefix is not None:
        def cb():
            txt = msgobj.get_text()
            if prefix in txt:
                txt = xpub
            else:
                txt = prefix+xpub
            msgobj.set_text(txt)
            qr_update(qrobj, txt)
        btn = add_button("Toggle derivation", on_release(cb), y=600)

def show_mnemonic(mnemonic):
    alert("Your recovery phrase:", "")
    add_mnemonic_table(mnemonic, y=100)

def show_wallet(wallet):
    idx = 0
    addr = wallet.address(idx)
    qrobj, msgobj = qr_alert("Wallet \"%s\"" % wallet.name, "bitcoin:"+addr, addr, ok_text="Close")
    lbl = add_label("Receiving address #%d" % idx, y=80)
    def cb_update(delta):
        idx = int(lbl.get_text().split("#")[1])
        if idx+delta >= 0:
            idx += delta
        addr = wallet.address(idx)
        msgobj.set_text(addr)
        qr_update(qrobj, "bitcoin:"+addr)
        lbl.set_text("Receiving address #%d" % idx)
        if idx > 0:
            prv.set_state(lv.btn.STATE.REL)
        else:
            prv.set_state(lv.btn.STATE.INA)
    def cb_next():
        cb_update(1)
    def cb_prev():
        cb_update(-1)
    prv, nxt = add_button_pair("Previous", on_release(cb_prev), "Next", on_release(cb_next), y=600)
    prv.set_state(lv.btn.STATE.INA)
