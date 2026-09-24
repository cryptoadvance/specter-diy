"""Shared errors, I/O helpers, and size limits for the PGP package."""

FILE_CHUNK_SIZE = 512
LINE_PROBE_LIMIT = 2000
MAX_PUBLIC_KEY_BYTES = 8192
MAX_RSA_MODULUS_BYTES = 512  # 4096-bit
MAX_RSA_EXPONENT_BYTES = 4
MAX_SD_LIST_FILES = 100

INVALID_PUBLIC_KEY_MSG = "Invalid or unsupported ASCII-armored OpenPGP public key"
UNSUPPORTED_KEY_MSG = (
    "This key seems valid, but we only support Ed25519 and RSA keys."
)
PUBLIC_KEY_TOO_LARGE_MSG = (
    "Public key is too large. We support RSA and Ed25519 keys up to 8KB."
)
INVALID_PGP_DATA_MSG = "Invalid PGP data."
SIG_EXPIRATION_MSG = "Signatures with expiration are not supported."


class PGPError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class PGPBinaryError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or INVALID_PUBLIC_KEY_MSG)


class PGPInvalidKeyError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or INVALID_PUBLIC_KEY_MSG)


class PGPUnsupportedKeyError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or UNSUPPORTED_KEY_MSG)


class PGPDecodeArmorError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or "Invalid ASCII armor.")


class PGPKeyTooLargeError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or PUBLIC_KEY_TOO_LARGE_MSG)


class PGPParseError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or INVALID_PGP_DATA_MSG)


class PGPInvalidSignatureError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or "Invalid PGP signature.")


class PGPSignatureExpirationError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or SIG_EXPIRATION_MSG)


class PGPUnknownHashError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(
            message
            or "Unknown hash format. We only support SHA256 and SHA512 signed messages."
        )


class PGPPublicKeyAsSignatureError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(
            message or "This file is a public key, not a signed message."
        )


class PGPOtherKeyError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(
            message or "This signature was made by a different key."
        )


class PGPBadMatchError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(
            message
            or "The signature claims to be from this key, but it does not match."
        )


class PGPMissingFileError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(message or "Missing companion file.")


class PGPSlashInFilenameError(PGPError):
    def __init__(self, message: str = None):
        super().__init__(
            message or "Checksum filenames must not contain '/'."
        )


def contains_non_ascii(data: bytes) -> bool:
    for byte in data:
        if byte > 127:
            return True
    return False


def iter_file_chunks(path: str, chunk_size: int = FILE_CHUNK_SIZE) -> "Iterator[bytes]":
    """Yield successive bytes chunks from a file."""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


def iter_crlf_normalized_bytes(chunks: "Iterator[bytes]") -> "Iterator[bytes]":
    """Yield bytes with CRLF and lone CR converted to LF.

    A chunk-ending CR is held until the next chunk (or EOF) so CRLF that
    straddles a boundary is not turned into two newlines.
    """
    pending_cr = False
    for chunk in chunks:
        if not chunk:
            continue
        if pending_cr:
            if chunk[0] == 0x0A:  # \n
                yield b"\n"
                chunk = chunk[1:]
            else:
                yield b"\n"
            pending_cr = False
            if not chunk:
                continue
        if chunk[-1] == 0x0D:  # \r
            pending_cr = True
            chunk = chunk[:-1]
            if not chunk:
                continue
        yield chunk.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if pending_cr:
        yield b"\n"


def basename(path: str) -> str:
    name = path.replace("\\", "/")
    if "/" in name:
        name = name.split("/")[-1]
    return name


def companion_filename(path: str) -> str:
    name = basename(path)
    if "." not in name:
        raise PGPMissingFileError("Cannot find companion file for %s" % name)
    return name.rsplit(".", 1)[0]
