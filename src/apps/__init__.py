__all__ = [
    "wallets",  # wallet manager, main app for bitcoin tx stuff
    "xpubs",  # master public keys and device fingerprint
    "signmessage",  # adds bitcoin message signing functionality
    "getrandom",  # allows to query random bytes from on-board TRNG
    "label",  # allows settings and getting a label for device
    "backup", # creates and loads backups (only loads for now)
    "blindingkeys", # blinding keys for liquid wallets
    "compatibility", # compatibility layer that converts json/files to Specter format
]
