from bitcoin import bip39, compact
import hashlib, hmac
from ucryptolib import aes
from io import BytesIO
import rng

AES_BLOCK = 16
IV_SIZE   = 16
AES_CBC   = 2

def gen_mnemonic(num_words:int)->str:
    """Generates a mnemonic with num_words"""
    if num_words < 12 or num_words > 24 or num_words%3 != 0:
        raise RuntimeError("Invalid word count")
    return bip39.mnemonic_from_bytes(rng.get_random_bytes(num_words*4//3))

def tagged_hash(tag:str, data:bytes)->bytes:
    """BIP-Schnorr tag-specific key derivation"""
    hashtag = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(hashtag+hashtag+data).digest()

def encrypt(plain:bytes, key:bytes)->bytes:
    """Encrypt data with bit padding (0x80...)"""
    iv = rng.get_random_bytes(IV_SIZE)
    crypto = aes(key, AES_CBC, iv)
    # encrypted data should be mod 16 (blocksize)
    # add padding
    plain += b'\x80'
    if len(plain) % AES_BLOCK != 0:
        # fill with zeroes
        plain += b"\x00"*(AES_BLOCK-(len(plain) % AES_BLOCK))
    return iv+crypto.encrypt(plain)

def decrypt(ct:bytes, key:bytes)->bytes:
    """Decrypt data and remove AES_CBC 80... padding"""
    iv = ct[:IV_SIZE]
    ct = ct[IV_SIZE:]
    # 2 - MODE_CBC
    crypto = aes(key, AES_CBC, iv)
    plain = crypto.decrypt(ct)
    # remove padding: 
    # split
    arr = plain.split(b"\x80")
    # remove last element and check it's all zeroes
    last = arr.pop()
    assert last == b"\x00"*len(last)
    # join all but last
    return b"\x80".join(arr)

def aead_encrypt(key:bytes, adata:bytes, plaintext:bytes)->bytes:
    """
    Encrypts and authenticates with associated data using key k.
    output format: <compact-len:associated data><iv><ct><hmac>
    """
    aes_key = tagged_hash("aes", key)
    hmac_key = tagged_hash("hmac", key)
    data = compact.to_bytes(len(adata))
    # if there is not ct - just add hmac
    if len(plaintext) > 0:
        data += encrypt(plaintext, aes_key)
    mac = hmac.new(hmac_key, msg=data, digestmod="sha256").digest()
    return data+mac

def aead_decrypt(ciphertext:bytes, key:bytes)->tuple:
    """
    Verifies MAC and decrypts ciphertext with associated data.
    Inverse to aead_encrypt
    Returns a tuple adata, plaintext
    """
    mac = ciphertext[-32:]
    ct = ciphertext[:-32]

    aes_key = tagged_hash("aes", key)
    hmac_key = tagged_hash("hmac", key)
    assert mac == hmac.new(hmac_key, msg=ct, digestmod="sha256").digest()
    b = BytesIO(ct)
    l = compact.read_from(b)
    adata = b.read(l)
    assert len(adata)==l
    ct = b.read()
    if len(ct)==0:
        return adata, b""
    return adata, decrypt(ct, aes_key)