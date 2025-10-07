import sys

# Ensure our local modules shadow similarly named stdlib modules (e.g. platform)
sys.path.insert(0, '.')
sys.path.insert(0, '../src')

is_micropython = sys.implementation.name == 'micropython'

if is_micropython:
    sys.path.insert(0, '../f469-disco/libs/common')
    sys.path.insert(0, '../f469-disco/libs/unix')
    sys.path.insert(0, '../f469-disco/usermods/udisplay_f469/display_unixport')
    sys.path.insert(0, '../f469-disco/tests')
else:
    from native_support import setup_native_stubs

    setup_native_stubs()

import unittest

if is_micropython:
    test_module = 'tests'

    def _patch_decoder_module(module_name):
        try:
            module = __import__(module_name, fromlist=['*'])  # type: ignore[call-overload]
        except ImportError:  # pragma: no cover - module absent on particular build
            return

        originals = {}

        def _wrap_pair_result(attr, func):
            def _decoder(*args, **kwargs):
                res = func(*args, **kwargs)

                try:
                    length = len(res)  # type: ignore[arg-type]
                except Exception:  # pragma: no cover - objects without length support
                    return res

                if length >= 3 and 'bech32' in attr.lower():
                    first = None
                    try:
                        first = res[0]  # type: ignore[index]
                    except Exception:  # pragma: no cover - sequence protocol violations
                        first = None
                    if isinstance(first, int):
                        try:
                            return res[1], res[2]  # type: ignore[index]
                        except Exception:  # pragma: no cover - sequence protocol violations
                            return res

                if length > 2:
                    try:
                        return res[0], res[1]  # type: ignore[index]
                    except Exception:  # pragma: no cover - sequence protocol violations
                        return res

                return res

            return _decoder

        for attr in ('bech32_decode', 'bech32m_decode'):
            func = getattr(module, attr, None)
            if func is None:
                continue

            originals[attr] = func
            setattr(module, attr, _wrap_pair_result(attr, func))

        if module_name == 'embit.bech32' and originals:
            decode_func = getattr(module, 'decode', None)
            if decode_func is not None:

                def _decode_wrapper(*args, **kwargs):
                    previous = {}
                    try:
                        for name, original in originals.items():
                            previous[name] = getattr(module, name)
                            setattr(module, name, original)
                        return decode_func(*args, **kwargs)
                    finally:
                        for name, patched in previous.items():
                            setattr(module, name, patched)

                setattr(module, 'decode', _decode_wrapper)

    _patch_decoder_module('embit.bech32')
else:
    test_module = 'tests_native'

try:
    from tests.util import clear_testdir
except ImportError:  # pragma: no cover - MicroPython may not expose package-style imports
    try:
        import platform

        def clear_testdir():
            try:
                platform.delete_recursively('testdir', include_self=True)
            except Exception:
                pass
    except Exception:  # pragma: no cover - fallback for extremely constrained ports
        def clear_testdir():
            pass

clear_testdir()

kwargs = {}
if not is_micropython:
    kwargs['verbosity'] = 2

unittest.main(test_module, **kwargs)
