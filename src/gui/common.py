import lvgl as lv
import qrcode
import math
from micropython import const
import gc

PADDING    = const(30)
BTN_HEIGHT = const(80)
HOR_RES    = const(480)
VER_RES    = const(800)
QR_PADDING = const(40)

styles = {}

def init_styles():
    # Title style - just a default style with larger font
    styles["title"] = lv.style_t()
    lv.style_copy(styles["title"], lv.style_plain)
    styles["title"].text.font = lv.font_roboto_28

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

def qr_update(lbl, text):
    print("QRcode on the screen:", text)
    qr = qrcode.encode_to_string(text)
    size = int(math.sqrt(len(qr)))
    width = lbl.get_width()
    scale = width//(size+4)
    sizes = [1,2,3,5,7,10]
    fontsize = [s for s in sizes if s < scale][-1]
    font = getattr(lv, "square%d" % fontsize)
    style = lv.style_t()
    lv.style_copy(style, lv.style_plain)
    style.body.main_color = lv.color_make(0xFF,0xFF,0xFF)
    style.body.grad_color = lv.color_make(0xFF,0xFF,0xFF)
    style.body.opa = 255
    style.text.font = font
    style.text.line_space = 0;
    style.text.letter_space = 0;
    lbl.set_style(0, style)
    # lbl.set_body_draw(True)
    lbl.set_text(qr)
    del qr
    gc.collect()

def add_qrcode(text, y=QR_PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if scr is None:
        scr = lv.scr_act()

    scr = lv.scr_act()

    lbl = add_label("Text", y=y, scr=scr, width=width)
    qr_update(lbl, text)
    return lbl

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
    num_style = lv.style_t()
    lv.style_copy(num_style, lv.style_transp)
    num_style.text.opa = lv.OPA._40

    table = lv.table(scr)
    table.set_col_cnt(4)
    table.set_row_cnt(12)
    table.set_col_width(0, 50)
    table.set_col_width(2, 50)
    table.set_col_width(1, 150)
    table.set_col_width(3, 150)

    table.set_style(lv.page.STYLE.BG, lv.style_transp)
    table.set_style(lv.table.STYLE.CELL1, lv.style_transp)
    table.set_style(lv.table.STYLE.CELL2, num_style)

    for i in range(12):
        table.set_cell_value(i, 0, "%d" % (i+1))
        table.set_cell_value(i, 2, "%d" % (i+13))
        table.set_cell_type(i, 0, lv.table.STYLE.CELL2)
        table.set_cell_type(i, 2, lv.table.STYLE.CELL2)
    table.align(scr, lv.ALIGN.IN_TOP_MID, 0, y)

    table_set_mnemonic(table, mnemonic)

    return table
