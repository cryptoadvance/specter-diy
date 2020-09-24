"""Base classes for inheritance"""
from errors import BaseError


class KeyStoreError(BaseError):
    NAME = "Keystore error"


class PinError(KeyStoreError):
    NAME = "PIN error"


class KeyStore:
    NAME = "Generic Keystore"
    NOTE = "Base class"
    path = None
    load_button = None
