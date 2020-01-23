import lvgl as lv
import qrcode
import math
from micropython import const
import gc
from .components import QRCode

PADDING    = const(30)
BTN_HEIGHT = const(80)
HOR_RES    = const(480)
VER_RES    = const(800)
QR_PADDING = const(40)

styles = {}

def init_styles():
    # Set theme
    th = lv.theme_night_init(210, lv.font_roboto_22)
    # adjusting theme
    # background color
    cbg = lv.color_hex(0x192432)
    th.style.scr.body.main_color = cbg
    th.style.scr.body.grad_color = cbg
    # text color
    ctxt = lv.color_hex(0x7f8fa4)
    th.style.scr.text.color = ctxt
    # buttons
    cbtnrel = lv.color_hex(0x506072)
    cbtnpr = lv.color_hex(0x405062)
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
    # button map pressed
    chl = lv.color_hex(0x313E50)
    lv.style_copy(th.style.btnm.btn.pr, th.style.btnm.btn.rel)
    th.style.btnm.btn.pr.body.main_color = chl
    th.style.btnm.btn.pr.body.grad_color = chl
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
    # slider
    th.style.slider.knob.body.main_color = cbtnrel
    th.style.slider.knob.body.grad_color = cbtnrel
    th.style.slider.knob.body.radius = 5
    th.style.slider.knob.body.border.width = 0
    styles["theme"] = th

    lv.theme_set_current(th)

    # Title style - just a default style with larger font
    styles["title"] = lv.style_t()
    lv.style_copy(styles["title"], th.style.label.prim)
    styles["title"].text.font = lv.font_roboto_28
    styles["title"].text.color = lv.color_hex(0xffffff)

    styles["hint"] = lv.style_t()
    lv.style_copy(styles["hint"], th.style.label.sec)
    styles["hint"].text.font = lv.font_roboto_16
    # styles["hint"].text.color = lv.color_hex(0xffffff)

def add_label(text, y=PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if width is None:
        width = HOR_RES-2*PADDING
    if scr is None:
        scr = lv.scr_act()
    lbl = lv.label(scr)
    lbl.set_text(text)
    if style in styles:
        lbl.set_style(0, styles[style])
    lbl.set_long_mode(lv.label.LONG.BREAK)
    lbl.set_width(width)
    lbl.set_x((HOR_RES-width)//2)
    lbl.set_align(lv.label.ALIGN.CENTER)
    lbl.set_y(y)
    return lbl

def add_button(text, callback=None, scr=None, y=700):
    """Helper function that creates a button with a text label"""
    if scr is None:
        scr = lv.scr_act()
    btn = lv.btn(scr)
    btn.set_width(HOR_RES-2*PADDING);
    btn.set_height(BTN_HEIGHT);
    
    lbl = lv.label(btn)
    lbl.set_text(text)
    lbl.set_align(lv.label.ALIGN.CENTER)

    btn.align(scr, lv.ALIGN.IN_TOP_MID, 0, 0)
    btn.set_y(y)

    if callback is not None:
        btn.set_event_cb(callback)

    return btn

def add_mnemonic(mnemonic, scr=None, y=200):
    return add_label(mnemonic, y=y, scr=scr)

def add_button_pair(text1, callback1, text2, callback2, scr=None, y=700):
    """Helper function that creates a button with a text label"""
    w = (HOR_RES-3*PADDING)//2
    btn1 = add_button(text1, callback1, scr=scr, y=y)
    btn1.set_width(w)
    btn2 = add_button(text2, callback2, scr=scr, y=y)
    btn2.set_width(w)
    btn2.set_x(HOR_RES//2+PADDING//2)
    return btn1, btn2

def add_qrcode(text, y=QR_PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if scr is None:
        scr = lv.scr_act()
    scr = lv.scr_act()

    if width is None:
        width = 350

    qr = QRCode(scr)
    qr.set_text(text)
    qr.set_size(width)
    qr.set_text(text)
    qr.align(scr, lv.ALIGN.IN_TOP_MID, 0, y)
    return qr

def table_set_mnemonic(table, mnemonic):
    words = mnemonic.split()
    for i in range(24):
        row = i%12
        col = 1+2*(i//12)
        if i < len(words):
            table.set_cell_value(row, col, words[i])
        else:
            table.set_cell_value(row, col, "")

def add_mnemonic_table(mnemonic, y=PADDING, scr=None):
    if scr is None:
        scr = lv.scr_act()

    cell_style = lv.style_t()
    lv.style_copy(cell_style, styles["theme"].style.label.prim)
    cell_style.body.opa = 0
    cell_style.text.font = lv.font_roboto_22

    num_style = lv.style_t()
    lv.style_copy(num_style, cell_style)
    num_style.text.opa = lv.OPA._40

    table = lv.table(scr)
    table.set_col_cnt(4)
    table.set_row_cnt(12)
    table.set_col_width(0, 50)
    table.set_col_width(2, 50)
    table.set_col_width(1, 150)
    table.set_col_width(3, 150)

    table.set_style(lv.page.STYLE.BG, cell_style)
    table.set_style(lv.table.STYLE.CELL1, cell_style)
    table.set_style(lv.table.STYLE.CELL2, num_style)

    for i in range(12):
        table.set_cell_value(i, 0, "%d" % (i+1))
        table.set_cell_value(i, 2, "%d" % (i+13))
        table.set_cell_type(i, 0, lv.table.STYLE.CELL2)
        table.set_cell_type(i, 2, lv.table.STYLE.CELL2)
    table.align(scr, lv.ALIGN.IN_TOP_MID, 0, y)

    table_set_mnemonic(table, mnemonic)

    return table
