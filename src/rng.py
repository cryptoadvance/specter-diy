# random number generator
# if os.urandom is available - entropy goes from TRNG
# otherwise - use whatever we have
# FIXME: mix in extra entropy
try:
    from os import urandom as get_random_bytes
except:
    import urandom
    def get_random_bytes(nbytes):
        return bytes([urandom.getrandbits(8) for i in range(nbytes)])
