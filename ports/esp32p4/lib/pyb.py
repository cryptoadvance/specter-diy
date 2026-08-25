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


def has_uart(name):
    """A UART `name` existe fisicamente nesta placa?

    Permite que quem monta a lista de perifericos pergunte em vez de descobrir
    por um travamento. O leitor de QR do Specter, por exemplo, marca
    is_configured=True incondicionalmente no fallback de trigger, entao sem
    esta consulta o app apresenta uma tela de scan que nunca recebe nada.
    """
    if name in UART_MAP:
        return True
    # A camera faz o papel do leitor de QR nesta placa.
    return name == QR_SCANNER_UART and _camera_available()


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
        """Pinos por nome de placa. Vazio: esta placa nao usa nomes do STM32."""

    class cpu:
        """Nomes de pino do STM32 que o app referencia literalmente.

        `keystore/javacard/util.py` monta o leitor de smartcard com
        Pin.cpu.A2, .A4, .G10, .C2 e .C5. Sao strings porque nao existem aqui;
        Pin() as trata como nao mapeadas e devolve um stub. Mesma abordagem do
        shim do simulador em f469-disco/libs/unix/pyb.py.
        """

        A2 = "A2"
        A4 = "A4"
        G10 = "G10"
        C2 = "C2"
        C5 = "C5"

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

# Nome que o Specter usa para o leitor de QR. Nesta placa ele e servido pela
# camera, nao por uma UART fisica.
QR_SCANNER_UART = "YA"


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


class CameraUART:
    """UART virtual alimentada pela camera MIPI-CSI.

    O QRHost do Specter le o leitor por `any()` e `read()`, esperando o payload
    terminado por CR. Esta placa nao tem leitor serial, mas tem uma camera --
    entao em vez de alterar o QRHost, entregamos algo com a forma de uma UART.

    Isso preserva de graca toda a logica de protocolo do QRHost: QR animado,
    UR, BBQr, remontagem de partes. Ele nao precisa saber de onde vieram os
    bytes.

    `write()` aceita e descarta: sao comandos de configuracao do scanner serial
    (beep, mira, luz) que nao tem equivalente aqui.
    """

    EOL = b"\r"

    # Lido pelo QRHost.init() para pular a configuracao serial do scanner.
    is_camera = True

    def __init__(self):
        self._pending = b""
        self._started = False

    def _ensure_started(self):
        if self._started:
            return True
        try:
            import camera

            camera.init()
            self._started = True
        except Exception as error:
            print("CameraUART: camera indisponivel:", error)
        return self._started

    def any(self):
        if self._pending:
            return len(self._pending)
        if not self._ensure_started():
            return 0
        try:
            import camera

            payload = camera.scan()
        except Exception:
            return 0
        if payload:
            self._pending = payload + self.EOL
        return len(self._pending)

    def read(self, nbytes=None):
        if not self._pending:
            return None
        if nbytes is None or nbytes >= len(self._pending):
            data, self._pending = self._pending, b""
            return data
        data, self._pending = self._pending[:nbytes], self._pending[nbytes:]
        return data

    def readline(self):
        return self.read()

    def readinto(self, buf, nbytes=None):
        data = self.read(nbytes if nbytes is not None else len(buf))
        if data is None:
            return None
        buf[:len(data)] = data
        return len(data)

    def write(self, data):
        return len(data)

    def init(self, *args, **kwargs):
        pass

    def deinit(self):
        if self._started:
            try:
                import camera

                camera.deinit()
            except Exception:
                pass
            self._started = False


def _camera_available():
    try:
        import camera  # noqa: F401

        return True
    except ImportError:
        return False


def UART(name, baudrate=9600, **kwargs):
    mapping = UART_MAP.get(name)
    if mapping is not None:
        uart_id, tx, rx = mapping
        return machine.UART(uart_id, baudrate=baudrate, tx=tx, rx=rx)
    if name == QR_SCANNER_UART and _camera_available():
        return CameraUART()
    _warn_stub("UART(%r)" % name)
    return _NullUART(name)


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

    # Protocolo de block device SIMPLES, para os.mount().
    #
    # A aridade destes metodos e significativa: o VFS do MicroPython inspeciona
    # quantos argumentos readblocks() aceita para decidir se o dispositivo
    # suporta o protocolo estendido, com deslocamento dentro do bloco. Declarar
    # um parametro `offset` aqui fazia o VFS passa-lo, e machine.SDCard --
    # MP_DEFINE_CONST_FUN_OBJ_3, so (self, block_num, buf) -- recusava:
    #
    #     function takes 3 positional arguments but 4 were given
    #
    # Nao ha o que ganhar em fingir suporte estendido: quem faz o trabalho e o
    # machine.SDCard, e ele e simples.
    def readblocks(self, block_num, buf):
        return self._open().readblocks(block_num, buf)

    def writeblocks(self, block_num, buf):
        return self._open().writeblocks(block_num, buf)

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
