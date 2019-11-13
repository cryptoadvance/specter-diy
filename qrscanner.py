try:
    import pyb
    linuxport = False
except:
    linuxport = True

import utime as time

if not linuxport:
    class QRScanner:
        def __init__(self, trigger="D5", uart="YA", baudrate=9600):
            self.trigger = pyb.Pin(trigger, pyb.Pin.OUT)
            self.trigger.on()
            self.uart = pyb.UART(uart, baudrate, read_buf_len=1024)
            self.uart.read(self.uart.any())
            self.scanning = False
            self.t0 = None
            self.callback = None

        def start_scan(self, callback=None, timeout=None):
            self.trigger.off()
            self.t0 = time.time()
            self.data = ""
            self.scanning = True
            self.callback = callback

        def scan(self, timeout=None):
            self.trigger.off()
            r = ""
            t0 = time.time()
            while len(r)==0 or not r.endswith("\r"):
                res = self.uart.read(self.uart.any())
                if len(res) > 0:
                    r += res.decode('utf-8')
                time.sleep(0.01)
                if timeout is not None:
                    if time.time() > t0+timeout:
                        break
            self.trigger.on()
            if r.endswith("\r"):
                return r[:-1]
            return r

        def update(self):
            if self.scanning:
                res = self.uart.read(self.uart.any())
                if len(res) > 0:
                    self.data += res.decode('utf-8')
                if self.is_done() and self.callback is not None:
                    data = self.data[:-1]
                    self.reset()
                    self.callback(data)

        def is_done(self):
            return self.data.endswith("\r")

        def reset(self):
            self.scanning = False
            self.data = ""
            self.t0 = None
            self.trigger.on()

        def stop(self):
            self.reset()
            return self.data
else:
    # dummy for linuxport
    class QRScanner:
        def __init__(self, *args, **kwargs):
            self.scanning = False
            self.t0 = None
            self.callback = None

        def scan(self, timeout=None):
            print("Enter what QRScanner would have scanned:")
            r = input()
            if r.endswith("\r") or r.endswith("\n"):
                return r[:-1]
            return r

        def reset(self):
            pass

        def start_scan(self, callback=None, timeout=None):
            self.data = ""
            self.scanning = True
            self.callback = callback

        def update(self):
            if self.scanning:
                data = self.scan()
                self.scanning = False
                if self.callback is not None:
                    self.callback(data)

        def stop(self):
            pass