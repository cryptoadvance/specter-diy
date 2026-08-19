import sys
from io import BytesIO


def _write_bytes(data):
    """Write debug output to ST-Link UART only.
    
    USB VCP is reserved for Bitcoin protocol communication.
    ST-Link UART (/dev/ttyACM0) is for debug logs and HIL testing.
    """
    wrote = False
    try:
        import platform
        uart = getattr(platform, "stlk", None)
        if uart is not None:
            uart.write(data)
            wrote = True
    except Exception:
        pass
    if not wrote:
        try:
            print(data.decode().rstrip("\n"))
        except Exception:
            pass


def log(tag, message):
    _write_bytes(("[%s] %s\n" % (tag, message)).encode())


def log_exception(tag, exc):
    log(tag, "EXCEPTION: %s" % exc)
    b = BytesIO()
    sys.print_exception(exc, b)
    _write_bytes(("[%s] TRACEBACK START\n" % tag).encode())
    _write_bytes(b.getvalue())
    if not b.getvalue().endswith(b"\n"):
        _write_bytes(b"\n")
    _write_bytes(("[%s] TRACEBACK END\n" % tag).encode())
