"""Testes da camada de plataforma na placa: pyb, sdram, hashes e RNG.

    ports/esp32p4/tools/push.py ports/esp32p4/lib/pyb.py:/pyb.py \\
        ports/esp32p4/lib/sdram.py:/sdram.py \\
        ports/esp32p4/test_platform.py:/test_platform.py "import test_platform"

Os valores esperados sao publicos e verificaveis: RFC 4231 para HMAC, os
digests classicos de "abc", e a semente BIP39 do mnemonico de teste.
"""

import binascii
import hashlib
import os

VECTORS = (
    ("sha256 abc", lambda: hashlib.sha256(b"abc").digest(),
     "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    ("sha512 abc", lambda: hashlib.sha512(b"abc").digest()[:32],
     "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"),
    ("ripemd160 abc", lambda: hashlib.ripemd160(b"abc").digest(),
     "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc"),
    # RFC 4231, caso de teste 1
    ("hmac-sha512", lambda: hashlib.hmac_sha512(b"\x0b" * 20, b"Hi There")[:32],
     "87aa7cdea5ef619d4ff0b4241a1d6cb02379f4e2ce4ec2787ad0b30545e17cde"),
    # BIP39 com passphrase VAZIA. O vetor oficial usa "TREZOR" e da um valor
    # diferente; confundir os dois gera um falso negativo convincente.
    ("bip39 seed", lambda: hashlib.pbkdf2_hmac(
        "sha512",
        b"abandon " * 11 + b"about",
        b"mnemonic", 2048, 64)[:32],
     "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc1"),
)


def test_hashes():
    for name, run, expected in VECTORS:
        got = binascii.hexlify(run()).decode()
        print("%-7s %-14s %s" % ("OK" if got == expected else "FALHOU", name, got))


def test_trng():
    """Nao mede qualidade criptografica -- pega um TRNG morto ou travado."""
    sample = os.urandom(4096)
    ones = sum(bin(byte).count("1") for byte in sample)
    distinct = len(set(sample))
    ratio = ones / (len(sample) * 8)
    healthy = 0.45 < ratio < 0.55 and distinct > 240
    print("%-7s %-14s %.3f de bits em 1, %d valores distintos"
          % ("OK" if healthy else "SUSPEITO", "trng", ratio, distinct))


def test_platform():
    import platform

    assert not platform.simulator and platform.esp32
    print("%-7s %-14s boot=%s prot=%s/%s usb=%s"
          % ("OK", "platform",
             platform.get_firmware_boot_mode(),
             platform.get_flash_read_protection_status(),
             platform.get_flash_write_protection_status(),
             platform.usb_connected()))


def test_ramdisk():
    import platform

    path = platform.mount_sdram()
    with open(path + "/scratch.bin", "wb") as handle:
        handle.write(os.urandom(64))
    ok = os.listdir(path) == ["scratch.bin"]
    os.umount(path)
    print("%-7s %-14s %s" % ("OK" if ok else "FALHOU", "ramdisk", path))


def test_stubs():
    import pyb

    print("%-7s %-14s %s" % ("INFO", "stubs", pyb.stub_report() or "nenhum"))


def run():
    test_hashes()
    test_trng()
    test_platform()
    test_ramdisk()
    test_stubs()


run()
