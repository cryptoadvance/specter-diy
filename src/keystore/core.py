"""Base classes for inheritance"""
from errors import BaseError


class KeyStoreError(BaseError):
    NAME = "Keystore error"


class PinError(KeyStoreError):
    NAME = "PIN error"


class KeyStore:
    pass
