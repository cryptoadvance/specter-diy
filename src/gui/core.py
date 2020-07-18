import lvgl as lv
import time

import display

from .common import init_styles


def init(blocking=True):
    display.init(not blocking)

    # Initialize the styles
    init_styles()

    scr = lv.obj()
    lv.scr_load(scr)
    update()


def update(dt: int = 30):
    display.update(dt)


def ioloop(dt: int = 30):
    while True:
        time.sleep_ms(dt)
        update(dt)
