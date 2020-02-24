# random number generator
# if os.urandom is available - entropy goes from TRNG
# in simulator just use whatever we have
import hashlib
entropy_pool = b'7'*64

try:
    from os import urandom as get_trng_bytes
except:
    # read /dev/urandom instead?
    def get_trng_bytes(nbytes):
        with open("/dev/urandom","rb") as f:
            return f.read(nbytes)

# assuming that entropy_pool has some real entropy
# we can generate bytes using it as well
# probably not the best way at the moment, 
# but anything is better than nothing
def get_random_bytes(nbytes):
    global entropy_pool
    d = get_trng_bytes(nbytes)
    feed(d) # why not?
    # if more than 64 - just do trng
    if nbytes > 64:
        return d
    else:
        h = hashlib.sha512(entropy_pool)
        h.update(d)
        return h.digest()[:nbytes]

# we hash together entropy pool and data we got
def feed(data):
    global entropy_pool
    h = hashlib.sha512(entropy_pool)
    h.update(data)
    entropy_pool = h.digest()
