"""Some commonly used functions, like helpers"""
import lvgl as lv
#import qrcode
import math
from micropython import const
import gc
from .components import QRCode, styles
from .decorators import feed_touch_on_pressing

PADDING = const(20)
BTN_HEIGHT = const(70)
HOR_RES = const(480)
VER_RES = const(800)
QR_PADDING = const(40)
QR_WIDTH = const(320)
FONT_SCALE_MINUS_TWO_PT = const(238)  # 26 / 28 * LVGL's 256 scale.
BUTTON_LABEL_SCALE = const(192)  # 21 / 28 * LVGL's 256 scale.


def init_styles(dark=True):
    # LVGL 9.x theme and style initialization
    disp = lv.display_get_default()

    if dark:
        cbg = lv.color_hex(0x192432)
        ctxt = lv.color_hex(0xFFFFFF)
        cbtnrel = lv.color_hex(0x506072)
        cbtnpr = lv.color_hex(0x405062)
        chl = lv.color_hex(0x313E50)
        cprimary = lv.palette_main(lv.PALETTE.BLUE)
        csecondary = lv.palette_main(lv.PALETTE.GREY)
    else:
        cbg = lv.color_hex(0xEEEEEE)
        ctxt = lv.color_hex(0x000000)
        cbtnrel = lv.color_hex(0x506072)
        cbtnpr = lv.color_hex(0x405062)
        chl = lv.color_hex(0x313E50)
        cprimary = lv.palette_main(lv.PALETTE.BLUE)
        csecondary = lv.palette_main(lv.PALETTE.GREY)

    # Initialize default theme
    th = lv.theme_default_init(disp, cprimary, csecondary, dark, lv.font_montserrat_22)
    disp.set_theme(th)

    # Store colors for later use
    styles["cbg"] = cbg
    styles["ctxt"] = ctxt
    styles["cbtnrel"] = cbtnrel
    styles["cbtnpr"] = cbtnpr
    styles["chl"] = chl
    styles["chint"] = lv.color_hex(0x6E7F91)

    # Screen style
    styles["scr"] = lv.style_t()
    styles["scr"].init()
    styles["scr"].set_bg_color(cbg)
    styles["scr"].set_bg_opa(255)
    styles["scr"].set_text_color(ctxt)
    styles["scr"].set_border_width(0)
    styles["scr"].set_outline_width(0)
    styles["scr"].set_shadow_width(0)
    styles["scr"].set_radius(0)
    styles["scr"].set_pad_all(0)

    # Button style
    styles["btn"] = lv.style_t()
    styles["btn"].init()
    styles["btn"].set_bg_color(cbtnrel)
    styles["btn"].set_bg_opa(255)
    styles["btn"].set_shadow_width(0)
    styles["btn"].set_border_width(0)
    styles["btn"].set_outline_width(0)
    styles["btn"].set_radius(10)
    styles["btn"].set_pad_all(0)
    styles["btn"].set_text_color(ctxt)
    styles["btn"].set_text_font(lv.font_montserrat_28)

    # Button pressed style
    styles["btn_pressed"] = lv.style_t()
    styles["btn_pressed"].init()
    styles["btn_pressed"].set_bg_color(cbtnpr)
    styles["btn_pressed"].set_bg_opa(255)
    styles["btn_pressed"].set_shadow_width(0)
    styles["btn_pressed"].set_border_width(0)
    styles["btn_pressed"].set_outline_width(0)
    styles["btn_pressed"].set_radius(10)
    styles["btn_pressed"].set_pad_all(0)
    styles["btn_pressed"].set_text_color(ctxt)
    styles["btn_pressed"].set_text_font(lv.font_montserrat_28)

    styles["btn_label"] = lv.style_t()
    styles["btn_label"].init()
    styles["btn_label"].set_text_color(ctxt)
    styles["btn_label"].set_text_font(lv.font_montserrat_28)
    styles["btn_label"].set_transform_scale(BUTTON_LABEL_SCALE)

    styles["page"] = lv.style_t()
    styles["page"].init()
    styles["page"].set_bg_opa(0)
    styles["page"].set_border_width(0)
    styles["page"].set_outline_width(0)
    styles["page"].set_shadow_width(0)
    styles["page"].set_radius(0)
    styles["page"].set_pad_all(0)

    # Button matrix styles
    styles["btnm"] = lv.style_t()
    styles["btnm"].init()
    styles["btnm"].set_bg_opa(0)
    styles["btnm"].set_radius(0)
    styles["btnm"].set_border_width(0)
    styles["btnm"].set_outline_width(0)
    styles["btnm"].set_shadow_width(0)
    styles["btnm"].set_pad_all(0)
    styles["btnm"].set_text_color(ctxt)

    styles["btnm_pressed"] = lv.style_t()
    styles["btnm_pressed"].init()
    styles["btnm_pressed"].set_bg_opa(0)
    styles["btnm_pressed"].set_radius(0)
    styles["btnm_pressed"].set_border_width(0)
    styles["btnm_pressed"].set_outline_width(0)
    styles["btnm_pressed"].set_shadow_width(0)
    styles["btnm_pressed"].set_pad_all(0)
    styles["btnm_pressed"].set_text_color(ctxt)

    styles["btnm_checked"] = lv.style_t()
    styles["btnm_checked"].init()
    styles["btnm_checked"].set_bg_color(chl)
    styles["btnm_checked"].set_bg_opa(255)
    styles["btnm_checked"].set_radius(0)
    styles["btnm_checked"].set_border_width(0)
    styles["btnm_checked"].set_outline_width(0)
    styles["btnm_checked"].set_shadow_width(0)
    styles["btnm_checked"].set_pad_all(0)
    styles["btnm_checked"].set_text_color(ctxt)

    styles["btnm_bg"] = lv.style_t()
    styles["btnm_bg"].init()
    styles["btnm_bg"].set_bg_opa(0)
    styles["btnm_bg"].set_border_width(0)
    styles["btnm_bg"].set_outline_width(0)
    styles["btnm_bg"].set_shadow_width(0)
    styles["btnm_bg"].set_radius(0)
    styles["btnm_bg"].set_pad_all(0)

    # Textarea style
    styles["ta"] = lv.style_t()
    styles["ta"].init()
    styles["ta"].set_bg_opa(0)
    styles["ta"].set_border_width(0)
    styles["ta"].set_outline_width(0)
    styles["ta"].set_shadow_width(0)
    styles["ta"].set_radius(0)
    styles["ta"].set_pad_all(0)
    styles["ta"].set_text_font(lv.font_montserrat_28)
    styles["ta"].set_text_color(ctxt)

    styles["ta_cursor"] = lv.style_t()
    styles["ta_cursor"].init()
    styles["ta_cursor"].set_border_side(lv.BORDER_SIDE.LEFT)
    styles["ta_cursor"].set_border_color(ctxt)
    styles["ta_cursor"].set_border_width(2)
    styles["ta_cursor"].set_bg_opa(lv.OPA.TRANSP)
    styles["ta_cursor"].set_anim_duration(500)

    # Slider knob style
    styles["slider_knob"] = lv.style_t()
    styles["slider_knob"].init()
    styles["slider_knob"].set_bg_color(cbtnrel)
    styles["slider_knob"].set_radius(5)
    styles["slider_knob"].set_border_width(0)

    styles["theme"] = th

    # Title style
    styles["title"] = lv.style_t()
    styles["title"].init()
    styles["title"].set_text_font(lv.font_montserrat_28)
    styles["title"].set_text_color(ctxt)

    # Hint style
    styles["hint"] = lv.style_t()
    styles["hint"].init()
    styles["hint"].set_text_font(lv.font_montserrat_16)
    styles["hint"].set_text_color(styles["chint"])

    # Small style
    styles["small"] = lv.style_t()
    styles["small"].init()
    styles["small"].set_text_font(lv.font_montserrat_16)
    styles["small"].set_text_color(ctxt)

    # Warning style
    styles["warning"] = lv.style_t()
    styles["warning"].init()
    styles["warning"].set_text_color(lv.color_hex(0xFF9A00))

def center_button_label(lbl):
    lbl.update_layout()
    lbl.set_style_transform_pivot_x(lbl.get_width() // 2, 0)
    lbl.set_style_transform_pivot_y(lbl.get_height() // 2, 0)
    lbl.center()


def recenter_button_labels(btn):
    for i in range(btn.get_child_count()):
        center_button_label(btn.get_child(i))


def add_button_label(btn, text):
    lbl = lv.label(btn)
    lbl.set_text(text)
    lbl.add_style(styles["btn_label"], 0)
    center_button_label(lbl)
    return lbl


def add_label(text, y=PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if width is None:
        width = HOR_RES - 2 * PADDING
    if scr is None:
        scr = lv.screen_active()
    lbl = lv.label(scr)
    lbl.set_text(text)
    if style in styles:
        lbl.add_style(styles[style], 0)
    lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
    lbl.set_width(width)
    lbl.set_x((HOR_RES - width) // 2)
    lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    lbl.set_y(y)
    return lbl


def add_button(text=None, callback=None, scr=None, y=700):
    """Helper function that creates a button with a text label"""
    if scr is None:
        scr = lv.screen_active()
    btn = lv.button(scr)
    btn.set_width(HOR_RES - 2 * PADDING)
    btn.set_height(BTN_HEIGHT)
    btn.add_style(styles["btn"], 0)
    btn.add_style(styles["btn_pressed"], lv.STATE.PRESSED)

    if text is not None:
        add_button_label(btn, text)

    btn.align(lv.ALIGN.TOP_MID, 0, 0)
    btn.set_y(y)

    if callback is not None:
        btn.add_event_cb(feed_touch_on_pressing, lv.EVENT.PRESSING, None)
        btn.add_event_cb(callback, lv.EVENT.CLICKED, None)

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
    # Clear alignment and set explicit x positions
    btn1.set_align(lv.ALIGN.DEFAULT)
    btn2.set_align(lv.ALIGN.DEFAULT)
    btn1.set_x(PADDING)
    btn2.set_x(PADDING + w + PADDING)
    recenter_button_labels(btn1)
    recenter_button_labels(btn2)


def add_qrcode(text, y=QR_PADDING, scr=None, style=None, width=None):
    """Helper functions that creates a title-styled label"""
    if scr is None:
        scr = lv.screen_active()

    if width is None:
        width = QR_WIDTH

    qr = QRCode(scr)
    qr.set_size(width)
    qr.set_qr_inset(13)
    qr.set_fixed_size(True)
    qr.set_text(text)
    qr.align_to(scr, lv.ALIGN.TOP_MID, 0, y)
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
