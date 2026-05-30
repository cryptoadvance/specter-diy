import lvgl as lv
import time
import rng


def feed_touch():
    """
    Gets a point from the touchscreen
    and feeds it to random number pool
    """
    point = lv.point_t()
    indev = lv.indev_active()
    if indev:
        indev.get_point(point)
        # now we can take bytes([point.x % 256, point.y % 256])
        # and feed it into hash digest
        t = time.ticks_cpu()
        random_data = t.to_bytes(4, "big") + bytes([point.x % 256, point.y % 256])
        rng.feed(random_data)


def feed_rng(func):
    """Feed touch entropy on PRESSING and pass all events to func."""
    def wrapper(event):
        code = event.get_code()
        if code == lv.EVENT.PRESSING:
            feed_touch()
        func(event)

    return wrapper


def feed_touch_on_pressing(event):
    """LVGL event callback that feeds touch entropy on PRESSING."""
    if event.get_code() == lv.EVENT.PRESSING:
        feed_touch()


def on_release(func):
    """Call func on CLICKED events.

    Shared buttons register a separate PRESSING handler for entropy. The
    PRESSING branch remains here for callbacks registered with EVENT.ALL.
    """
    def wrapper(event):
        code = event.get_code()
        if code == lv.EVENT.PRESSING:
            feed_touch()
        elif code == lv.EVENT.CLICKED and func is not None:
            func()

    return wrapper


def cb_with_args(callback, *args, **kwargs):
    """Pass arguments to the lv callback"""

    def cb():
        if callback is not None:
            callback(*args, **kwargs)

    return cb
