import lvgl as lv

def on_release(func):
    def wrapper(o, e):
        if e == lv.EVENT.RELEASED:
            func()
    return wrapper

def cb_with_args(callback, *args, **kwargs):
    def cb():
        if callback is not None:
            callback(*args, **kwargs)
    return cb
