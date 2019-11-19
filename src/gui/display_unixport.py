import lvgl as lv
import SDL

HOR_RES = 480
VER_RES = 800

def init(*args, **kwargs):
    """
    GUI initialization function. 
    Should be called once in the very beginning.
    """

    # init the gui library
    lv.init()
    # init the hardware library
    SDL.init()

    # Register SDL display driver
    disp_buf1 = lv.disp_buf_t()
    buf1_1 = bytearray(HOR_RES*10)
    lv.disp_buf_init(disp_buf1,buf1_1, None, len(buf1_1)//4)
    disp_drv = lv.disp_drv_t()
    lv.disp_drv_init(disp_drv)
    disp_drv.buffer = disp_buf1
    disp_drv.flush_cb = SDL.monitor_flush
    disp_drv.hor_res = HOR_RES
    disp_drv.ver_res = VER_RES
    lv.disp_drv_register(disp_drv)

    # Regsiter SDL mouse driver
    indev_drv = lv.indev_drv_t()
    lv.indev_drv_init(indev_drv) 
    indev_drv.type = lv.INDEV_TYPE.POINTER;
    indev_drv.read_cb = SDL.mouse_read;
    lv.indev_drv_register(indev_drv);

def update(*args, **kwargs):
    pass