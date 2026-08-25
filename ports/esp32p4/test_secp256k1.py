"""Vetores de teste do secp256k1 na placa.

    mpremote cp ports/esp32p4/test_secp256k1.py :test_secp256k1.py
    mpremote exec "import test_secp256k1; test_secp256k1.run()"

Os valores esperados sao constantes publicas e verificaveis:
o ponto gerador da curva e o vetor 0 do BIP340
(bitcoin/bips, bip-0340/test-vectors.csv).
"""

import ubinascii as b2a

import secp256k1

GENERATOR = "0279BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798"

# BIP340 test vector 0
BIP340_SECKEY = "00" * 31 + "03"
BIP340_XONLY = "F9308A019258C31049344F85F89D5229B531C845836F99B08601F113BCE036F9"
BIP340_SIG = (
    "E907831F80848D1069A5371B402410364BDF1C5F8307B0084C55F1CE2DCA8215"
    "25F66A4A85EA8B71E482A74F382D2CE5EBEEE8FDB2172F477DF4900D310536C0"
)


def _hex(data):
    return b2a.hexlify(data).decode().upper()


def test_generator():
    """Chave privada 1 deve produzir exatamente o ponto gerador."""
    seckey = bytes(31) + b"\x01"
    pubkey = secp256k1.ec_pubkey_create(seckey)
    got = _hex(secp256k1.ec_pubkey_serialize(pubkey, secp256k1.EC_COMPRESSED))
    assert got == GENERATOR, got
    return got


def test_ecdsa():
    """Assina, verifica, e confirma que a mensagem errada e rejeitada."""
    seckey = bytes(31) + b"\x01"
    pubkey = secp256k1.ec_pubkey_create(seckey)
    message = bytes(range(32))
    signature = secp256k1.ecdsa_sign(message, seckey)
    assert secp256k1.ecdsa_verify(signature, message, pubkey)
    assert not secp256k1.ecdsa_verify(signature, bytes(32), pubkey)
    return _hex(secp256k1.ecdsa_signature_serialize_der(signature))


def test_bip340_pubkey():
    seckey = bytes.fromhex(BIP340_SECKEY)
    pubkey = secp256k1.ec_pubkey_create(seckey)
    compressed = _hex(secp256k1.ec_pubkey_serialize(pubkey, secp256k1.EC_COMPRESSED))
    # O byte de prefixo e descartado: BIP340 usa a coordenada x sozinha.
    assert compressed[2:] == BIP340_XONLY, compressed
    return compressed


def test_bip340_signature():
    """A assinatura deve bater com o vetor oficial byte a byte.

    Nota sobre a API: xonly_pubkey_from_pubkey() devolve uma tupla cujo
    primeiro item e a struct interna de 64 bytes do libsecp256k1, nao a chave
    x-only serializada de 32 bytes. Compare sempre pela pubkey comprimida.
    """
    seckey = bytes.fromhex(BIP340_SECKEY)
    keypair = secp256k1.keypair_create(seckey)
    xonly = secp256k1.xonly_pubkey_from_pubkey(secp256k1.ec_pubkey_create(seckey))[0]
    message = bytes(32)
    signature = secp256k1.schnorrsig_sign(message, keypair)
    assert secp256k1.schnorrsig_verify(signature, message, xonly)
    got = _hex(signature)
    assert got == BIP340_SIG, got
    return got


def run():
    for name, test in (
        ("ponto gerador", test_generator),
        ("ECDSA sign/verify", test_ecdsa),
        ("BIP340 pubkey", test_bip340_pubkey),
        ("BIP340 assinatura", test_bip340_signature),
    ):
        try:
            value = test()
            print("OK     %-20s %s" % (name, value[:48]))
        except Exception as error:  # noqa: BLE001 - relatorio, nao propagacao
            print("FALHOU %-20s %r" % (name, error))
