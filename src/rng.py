# random number generator
# if os.urandom is available - entropy goes from TRNG
# otherwise - use whatever we have
# FIXME: mix in extra entropy
try:
    from os import urandom as get_random_bytes
except:
    # read /dev/urandom instead?
    import urandom, time
    urandom.seed(int(time.time()))
    def get_random_bytes(nbytes):
        return bytes([urandom.getrandbits(8) for i in range(nbytes)])
