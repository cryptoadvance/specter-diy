import lvgl as lv
import utime as time

try:
    import display
except:
    from . import display_unixport as display

from .common import init_styles
from .decorators import handle_queue

def init():
    display.init()

    # Set theme
    th = lv.theme_material_init(210, lv.font_roboto_22)
    lv.theme_set_current(th)
    
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
