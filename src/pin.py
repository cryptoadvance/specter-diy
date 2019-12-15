from hashlib import hmac_sha512
from struct import unpack
from bitcoin import bip39
from platform import storage_root
from rng import get_random_bytes
from ubinascii import hexlify, unhexlify
import ujson as json

secret_fname = "%s/%s" % (storage_root, "secret.json")

class Key:
    key = None

    @staticmethod
    def generate_key(user_pin):
        Key.key = hmac_sha512(Secret.secret, user_pin)[0:32]

class Secret:
    secret = None
    hmac   = None

    @staticmethod
    def load_secret():
        try:
            with open(secret_fname, "r") as f:
                d = json.loads(f.read())
        except:
            return False
        Secret.secret = unhexlify(d["secret"])
        Secret.hmac = unhexlify(d["hmac"])
        return True

    @staticmethod
    def generate_secret():
        Secret.secret = get_random_bytes(32)

    @staticmethod
    def save_secret():
        Secret.hmac = hmac_sha512(Key.key, Secret.secret)
        with open(secret_fname, "w") as f:
            f.write('{"secret":"%s", "hmac":"%s"}' % \
                    (hexlify(Secret.secret).decode('utf-8'), \
                     hexlify(Secret.hmac).decode('utf-8')))

class Pin:
    @staticmethod
    def is_pin_valid():
        assert(Secret.hmac != None)
        hmac_calc = hmac_sha512(Key.key, Secret.secret)
        if hmac_calc != Secret.hmac:
            return False
        return True
