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
            for entry in os.scandir(path):
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
            setattr(screens, _name, type(_name, (), {}))

    _ensure_submodule("gui.screens", "mnemonic", {
        "ExportMnemonicScreen": type("ExportMnemonicScreen", (), {}),
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
