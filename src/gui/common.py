"""Some commonly used functions, like helpers"""
import lvgl as lv
import qrcode
import math
from micropython import const
import gc
from .components import QRCode, styles

PADDING = const(20)
BTN_HEIGHT = const(70)
HOR_RES = const(480)
VER_RES = const(800)
QR_PADDING = const(40)


def init_styles(dark=True):
    if dark:
        # Set theme
        th = lv.theme_night_init(210, lv.font_roboto_22)
        # adjusting theme
        # background color
        cbg = lv.color_hex(0x192432)
        # ctxt = lv.color_hex(0x7f8fa4)
        ctxt = lv.color_hex(0xFFFFFF)
        cbtnrel = lv.color_hex(0x506072)
        cbtnpr = lv.color_hex(0x405062)
        chl = lv.color_hex(0x313E50)
    else:
        # Set theme to light
        # TODO: work in progress...
        th = lv.theme_material_init(210, lv.font_roboto_22)
        # adjusting theme
        # background color
        cbg = lv.color_hex(0xEEEEEE)
        # ctxt = lv.color_hex(0x7f8fa4)
        ctxt = lv.color_hex(0)
        cbtnrel = lv.color_hex(0x506072)
        cbtnpr = lv.color_hex(0x405062)
        chl = lv.color_hex(0x313E50)
        th.style.label.sec.text.color = cbtnrel
    th.style.scr.body.main_color = cbg
    th.style.scr.body.grad_color = cbg
    # text color
    th.style.scr.text.color = ctxt
    # buttons
    # btn released
    th.style.btn.rel.body.main_color = cbtnrel
    th.style.btn.rel.body.grad_color = cbtnrel
    th.style.btn.rel.body.shadow.width = 0
    th.style.btn.rel.body.border.width = 0
    th.style.btn.rel.body.radius = 10
    # btn pressed
    lv.style_copy(th.style.btn.pr, th.style.btn.rel)
    th.style.btn.pr.body.main_color = cbtnpr
    th.style.btn.pr.body.grad_color = cbtnpr
    # button map released
    th.style.btnm.btn.rel.body.main_color = cbg
    th.style.btnm.btn.rel.body.grad_color = cbg
    th.style.btnm.btn.rel.body.radius = 0
    th.style.btnm.btn.rel.body.border.width = 0
    th.style.btnm.btn.rel.body.shadow.width = 0
    th.style.btnm.btn.rel.text.color = ctxt
    # button map pressed
    lv.style_copy(th.style.btnm.btn.pr, th.style.btnm.btn.rel)
    th.style.btnm.btn.pr.body.main_color = chl
    th.style.btnm.btn.pr.body.grad_color = chl
    # button map toggled
    lv.style_copy(th.style.btnm.btn.tgl_pr, th.style.btnm.btn.pr)
    lv.style_copy(th.style.btnm.btn.tgl_rel, th.style.btnm.btn.pr)
    # button map inactive
    lv.style_copy(th.style.btnm.btn.ina, th.style.btnm.btn.rel)
    th.style.btnm.btn.ina.text.opa = 80
    # button map background
    th.style.btnm.bg.body.opa = 0
    th.style.btnm.bg.body.border.width = 0
    th.style.btnm.bg.body.shadow.width = 0
    # textarea
    th.style.ta.oneline.body.opa = 0
    th.style.ta.oneline.body.border.width = 0
    th.style.ta.oneline.text.font = lv.font_roboto_28
    th.style.ta.oneline.text.color = ctxt
    # slider
    th.style.slider.knob.body.main_color = cbtnrel
    th.style.slider.knob.body.grad_color = cbtnrel
    th.style.slider.knob.body.radius = 5
    th.style.slider.knob.body.border.width = 0
    # page
    th.style.page.bg.body.opa = 0
    th.style.page.scrl.body.opa = 0
    th.style.page.bg.body.border.width = 0
    th.style.page.bg.body.padding.left = 0
    th.style.page.bg.body.padding.right = 0
    th.style.page.bg.body.padding.top = 0
    th.style.page.bg.body.padding.bottom = 0
    th.style.page.scrl.body.border.width = 0
    th.style.page.scrl.body.padding.left = 0
    th.style.page.scrl.body.padding.right = 0
    th.style.page.scrl.body.padding.top = 0
    th.style.page.scrl.body.padding.bottom = 0

    lv.theme_set_current(th)

    styles["theme"] = th
    # Title style - just a default style with larger font
    styles["title"] = lv.style_t()
    lv.style_copy(styles["title"], th.style.label.prim)
    styles["title"].text.font = lv.font_roboto_28
    styles["title"].text.color = ctxt

    styles["hint"] = lv.style_t()
    lv.style_copy(styles["hint"], th.style.label.sec)
    styles["hint"].text.font = lv.font_roboto_16

    styles["small"] = lv.style_t()
    lv.style_copy(styles["small"], styles["hint"])
    styles["small"].text.color = ctxt


def add_label(text, y=PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if width is None:
        width = HOR_RES - 2 * PADDING
    if scr is None:
        scr = lv.scr_act()
    lbl = lv.label(scr)
    lbl.set_text(text)
    if style in styles:
        lbl.set_style(0, styles[style])
    lbl.set_long_mode(lv.label.LONG.BREAK)
    lbl.set_width(width)
    lbl.set_x((HOR_RES - width) // 2)
    lbl.set_align(lv.label.ALIGN.CENTER)
    lbl.set_y(y)
    return lbl


def add_button(text=None, callback=None, scr=None, y=700):
    """Helper function that creates a button with a text label"""
    if scr is None:
        scr = lv.scr_act()
    btn = lv.btn(scr)
    btn.set_width(HOR_RES - 2 * PADDING)
    btn.set_height(BTN_HEIGHT)

    if text is not None:
        lbl = lv.label(btn)
        lbl.set_text(text)
        lbl.set_align(lv.label.ALIGN.CENTER)

    btn.align(scr, lv.ALIGN.IN_TOP_MID, 0, 0)
    btn.set_y(y)

    if callback is not None:
        btn.set_event_cb(callback)

    return btn


def add_button_pair(text1, callback1, text2, callback2, scr=None, y=700):
    """Helper function that creates a button with a text label"""
    btn1 = add_button(text1, callback1, scr=scr, y=y)
    btn2 = add_button(text2, callback2, scr=scr, y=y)
    align_button_pair(btn1, btn2)
    return btn1, btn2


def align_button_pair(btn1, btn2):
    """Aligns two buttons in a row"""
    w = (HOR_RES - 3 * PADDING) // 2
    btn1.set_width(w)
    btn2.set_width(w)
    btn1.set_x(PADDING)
    btn2.set_x(HOR_RES // 2 + PADDING // 2)


def add_qrcode(text, y=QR_PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if scr is None:
        scr = lv.scr_act()

    if width is None:
        width = 350

    qr = QRCode(scr)
    qr.set_text(text)
    qr.set_size(width)
    qr.set_text(text)
    qr.align(scr, lv.ALIGN.IN_TOP_MID, 0, y)
    return qr


def separate(addr, letters=6, separator=" "):
    extra = ""
    if len(addr) % letters > 0:
        extra = " " * (letters - (len(addr) % letters))
    return (
        separator.join([addr[i : i + letters] for i in range(0, len(addr), letters)])
        + extra
    )


def format_addr(addr, letters=6, words=3, eol="\n", space=" "):
    return separate(
        separate(addr, letters=letters, separator=space),
        letters=(words * (letters + 1)),
        separator=eol,
    )
