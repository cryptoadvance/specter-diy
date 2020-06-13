from bitcoin import bip39
import rng

def gen_mnemonic(num_words):
    """Generates a mnemonic with num_words"""
    if num_words < 12 or num_words > 24 or num_words%3 != 0:
        raise RuntimeError("Invalid word count")
    return bip39.mnemonic_from_bytes(rng.get_random_bytes(num_words*4//3))
