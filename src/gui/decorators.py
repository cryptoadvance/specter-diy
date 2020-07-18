import lvgl as lv
import time
import rng


def feed_touch():
    """
    Gets a point from the touchscreen 
    and feeds it to random number pool
    """
    point = lv.point_t()
    indev = lv.indev_get_act()
    lv.indev_get_point(indev, point)
    # now we can take bytes([point.x % 256, point.y % 256])
    # and feed it into hash digest
    t = time.ticks_cpu()
    random_data = t.to_bytes(4, 'big') + bytes([point.x % 256, point.y % 256])
    rng.feed(random_data)


def feed_rng(func):
    """Any callback will contribute to random number pool"""
    def wrapper(o, e):
        if e == lv.EVENT.PRESSING:
            feed_touch()
        func(o, e)
    return wrapper


def on_release(func):
    """Handy decorator if you only care about click event"""
    def wrapper(o, e):
        if e == lv.EVENT.PRESSING:
            feed_touch()
        elif e == lv.EVENT.RELEASED and func is not None:
            func()
    return wrapper


def cb_with_args(callback, *args, **kwargs):
    """Pass arguments to the lv callback"""
    def cb():
        if callback is not None:
            callback(*args, **kwargs)
    return cb
