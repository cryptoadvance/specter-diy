from hashlib import hmac_sha512
from struct import unpack
from bitcoin import bip39
from platform import storage_root, simulator
from rng import get_random_bytes
from ubinascii import hexlify, unhexlify
from micropython import const
import ujson as json
import os
import sys

secret_fname = "%s/%s" % (storage_root, "secret.json")
login_fname = "%s/%s" % (storage_root, "login.json")

class Key:
    key = None
    iv  = None

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
    ATTEMPTS_MAX = const(10)
    counter = ATTEMPTS_MAX

    @staticmethod
    def is_pin_valid():
        assert(Secret.hmac != None)
        hmac_calc = hmac_sha512(Key.key, Secret.secret)
        if hmac_calc != Secret.hmac:
            return False
        return True

    @staticmethod
    def read_counter():
        try:
            with open(login_fname, "r") as f:
                d = json.loads(f.read())
                Pin.counter = d["pin_counter"]
        except:
            Pin.counter = ATTEMPTS_MAX

    @staticmethod
    def save_counter():
        obj = {"pin_counter": Pin.counter}
        try:
            with open(login_fname, "w") as f:
                f.write(json.dumps(obj))
        except:
            # If we cannot save counter, we must not allow pin evaluation - reset.
            alert("Error", "Could not save %s" % login_fname, lambda: sys.exit())

    @staticmethod
    def reset_counter():
        Pin.counter = ATTEMPTS_MAX
        try:
            os.remove(login_fname)
        except:
            alert("Error", "Could not delete %s" % login_fname, lambda: sys.exit())
            
class Factory_settings:
    """
    Recursively delete storage_root directory. Files and folders are excluded
    from deletion if blacklisted.
    """
    blacklist = ['.', '..']

    @staticmethod
    def restore():

        def delete_files_recursively(path, blacklist):
            # unlike listdir, ilistdir is supported by unix and stm32 platform
            files = os.ilistdir(path)

            for _file in files:
                if _file[0] in blacklist:
                    continue
                f = "%s/%s" % (path, _file[0])
                # regular file
                if _file[1] == 0x8000:
                    try:
                        os.remove(f)
                    except:
                        alert("Error", "Could not delete %s" % f)
                # directory
                elif _file[1] == 0x4000:
                    isEmpty = delete_files_recursively(f, blacklist)
                    if isEmpty:
                        try:
                            os.rmdir(f)
                        except:
                            alert("Error", "Could not delete %s" % f)

            files = os.ilistdir(path)
            num_of_files = sum(1 for _ in files)
            if (num_of_files == 2 and simulator) or num_of_files == 0:
                """
                Directory is empty - it contains exactly 2 directories -
                current directory and parent directory (unix) or
                0 directories (stm32)
                """
                return True
            return False

        delete_files_recursively(storage_root, Factory_settings.blacklist)

def antiphishing_word(pin_digit):
    _hmac = hmac_sha512(Secret.secret, pin_digit)
    hmac_num = unpack('<H', bytearray(_hmac[0:8]))[0]
    idx = hmac_num % len(bip39.WORDLIST)
    word = (bip39.WORDLIST[idx])
    return word
