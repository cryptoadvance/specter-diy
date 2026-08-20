import os
import sys
import types


def _ensure_module(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _ensure_submodule(package, name, attrs):
    full_name = f"{package}.{name}"
    module = _ensure_module(full_name)
    for attr, value in attrs.items():
        if not hasattr(module, attr):
            setattr(module, attr, value)
    parent = _ensure_module(package)
    if not hasattr(parent, "__path__"):
        parent.__path__ = []
    setattr(parent, name, module)
    return module

# The setup_native_stubs() function creates mock/stub implementations of 
# MicroPython-specific modules that don't exist in regular Python
def setup_native_stubs():
    if sys.implementation.name == 'micropython':
        return

    if not hasattr(os, "ilistdir"):
        def _ilistdir(path):
            # scandir() as a context manager, so abandoning the iterator
            # early (as a caller enforcing an entry limit does) still
            # releases the directory handle instead of leaking it.
            with os.scandir(path) as entries:
                for entry in entries:
                    mode = 0x4000 if entry.is_dir() else 0x8000
                    yield (entry.name, mode, 0, 0)
        os.ilistdir = _ilistdir

    pyb = _ensure_module("pyb")
    if not hasattr(pyb, "SDCard"):
        class _DummySDCard:
            def __init__(self, *args, **kwargs):
                pass

            def present(self):
                return True

            def power(self, value):
                pass

        class _DummyLED:
            def __init__(self, *args, **kwargs):
                pass

            def on(self):
                pass

            def off(self):
                pass

        pyb.SDCard = _DummySDCard
        pyb.LED = _DummyLED
        pyb.usb_mode = lambda *args, **kwargs: None
        pyb.UART = lambda *args, **kwargs: None
        pyb.USB_VCP = lambda *args, **kwargs: None

    lvgl = _ensure_module("lvgl")
    if not hasattr(lvgl, "SYMBOL"):
        class _Symbol:
            EDIT = "[edit]"
            TRASH = "[trash]"

            def __getattr__(self, name):
                return f"[{name.lower()}]"

        lvgl.SYMBOL = _Symbol()

    display = _ensure_module("display")
    if not hasattr(display, "Screen"):
        display.Screen = type("Screen", (), {})

    gui = _ensure_module("gui")
    if not hasattr(gui, "__path__"):
        gui.__path__ = []

    class _StubScreen:
        """Stand-in for a real lvgl-backed Screen class: accepts the same
        positional/keyword args the flexible real constructors take, and
        exposes the kwargs as attributes so tests can inspect what a screen
        was constructed with.

        Deliberately permissive about *what* it accepts (real screen
        constructors vary widely, and this one stub covers many of them),
        but records the full construction call in __repr__ so a test that
        passes the wrong args to a screen can be diagnosed from a failure
        message instead of silently producing an opaque <_StubScreen obj>.
        Also rejects container types (list/dict/set) as positional args,
        which no real screen constructor in this codebase accepts - those
        almost always indicate a test wiring bug rather than a screen that
        happens to take a list of titles."""

        def __init__(self, *args, **kwargs):
            for a in args:
                if isinstance(a, (list, dict, set)):
                    raise TypeError(
                        "%s: positional arg %r is a %s, which no real screen "
                        "constructor accepts - likely a test wiring bug"
                        % (type(self).__name__, a, type(a).__name__)
                    )
            self.args = args
            self.kwargs = kwargs
            for _k, _v in kwargs.items():
                setattr(self, _k, _v)

        def __repr__(self):
            cls = type(self).__name__
            args_repr = ", ".join(repr(a) for a in self.args)
            kwargs_repr = ", ".join(
                "%s=%r" % (k, v) for k, v in self.kwargs.items()
            )
            all_args = ", ".join(x for x in [args_repr, kwargs_repr] if x)
            return "%s(%s)" % (cls, all_args)

    screens = _ensure_module("gui.screens")
    if not hasattr(screens, "__path__"):
        screens.__path__ = []
    for _name in [
        "Menu",
        "InputScreen",
        "Prompt",
        "TransactionScreen",
        "WalletScreen",
        "ConfirmWalletScreen",
        "QRAlert",
        "Alert",
        "PinScreen",
        "DerivationScreen",
        "NumericScreen",
        "MnemonicScreen",
        "NewMnemonicScreen",
        "RecoverMnemonicScreen",
        "Progress",
        "DevSettings",
    ]:
        if not hasattr(screens, _name):
            setattr(screens, _name, type(_name, (_StubScreen,), {}))

    _ensure_submodule("gui.screens", "mnemonic", {
        "ExportMnemonicScreen": type("ExportMnemonicScreen", (_StubScreen,), {}),
        "MnemonicPrompt": type("MnemonicPrompt", (_StubScreen,), {}),
    })
    _ensure_submodule("gui.screens", "settings", {
        "HostSettings": type("HostSettings", (), {}),
    })
    _ensure_submodule("gui.screens", "screen", {
        "Screen": type("Screen", (), {}),
    })
    _ensure_submodule("gui.screens", "qralert", {
        "QRAlert": type("QRAlert", (), {}),
    })

    common = _ensure_module("gui.common")
    if not hasattr(common, "HOR_RES"):
        common.HOR_RES = 480
    if not hasattr(common, "styles"):
        common.styles = types.SimpleNamespace()
    for _name in [
        "add_label",
        "add_button",
        "add_button_pair",
        "align_button_pair",
        "format_addr",
    ]:
        if not hasattr(common, _name):
            setattr(common, _name, lambda *args, **kwargs: None)

    decorators = _ensure_module("gui.decorators")
    if not hasattr(decorators, "on_release"):
        decorators.on_release = lambda func: func

    ucryptolib = _ensure_module("ucryptolib")
    if not hasattr(ucryptolib, "aes"):
        class _DummyAES:
            def __init__(self, key, mode, iv):
                self.key = key
                self.mode = mode
                self.iv = iv

            def encrypt(self, data):
                return data

            def decrypt(self, data):
                return data

        ucryptolib.aes = lambda key, mode, iv: _DummyAES(key, mode, iv)

    bcur = _ensure_module("bcur")
    if not hasattr(bcur, "bcur_decode_stream"):
        bcur.bcur_decode_stream = lambda stream: stream

    # microur lives in the f469-disco submodule (libs/common/microur), which
    # the native-tests CI job does not check out. Importing specter pulls it
    # in transitively via hosts -> hosts.qr, so stub it here. Only the names
    # actually imported by src/ are provided; anything that really exercises
    # UR decoding belongs in the MicroPython test suite, not here.
    if "microur" not in sys.modules:
        microur = _ensure_module("microur")
        microur.__path__ = []
        _ensure_submodule("microur", "decoder", {
            "FileURDecoder": type("FileURDecoder", (), {}),
        })
        _ensure_submodule("microur", "encoder", {
            "UREncoder": type("UREncoder", (), {}),
        })
        util = _ensure_submodule("microur", "util", {})
        util.__path__ = []
        _ensure_submodule("microur.util", "cbor", {})
        _ensure_submodule("microur.util", "bytewords", {
            "stream_pos": lambda *args, **kwargs: 0,
        })
        # hosts/qr.py does `from microur.util import cbor`
        setattr(sys.modules["microur.util"], "cbor", sys.modules["microur.util.cbor"])

    secp256k1 = _ensure_module("secp256k1")
    if not hasattr(secp256k1, "EC_UNCOMPRESSED"):
        secp256k1.EC_UNCOMPRESSED = 0
        secp256k1.ec_pubkey_parse = lambda data: data
        secp256k1.ec_pubkey_create = lambda secret: secret
        secp256k1.ec_pubkey_serialize = lambda pub, flag=0: b"\x04" + bytes(64)
        secp256k1.ec_pubkey_tweak_mul = lambda pub, secret: None
        secp256k1.ecdsa_signature_parse_der = lambda raw: raw
        secp256k1.ecdsa_signature_normalize = lambda sig: sig
        secp256k1.ecdsa_verify = lambda sig, msg, pub: True
        secp256k1.ecdsa_sign_recoverable = lambda msghash, secret: bytes(65)

    utime = _ensure_module("utime")
    if not hasattr(utime, "time"):
        import time as _time
        utime.time = _time.time
        utime.sleep = _time.sleep
        utime.sleep_ms = lambda ms: _time.sleep(ms / 1000.0)
        utime.sleep_us = lambda us: _time.sleep(us / 1000000.0)
        utime.ticks_ms = lambda: int(_time.time() * 1000)
        utime.ticks_us = lambda: int(_time.time() * 1000000)
        utime.ticks_add = lambda ticks, delta: ticks + delta
        utime.ticks_diff = lambda ticks1, ticks2: ticks1 - ticks2
        utime.mktime = _time.mktime
        utime.localtime = _time.localtime
        utime.gmtime = _time.gmtime

    from app import BaseApp

    if not hasattr(BaseApp, "_native_original_get_prefix"):
        BaseApp._native_original_get_prefix = BaseApp.get_prefix

        def _native_get_prefix(self, stream):
            pos = stream.tell()
            prefix = BaseApp._native_original_get_prefix(self, stream)
            if prefix is not None:
                prefixes = getattr(self, 'prefixes', None)
                if prefixes and prefix not in prefixes:
                    stream.seek(pos)
                    return None
            return prefix

        BaseApp.get_prefix = _native_get_prefix

    try:
        import embit.util
        from apps.wallets.wallet import Wallet as _Wallet
    except ModuleNotFoundError as exc:
        if exc.name.startswith("embit"):
            raise ModuleNotFoundError(
                "Native test suite requires the 'embit' package. "
                "Install it with 'pip install -r test/integration/requirements.txt'."
            ) from exc
        raise

    if not hasattr(_Wallet, '_native_original_from_descriptor'):
        _Wallet._native_original_from_descriptor = _Wallet.from_descriptor

        def _native_from_descriptor(cls, desc: str, path):
            desc = desc.split('#')[0].replace(' ', '')
            descriptor = cls.DescriptorClass.from_string(desc)
            return cls(descriptor, path)

        _Wallet.from_descriptor = classmethod(_native_from_descriptor)
