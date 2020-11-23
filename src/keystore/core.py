"""Base classes for inheritance"""
from errors import BaseError


class KeyStoreError(BaseError):
    NAME = "Keystore error"


class PinError(KeyStoreError):
    NAME = "PIN error"


class KeyStore:
    NAME = "Generic Keystore"
    NOTE = "Base class"
    COLOR = "FF9A00"
    path = None
    load_button = None


    @classmethod
    def is_available(cls):
        return True
