import lvgl as lv
import time

import display

from .common import init_styles


def init(blocking=True, dark=True):
    # Ensure display is initialized first (for LVGL 9.x)
    display.init(not blocking)

    # Initialize the styles
    init_styles(dark=dark)

    scr = lv.obj()
    lv.screen_load(scr)
    update()


def update(dt: int = 30):
    display.update(dt)


def ioloop(dt: int = 30):
    while True:
        time.sleep_ms(dt)
        update(dt)
