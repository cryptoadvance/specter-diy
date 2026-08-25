"""Camada de compatibilidade `pyb` para o ESP32-P4.

O app do Specter fala com o hardware por `pyb`, a API da porta STM32 do
MicroPython, que nao existe no ESP32. Ha precedente para resolver isso com um
shim: `f469-disco/libs/unix/pyb.py` finge o modulo inteiro em 117 linhas para o
simulador rodar em Linux. Este arquivo faz o mesmo para a placa, mapeando para
`machine`.

O app toca hardware em apenas quatro arquivos, com 26 pontos de chamada no
total, entao a superficie coberta aqui e pequena de proposito.

HONESTIDADE SOBRE OS STUBS
--------------------------
Nem tudo que o STM32 oferece existe nesta placa. Onde nao existe, este modulo
entrega um objeto inerte que NAO falha, para nao quebrar imports -- e avisa uma
vez no console. Um stub silencioso seria pior que um erro. Sao eles:

  * LED     -- a placa nao tem LEDs discretos.
  * USB_VCP -- o REPL chega pela ponte CH343; USB nativo nao esta implementado.
  * UART sem mapeamento de pinos (ex.: "YB", a serial do ST-Link).

Consulte `stub_report()` para saber o que foi exercitado sem hardware real.
"""

import machine
from micropython import const

_warned = set()
_used_stubs = set()


def _warn_stub(what):
    _used_stubs.add(what)
    if what not in _warned:
        _warned.add(what)
        print("pyb: '%s' nao existe nesta placa; usando stub inerte" % what)


def stub_report():
    """Nomes de stubs efetivamente usados desde o boot."""
    return sorted(_used_stubs)


# ---------------------------------------------------------------- Pin --------

# O Specter usa nomes de pino do STM32 ("D2" para o gatilho do leitor de QR).
# Esta placa nao tem esses pinos; o mapa fica vazio ate haver periferico
# fisico ligado, e nomes desconhecidos viram stub em vez de excecao.
PIN_MAP = {}


class Pin:
    IN = const(0)
    OUT = const(1)
    PULL_UP = const(2)
    PULL_DOWN = const(3)

    class board:
        pass

    class cpu:
        pass

    def __init__(self, name, mode=OUT, *args, **kwargs):
        self._name = name
        self._pin = None
        gpio = PIN_MAP.get(name)
        if gpio is None:
            _warn_stub("Pin(%r)" % name)
            return
        self._pin = machine.Pin(
            gpio, machine.Pin.OUT if mode == Pin.OUT else machine.Pin.IN
        )

    def on(self):
        if self._pin:
            self._pin.value(1)

    def off(self):
        if self._pin:
            self._pin.value(0)

    def value(self, *args):
        if self._pin:
            return self._pin.value(*args)
        return 0


# --------------------------------------------------------------- UART --------

# Nome do Specter -> (id da UART, tx, rx). A UART0 esta ocupada pelo REPL nos
# GPIO 37/38, entao nao aparece aqui.
UART_MAP = {}


class _NullUART:
    """Porta que aceita escrita e nunca entrega dados."""

    def __init__(self, name):
        self._name = name

    def init(self, *args, **kwargs):
        pass

    def deinit(self):
        pass

    def any(self):
        return 0

    def read(self, *args):
        return None

    def readline(self):
        return None

    def readinto(self, buf, *args):
        return None

    def write(self, data):
        return len(data)


def UART(name, baudrate=9600, **kwargs):
    mapping = UART_MAP.get(name)
    if mapping is None:
        _warn_stub("UART(%r)" % name)
        return _NullUART(name)
    uart_id, tx, rx = mapping
    return machine.UART(uart_id, baudrate=baudrate, tx=tx, rx=rx)


# ---------------------------------------------------------------- LED --------


class LED:
    """Sem LEDs discretos nesta placa. Para feedback visual use o backlight."""

    def __init__(self, number):
        self._number = number
        _warn_stub("LED(%d)" % number)

    def on(self):
        pass

    def off(self):
        pass

    def toggle(self):
        pass


# ------------------------------------------------------------ USB_VCP --------


class USB_VCP:
    RTS = const(1)
    CTS = const(2)

    def __init__(self, *args, **kwargs):
        _warn_stub("USB_VCP")

    def init(self, *args, **kwargs):
        pass

    def isconnected(self):
        return False

    def any(self):
        return False

    def read(self, *args):
        return None

    def readline(self):
        return None

    def write(self, data):
        return len(data)


_usb_mode = None


def usb_mode(*args):
    """Sem USB nativo: o REPL chega pela ponte CH343."""
    global _usb_mode
    if not args:
        return _usb_mode
    _usb_mode = args[0]
    _warn_stub("usb_mode")


# ------------------------------------------------------------- SDCard --------


class SDCard:
    """microSD por SDMMC.

    Pinos D0-D3/CLK/CMD em GPIO 39-44, do board_config do bootloader. O slot
    responde ali -- verificado sondando sem cartao, que chegou ao send_op_cond
    e expirou como esperado. Leitura e escrita com cartao presente ainda nao
    foram exercitadas.
    """

    def __init__(self, slot=0, width=4):
        self._slot = slot
        self._width = width
        self._sd = None

    def _open(self):
        if self._sd is None:
            self._sd = machine.SDCard(slot=self._slot, width=self._width)
        return self._sd

    def present(self):
        try:
            self._open().info()
            return True
        except Exception:
            self._sd = None
            return False

    def power(self, state):
        if not state and self._sd is not None:
            try:
                self._sd.deinit()
            except Exception:
                pass
            self._sd = None
        elif state:
            self._open()

    # Protocolo de block device, para os.mount()
    def readblocks(self, block_num, buf, offset=0):
        return self._open().readblocks(block_num, buf, offset)

    def writeblocks(self, block_num, buf, offset=0):
        return self._open().writeblocks(block_num, buf, offset)

    def ioctl(self, op, arg):
        return self._open().ioctl(op, arg)


# -------------------------------------------------------------- Flash --------


def Flash(*args, **kwargs):
    """Particao de dados que hospeda o sistema de arquivos interno.

    `esp32.Partition` ja implementa o protocolo de block device, entao serve
    diretamente. Note que o `wipe()` do Specter usa indices de bloco do mapa de
    flash do STM32; o caminho de apagamento precisa de logica propria aqui e
    esta em platform.py, nao neste shim.
    """
    import esp32

    return esp32.Partition.find(esp32.Partition.TYPE_DATA, label="vfs")[0]


# ------------------------------------------------------------- diversos ------


def hard_reset():
    machine.reset()


def unique_id():
    return machine.unique_id()


def millis():
    import time

    return time.ticks_ms()


def delay(ms):
    import time

    time.sleep_ms(ms)
