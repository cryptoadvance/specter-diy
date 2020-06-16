"""Base classes for inheritance"""

class KeyStoreError(Exception):
    pass

class PinError(KeyStoreError):
	pass

class KeyStore:
    pass
