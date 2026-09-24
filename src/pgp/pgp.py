# OpenPGP public-key loading and signature verification (verify-only).
#
# Canonical text (signature type 0x01) strips trailing whitespace and uses
# CRLF line endings; a terminating newline is a line separator, not an extra
# blank line (GnuPG clearsign behavior).

from .base import (
    LINE_PROBE_LIMIT,
    MAX_PUBLIC_KEY_BYTES,
    PGPBinaryError,
    PGPError,
    PGPInvalidKeyError,
    PGPInvalidSignatureError,
    PGPKeyTooLargeError,
    PGPMissingFileError,
    PGPParseError,
    PGPPublicKeyAsSignatureError,
    PGPSignatureExpirationError,
    PGPUnknownHashError,
    PGPUnsupportedKeyError,
    basename,
    companion_filename,
    contains_non_ascii,
    iter_crlf_normalized_bytes,
)
from .checksums import PayloadClassifier
from .codec import (
    BEGIN_PUBLIC_KEY,
    BEGIN_SIGNATURE,
    BEGIN_SIGNED_MESSAGE,
    END_SIGNATURE,
    FLAG_SIGN,
    HASH_ALGOS,
    HASH_HEADER,
    SIG_TYPE_BINARY,
    SIG_TYPE_CERT_GENERIC,
    SIG_TYPE_CERT_POSITIVE,
    SIG_TYPE_CERT_REVOCATION,
    SIG_TYPE_DIRECT_KEY,
    SIG_TYPE_KEY_REVOCATION,
    SIG_TYPE_PRIMARY_BINDING,
    SIG_TYPE_SUBKEY_BINDING,
    SIG_TYPE_SUBKEY_REVOCATION,
    SIG_TYPE_TEXT,
    TAG_MARKER,
    TAG_PADDING,
    TAG_PUBLIC_KEY,
    TAG_PUBLIC_SUBKEY,
    TAG_SIGNATURE,
    TAG_USER_ATTR,
    TAG_USER_ID,
    Signature,
    check_sig,
    decode_armor,
    fingerprint,
    issuer_match,
    key_creation_time,
    parse_armored_signature,
    parse_signature_packet,
    parse_supported_key,
    read_packet,
    signature_trailer,
    verify_signature,
)

CLEARSIGN = "clearsign"
DETACHED = "detached"

SIG_INVALID_MSG = "Invalid PGP signature."
SIG_TOO_LARGE_MSG = "Signed message is too large to verify."

MAX_SIGNATURE_BYTES = 8192
PROBE_HEADER_LEN = len(BEGIN_PUBLIC_KEY)


def load_ascii_armored_public_key(chunks: "Iterator[bytes]") -> tuple:
    """
    Decode an ASCII-armored OpenPGP public key from an iterator of bytes
    chunks and return (fingerprint_bytes, signing_keys, expires_at).

    fingerprint_bytes is the primary key fingerprint. signing_keys is a
    non-empty list of (fingerprint, key_type, key) for every key that
    may sign documents: the primary if it has the Sign flag, plus each
    signing subkey with a valid binding (and backsig). Encryption
    subkeys are ignored. SHA-1, unverifiable bindings, expiring
    self-signatures or bindings, and any revocation or designated
    revoker are rejected.
    expires_at is the earliest key/subkey expiration as a Unix time, or
    None if none expire.
    """
    acc = []
    total = 0
    header_ok = False
    begin_len = len(BEGIN_PUBLIC_KEY)
    for piece in iter_crlf_normalized_bytes(chunks):
        try:
            text = piece.decode("ascii")
        except Exception:
            raise PGPBinaryError()
        acc.append(text)
        total += len(text)
        if total > MAX_PUBLIC_KEY_BYTES:
            raise PGPKeyTooLargeError()
        if not header_ok:
            joined = "".join(acc)
            lstripped = joined.lstrip()
            if len(lstripped) > begin_len or total > LINE_PROBE_LIMIT:
                if not lstripped.startswith(BEGIN_PUBLIC_KEY):
                    raise PGPInvalidKeyError()
                header_ok = True
                acc = [lstripped]
                total = len(lstripped)
    joined = "".join(acc)
    if header_ok:
        lstripped = joined
    else:
        lstripped = joined.lstrip()
        if not lstripped.startswith(BEGIN_PUBLIC_KEY):
            raise PGPInvalidKeyError()

    packets = decode_armor(lstripped)
    return collect_signing_keys(packets)


def verify_signed_checksums(
    signing_keys: list,
    sig_factory,
    companion_factory=None,
    fname: str = "",
) -> tuple:
    """
    Verify an ASCII-armored clearsigned or detached signature.

    signing_keys is a non-empty list of (fingerprint, key_type, key)
    from load_ascii_armored_public_key. sig_factory and companion_factory
    re-open the file so the payload can be classified after hashing.
    companion_factory is required for detached signatures. fname is used
    only in the missing-companion error.

    Returns (kind, value). Signatures with an expiration are rejected.
    """
    kind, header_algo, hasher, sig_text = _stream_verify_pass(sig_factory)
    if kind == CLEARSIGN:
        sig = parse_armored_signature(sig_text)
        _require_usable_signature(sig, header_algo, (SIG_TYPE_TEXT,))
        hasher.h.update(signature_trailer(sig))
        verify_signature(signing_keys, sig, hasher.h.digest())
        return _classify_clearsign(sig_factory)
    if kind == DETACHED:
        sig = parse_armored_signature(sig_text)
        _require_usable_signature(
            sig, None, (SIG_TYPE_BINARY, SIG_TYPE_TEXT)
        )
        if companion_factory is None:
            try:
                name = companion_filename(fname)
            except PGPError:
                name = basename(fname)
            raise PGPMissingFileError("Missing companion file %s" % name)
        digest = _hash_companion(companion_factory, sig)
        verify_signature(signing_keys, sig, digest)
        clf = PayloadClassifier()
        for piece in iter_crlf_normalized_bytes(companion_factory()):
            clf.feed_bytes(piece)
        return clf.finish()
    raise PGPInvalidSignatureError()


def _require_usable_signature(sig, header_algo, allowed_types):
    if sig.sig_type not in allowed_types:
        raise PGPInvalidSignatureError()
    if sig.unknown_critical:
        raise PGPInvalidSignatureError()
    if sig.has_sig_expiration:
        raise PGPSignatureExpirationError()
    if sig.hash_algo not in HASH_ALGOS:
        raise PGPUnknownHashError()
    if header_algo is not None and header_algo != sig.hash_algo:
        raise PGPInvalidSignatureError()


def _expiry_unix(body: bytes, duration):
    if not duration:
        return None
    created = key_creation_time(body)
    if created is None:
        return None
    return created + duration


def _stream_verify_pass(sig_factory) -> tuple:
    # Clearsign: headers → payload (hashed) → signature armor.
    # Detached: signature armor only.
    pending = ""
    header_ok = False
    kind = None
    linebuf = _LineBuf()
    state = None
    header_algo = None
    payload_hasher = None
    sig_parts = []
    sig_total = 0

    for piece in iter_crlf_normalized_bytes(sig_factory()):
        non_ascii = contains_non_ascii(piece)
        text = piece.decode("latin-1")
        if not header_ok:
            if non_ascii:
                raise PGPBinaryError(SIG_INVALID_MSG)
            pending += text
            probed = _probe_signed_header(pending)
            if probed is None:
                continue
            kind, stripped = probed
            header_ok = True
            text = stripped
            if kind == DETACHED:
                sig_parts.append(stripped)
                sig_total = len(stripped)
                if _has_armor_end("".join(sig_parts)):
                    break
                continue
            state = "headers"
        elif kind == DETACHED:
            if non_ascii:
                raise PGPBinaryError(SIG_INVALID_MSG)
            sig_parts.append(text)
            sig_total += len(text)
            if sig_total > MAX_SIGNATURE_BYTES:
                raise PGPInvalidSignatureError(SIG_TOO_LARGE_MSG)
            if _has_armor_end("".join(sig_parts)):
                break
            continue
        elif non_ascii and state != "payload":
            raise PGPBinaryError(SIG_INVALID_MSG)

        stop = False
        for line in linebuf.feed(text):
            if state == "headers":
                if line.startswith(BEGIN_SIGNED_MESSAGE):
                    continue
                if line.strip() == "":
                    if header_algo is None:
                        raise PGPUnknownHashError()
                    payload_hasher = _CanonicalTextHasher(
                        HASH_ALGOS[header_algo][2]
                    )
                    state = "payload"
                    continue
                if ":" in line:
                    name, value = line.split(":", 1)
                    if name.strip().lower() == "hash" and header_algo is None:
                        header_algo = _parse_hash_header(value)
                continue
            if state == "payload":
                if line.startswith(BEGIN_SIGNATURE):
                    payload_hasher.finish_clearsign()
                    state = "signature"
                    sig_parts = [line, "\n"]
                    sig_total = len(line) + 1
                    continue
                payload_hasher.feed_line(line)
                continue
            if state == "signature":
                if non_ascii:
                    raise PGPBinaryError(SIG_INVALID_MSG)
                sig_parts.append(line)
                sig_parts.append("\n")
                sig_total += len(line) + 1
                if sig_total > MAX_SIGNATURE_BYTES:
                    raise PGPInvalidSignatureError(SIG_TOO_LARGE_MSG)
                if line.startswith(END_SIGNATURE):
                    stop = True
                    break
        if stop:
            break

    if not header_ok:
        probed = _probe_signed_header(pending, eof=True)
        if probed is None:
            raise PGPInvalidSignatureError()
        kind, stripped = probed
        if kind == DETACHED:
            sig_parts = [stripped]
        else:
            raise PGPInvalidSignatureError()

    if kind == DETACHED:
        return kind, None, None, "".join(sig_parts)
    if kind == CLEARSIGN:
        if state != "signature" or payload_hasher is None:
            if state == "signature" and linebuf.buf:
                sig_parts.append(linebuf.buf)
            else:
                raise PGPInvalidSignatureError()
        if linebuf.buf and not "".join(sig_parts).rstrip().endswith(
            END_SIGNATURE
        ):
            sig_parts.append(linebuf.buf)
        return kind, header_algo, payload_hasher, "".join(sig_parts)
    raise PGPInvalidSignatureError()


def _probe_signed_header(acc: str, eof: bool = False):
    stripped = acc.lstrip()
    ready = (
        eof
        or len(stripped) > PROBE_HEADER_LEN
        or len(acc) > LINE_PROBE_LIMIT
    )
    if not ready:
        return None
    if stripped.startswith(BEGIN_PUBLIC_KEY):
        raise PGPPublicKeyAsSignatureError()
    if stripped.startswith(BEGIN_SIGNED_MESSAGE):
        return CLEARSIGN, stripped
    if stripped.startswith(BEGIN_SIGNATURE):
        return DETACHED, stripped
    raise PGPInvalidSignatureError()


def _has_armor_end(text: str) -> bool:
    return ("\n" + END_SIGNATURE) in ("\n" + text) or text.startswith(
        END_SIGNATURE
    )


def _classify_clearsign(sig_factory) -> tuple:
    clf = PayloadClassifier()
    linebuf = _LineBuf()
    pending = ""
    header_ok = False
    state = "headers"
    for piece in iter_crlf_normalized_bytes(sig_factory()):
        text = piece.decode("latin-1")
        if not header_ok:
            pending += text
            probed = _probe_signed_header(pending)
            if probed is None:
                continue
            _kind, stripped = probed
            header_ok = True
            text = stripped
        stop = False
        for line in linebuf.feed(text):
            if state == "headers":
                if line.startswith(BEGIN_SIGNED_MESSAGE):
                    continue
                if line.strip() == "":
                    state = "payload"
                continue
            if state == "payload":
                if line.startswith(BEGIN_SIGNATURE):
                    stop = True
                    break
                unescaped = line[2:] if line.startswith("- ") else line
                try:
                    unescaped.encode("ascii")
                    clf.feed_text(unescaped + "\n")
                except Exception:
                    clf.feed_bytes(unescaped.encode("latin-1") + b"\n")
        if stop:
            break
    return clf.finish()


def _hash_companion(factory, sig) -> bytes:
    entry = HASH_ALGOS.get(sig.hash_algo)
    if entry is None:
        raise PGPUnknownHashError()
    _short, _asn1_name, hash_ctor = entry
    if sig.sig_type == SIG_TYPE_BINARY:
        h = hash_ctor()
        for chunk in factory():
            h.update(chunk)
        h.update(signature_trailer(sig))
        return h.digest()
    if sig.sig_type == SIG_TYPE_TEXT:
        hasher = _CanonicalTextHasher(hash_ctor)
        linebuf = _LineBuf()
        for piece in iter_crlf_normalized_bytes(factory()):
            text = piece.decode("latin-1")
            for line in linebuf.feed(text):
                hasher.feed_line(line)
        if linebuf.buf:
            hasher.feed_line(linebuf.buf)
        hasher.finish_eof()
        hasher.h.update(signature_trailer(sig))
        return hasher.h.digest()
    raise PGPInvalidSignatureError()


class _LineBuf:
    def __init__(self):
        self.buf = ""

    def feed(self, text: str) -> list:
        self.buf += text
        lines = []
        while True:
            idx = self.buf.find("\n")
            if idx < 0:
                if len(self.buf) > LINE_PROBE_LIMIT:
                    raise PGPInvalidSignatureError(SIG_TOO_LARGE_MSG)
                return lines
            if idx > LINE_PROBE_LIMIT:
                raise PGPInvalidSignatureError(SIG_TOO_LARGE_MSG)
            lines.append(self.buf[:idx])
            self.buf = self.buf[idx + 1 :]


class _CanonicalTextHasher:
    def __init__(self, hash_ctor):
        self.h = hash_ctor()
        self.prev = None
        self.first = True

    def feed_line(self, line: str):
        if self.prev is not None:
            self._commit(self.prev)
        self.prev = line

    def finish_clearsign(self):
        if self.prev is not None and self.prev != "":
            self._commit(self.prev)
        self.prev = None

    def finish_eof(self):
        if self.prev is not None:
            self._commit(self.prev)
        self.prev = None

    def _commit(self, line: str):
        if line.startswith("- "):
            line = line[2:]
        line = line.rstrip(" \t")
        try:
            data = line.encode("utf-8")
        except Exception:
            data = line.encode("latin-1")
        if self.first:
            self.h.update(data)
            self.first = False
        else:
            self.h.update(b"\r\n")
            self.h.update(data)


def _parse_hash_header(value: str) -> int:
    token = value.strip().split(",")[0].strip().upper().replace("-", "")
    algo = HASH_HEADER.get(token)
    if algo is None:
        raise PGPUnknownHashError()
    return algo


def _v4_key_header(body: bytes) -> bytes:
    n = len(body)
    if n > 0xFFFF:
        raise PGPParseError()
    return bytes([0x99, (n >> 8) & 0xFF, n & 0xFF])


def _uid_header(tag: int, body: bytes) -> bytes:
    n = len(body)
    prefix = 0xB4 if tag == TAG_USER_ID else 0xD1
    return bytes(
        [
            prefix,
            (n >> 24) & 0xFF,
            (n >> 16) & 0xFF,
            (n >> 8) & 0xFF,
            n & 0xFF,
        ]
    )


def _check_key_signature(key_type: str, key, sig: Signature, parts) -> bool:
    entry = HASH_ALGOS.get(sig.hash_algo)
    if entry is None:
        raise PGPInvalidKeyError()
    h = entry[2]()
    for part in parts:
        h.update(part)
    h.update(signature_trailer(sig))
    digest = h.digest()
    if digest[:2] != sig.left16:
        return False
    return check_sig(key_type, key, sig, digest)


def collect_signing_keys(data: bytes) -> tuple:
    """
    Walk a transferable public key and return
    (primary_fingerprint, signing_keys, expires_at).

    The primary is included in signing_keys if a verified self-signature
    gives it the Sign flag. Each subkey needs a verified 0x18 binding;
    signing subkeys also need a verified 0x19 backsig. Encryption
    subkeys are skipped. Fail closed on SHA-1, bad/missing bindings,
    expiring self-signatures or bindings, revocations, designated
    revokers, or no signer.
    """
    collector = _TransferablePublicKey(data)
    collector.parse()
    return collector.primary_fpr, collector.signing_keys(), collector.expires_at


class _TransferablePublicKey:
    # One walk of a transferable public key. Primary signs if [S]; subkeys need 0x18 + 0x19.
    def __init__(self, data: bytes):
        self.data = data
        self.primary_body = None
        self.primary_fpr = None
        self.primary_type = None
        self.primary_key = None
        self.have_self_sig = False
        self.primary_flags = None
        self.primary_flags_created = -1
        self.primary_key_expiration = None
        self.primary_exp_created = -1
        self.uid_body = None
        self.uid_tag = 0
        self.sub_body = None
        self.sub_fpr = None
        self.sub_type = None
        self.sub_key = None
        self.sub_binding_created = -1
        self.sub_flags = None
        self.sub_key_expiration = None
        self.sub_have_binding = False
        self.sub_backsig_ok = False
        self.signers = []
        self.expires_at = None

    def parse(self):
        offset = 0
        while offset < len(self.data):
            tag, body, offset = read_packet(self.data, offset)
            if tag == TAG_MARKER or tag == TAG_PADDING:
                continue
            if tag == TAG_PUBLIC_KEY:
                if self.primary_body is not None:
                    raise PGPInvalidKeyError()
                self._set_primary(body)
                continue
            if self.primary_body is None:
                raise PGPInvalidKeyError()
            if tag == TAG_USER_ID or tag == TAG_USER_ATTR:
                self._finish_subkey()
                self.uid_body = body
                self.uid_tag = tag
                self.sub_body = None
                continue
            if tag == TAG_PUBLIC_SUBKEY:
                self._finish_subkey()
                self.uid_body = None
                self._set_subkey(body)
                continue
            if tag == TAG_SIGNATURE:
                self._handle_signature(body)
                continue
            raise PGPInvalidKeyError()
        self._finish_subkey()
        if not self.have_self_sig:
            raise PGPInvalidKeyError()
        self._note_expiry(self.primary_body, self.primary_key_expiration)

    def signing_keys(self) -> list:
        keys = []
        if self.primary_flags is not None and (self.primary_flags & FLAG_SIGN):
            if self.primary_type is None:
                raise PGPInvalidKeyError()
            keys.append((self.primary_fpr, self.primary_type, self.primary_key))
        keys.extend(self.signers)
        if not keys:
            raise PGPInvalidKeyError()
        return keys

    def _set_primary(self, body: bytes):
        self.primary_body = body
        self.primary_fpr = fingerprint(body)
        try:
            self.primary_type, self.primary_key = parse_supported_key(body)
        except PGPError:
            raise PGPInvalidKeyError()
        if self.primary_type is None:
            raise PGPUnsupportedKeyError()

    def _set_subkey(self, body: bytes):
        self.sub_body = body
        self.sub_fpr = fingerprint(body)
        try:
            self.sub_type, self.sub_key = parse_supported_key(body)
        except PGPError:
            self.sub_type, self.sub_key = None, None
        self.sub_binding_created = -1
        self.sub_flags = None
        self.sub_key_expiration = None
        self.sub_have_binding = False
        self.sub_backsig_ok = False

    def _finish_subkey(self):
        if self.sub_body is None:
            return
        if not self.sub_have_binding:
            raise PGPInvalidKeyError()
        body = self.sub_body
        duration = self.sub_key_expiration
        self.sub_body = None
        self._note_expiry(body, duration)
        if self.sub_flags is None or (self.sub_flags & FLAG_SIGN) == 0:
            return
        if not self.sub_backsig_ok or self.sub_type is None:
            raise PGPInvalidKeyError()
        self.signers.append((self.sub_fpr, self.sub_type, self.sub_key))

    def _handle_signature(self, body: bytes):
        try:
            sig = parse_signature_packet(body)
        except PGPError:
            raise PGPInvalidKeyError()
        if (
            sig.sig_type
            in (
                SIG_TYPE_KEY_REVOCATION,
                SIG_TYPE_SUBKEY_REVOCATION,
                SIG_TYPE_CERT_REVOCATION,
            )
            or sig.has_designated_revoker
        ):
            raise PGPInvalidKeyError()
        match = issuer_match(sig, self.primary_fpr)
        if match is not True:
            return
        if sig.hash_algo not in HASH_ALGOS or sig.unknown_critical:
            raise PGPInvalidKeyError()
        if sig.created is None:
            raise PGPInvalidKeyError()
        if self.sub_body is not None:
            self._handle_subkey_sig(sig)
            return
        if self.uid_body is not None:
            self._handle_uid_sig(sig)
            return
        self._handle_primary_sig(sig)

    def _primary_hash_parts(self):
        return (_v4_key_header(self.primary_body), self.primary_body)

    def _subkey_hash_parts(self):
        return (
            _v4_key_header(self.primary_body),
            self.primary_body,
            _v4_key_header(self.sub_body),
            self.sub_body,
        )

    def _handle_primary_sig(self, sig: Signature):
        parts = self._primary_hash_parts()
        if sig.sig_type != SIG_TYPE_DIRECT_KEY:
            raise PGPInvalidKeyError()
        if not _check_key_signature(self.primary_type, self.primary_key, sig, parts):
            raise PGPInvalidKeyError()
        if sig.has_sig_expiration:
            raise PGPInvalidKeyError()
        self.have_self_sig = True
        self._maybe_primary_flags(sig)

    def _handle_uid_sig(self, sig: Signature):
        if sig.sig_type < SIG_TYPE_CERT_GENERIC or sig.sig_type > SIG_TYPE_CERT_POSITIVE:
            raise PGPInvalidKeyError()
        parts = self._primary_hash_parts() + (
            _uid_header(self.uid_tag, self.uid_body),
            self.uid_body,
        )
        if not _check_key_signature(self.primary_type, self.primary_key, sig, parts):
            raise PGPInvalidKeyError()
        if sig.has_sig_expiration:
            raise PGPInvalidKeyError()
        self.have_self_sig = True
        self._maybe_primary_flags(sig)

    def _handle_subkey_sig(self, sig: Signature):
        parts = self._subkey_hash_parts()
        if sig.sig_type != SIG_TYPE_SUBKEY_BINDING:
            raise PGPInvalidKeyError()
        if not _check_key_signature(self.primary_type, self.primary_key, sig, parts):
            raise PGPInvalidKeyError()
        if sig.has_sig_expiration:
            raise PGPInvalidKeyError()
        if sig.created < self.sub_binding_created:
            return
        self.sub_have_binding = True
        self.sub_binding_created = sig.created
        self.sub_flags = sig.key_flags
        self.sub_key_expiration = sig.key_expiration
        self.sub_backsig_ok = False
        if self.sub_flags is not None and (self.sub_flags & FLAG_SIGN):
            self.sub_backsig_ok = self._verify_backsig(sig, parts)

    def _maybe_primary_flags(self, sig: Signature):
        if sig.created >= self.primary_exp_created:
            self.primary_exp_created = sig.created
            self.primary_key_expiration = sig.key_expiration
        if sig.key_flags is None:
            return
        if sig.created < self.primary_flags_created:
            return
        self.primary_flags = sig.key_flags
        self.primary_flags_created = sig.created

    def _note_expiry(self, body: bytes, duration):
        exp = _expiry_unix(body, duration)
        if exp is None:
            return
        if self.expires_at is None or exp < self.expires_at:
            self.expires_at = exp

    def _verify_backsig(self, binding: Signature, parts) -> bool:
        if self.sub_type is None:
            return False
        i = 0
        while i < len(binding.embedded):
            try:
                back = parse_signature_packet(binding.embedded[i])
            except PGPError:
                i += 1
                continue
            i += 1
            if back.has_designated_revoker:
                raise PGPInvalidKeyError()
            if back.sig_type != SIG_TYPE_PRIMARY_BINDING:
                continue
            if back.hash_algo not in HASH_ALGOS or back.unknown_critical:
                raise PGPInvalidKeyError()
            if back.created is None:
                raise PGPInvalidKeyError()
            match = issuer_match(back, self.sub_fpr)
            if match is not True:
                continue
            if _check_key_signature(self.sub_type, self.sub_key, back, parts):
                if back.has_sig_expiration:
                    raise PGPInvalidKeyError()
                return True
        return False
