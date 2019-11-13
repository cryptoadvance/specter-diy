import lvgl as lv

queue = []

# decorators
def queued(func):
    """A decorator to put a function in a queue
    after lvgl update instead of calling it right away
    """
    def wrapper(*args, **kwargs):
        queue.append((func, args, kwargs))
    return wrapper

def on_release(func):
    def wrapper(o, e):
        if e == lv.EVENT.RELEASED:
            func()
    return wrapper

def handle_queue():
    while len(queue) > 0:
        cb, args, kwargs = queue.pop()
        cb(*args, **kwargs)