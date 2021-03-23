import sys
import os
from embit import compact, ec
import hashlib

# We will use multisig later on
priv = ec.PrivateKey(b"1"*32)

# Later we will probably switch to bitcoin message signing and bech32 encoding
def tagged_hash(tag: str, data: bytes) -> bytes:
    """BIP-Schnorr tag-specific key derivation"""
    hashtag = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(hashtag + hashtag + data).digest()

def main():
    if len(sys.argv) != 2:
        print("usage: %s /path/to/file.mpy" % sys.argv[0])
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.isfile(path):
        print("%s is not a file" % path)
        sys.exit(1)
    if not path.endswith(".mpy"):
        print("%s is not an .mpy file" % path)
        sys.exit(1)
    with open(path, "rb") as f:
        raw = f.read()
    hsh = hashlib.sha256(raw).digest()
    msg = tagged_hash("diyapp", hsh)
    sig = priv.sign(msg)
    der = sig.serialize()

    with open(path.replace(".mpy", ".mapp"), "wb") as f:
        f.write(b"importapp ")
        # 1 signature
        f.write(compact.to_bytes(1))
        # sig len
        f.write(compact.to_bytes(len(der)))
        # sig
        f.write(der)
        # len app
        f.write(compact.to_bytes(len(raw)))
        # app itself
        f.write(raw)

if __name__ == '__main__':
    main()