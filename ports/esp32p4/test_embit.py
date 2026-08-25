"""Vetores oficiais do BIP84 rodando na placa.

    ports/esp32p4/tools/push.py ports/esp32p4/test_embit.py:/test_embit.py "import test_embit"

Valores retirados de bitcoin/bips, bip-0084.mediawiki, secao Test vectors.
Exercitam a cadeia inteira: PBKDF2-HMAC-SHA512 (BIP39), HMAC-SHA512 e
derivacao (BIP32), secp256k1 (chaves publicas) e SHA256+RIPEMD160 (enderecos).
"""

from embit import bip32, bip39, script
from embit.networks import NETWORKS

MNEMONIC = "abandon " * 11 + "about"

EXPECTED = {
    "rootpriv": "zprvAWgYBBk7JR8Gjrh4UJQ2uJdG1r3WNRRfURiABBE3RvMXYSrRJL62Xue"
                "zvGdPvG6GFBZduosCc1YP5wixPox7zhZLfiUm8aunE96BBa4Kei5",
    "rootpub": "zpub6jftahH18ngZxLmXaKw3GSZzZsszmt9WqedkyZdezFtWRFBZqsQH5hy"
               "Umb4pCEeZGmVfQuP5bedXTB8is6fTv19U1GQRyQUKQGUTzyHACMF",
    "acct_xpub": "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3E"
                 "fH1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs",
    "addr_0_0": "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu",
    "addr_0_1": "bc1qnjg0jd8228aq7egyzacy8cys3knf9xvrerkf9g",
    "addr_1_0": "bc1q8c6fshw2dlwun7ekn9qwf37cu2rn755upcp6el",
    "pubkey_0_0": "0330d54fd0dd420a6e5f8d3624f5f3482cae350f79d5f0753bf5beef9c2d91af3c",
}


def _check(results, name, got):
    expected = EXPECTED[name]
    ok = got == expected
    results.append(ok)
    print("%-7s %-11s %s" % ("OK" if ok else "FALHOU", name, got[:52]))
    if not ok:
        print("        esperado    %s" % expected[:52])


def run():
    results = []
    seed = bip39.mnemonic_to_seed(MNEMONIC)
    root = bip32.HDKey.from_seed(seed)

    version_priv = NETWORKS["main"]["zprv"]
    version_pub = NETWORKS["main"]["zpub"]

    _check(results, "rootpriv", root.to_base58(version=version_priv))
    _check(results, "rootpub", root.to_public().to_base58(version=version_pub))

    account = root.derive("m/84h/0h/0h")
    _check(results, "acct_xpub", account.to_public().to_base58(version=version_pub))

    first = account.derive("m/0/0")
    _check(results, "pubkey_0_0", first.get_public_key().sec().hex())

    for name, path in (("addr_0_0", "m/0/0"), ("addr_0_1", "m/0/1"),
                       ("addr_1_0", "m/1/0")):
        key = account.derive(path)
        addr = script.p2wpkh(key.get_public_key()).address(NETWORKS["main"])
        _check(results, name, addr)

    print("\n%d de %d vetores conferem" % (sum(results), len(results)))
    return all(results)


run()
