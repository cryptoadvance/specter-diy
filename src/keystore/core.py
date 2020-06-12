class KeyStoreError(Exception):
    pass

class PinError(KeyStoreError):
	pass

class KeyStore:
    STATUS_SETUP    = 2 # PIN is not set
    STATUS_LOCKED   = 3 # PIN is set but not entered
    STATUS_UNLOCKED = 4 # normal operation
    STATUS_BLOCKED  = 5 # no PIN attempts left - permanently blocked
    STATUS_ERROR    = 6 # something bad happened
