import lvgl as lv
import utime as time

try:
    # hardware - use udisplay
    import udisplay as display
except:
    # otherwise - display_unixport frozen in unix simulator
    import display

from .common import init_styles
from .decorators import handle_queue

def init():
    display.init()
    
    # Initialize the styles
    init_styles()

    scr = lv.obj()
    lv.scr_load(scr)

def update(dt:int=30):
    display.update(dt)
    handle_queue()

def ioloop(dt:int=30):
    while True:
        time.sleep_ms(dt)
        update(dt)
