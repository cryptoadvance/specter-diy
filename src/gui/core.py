import lvgl as lv
import utime as time

import display

from .common import init_styles
from .decorators import handle_queue

def init(blocking=True):
    display.init(not blocking)

    # Initialize the styles
    init_styles()

    scr = lv.obj()
    lv.scr_load(scr)
    update()

def update(dt:int=30):
    display.update(dt)
    handle_queue()

def ioloop(dt:int=30):
    while True:
        time.sleep_ms(dt)
        update(dt)
