from .base import PGPSlashInFilenameError, contains_non_ascii

_HEX = "0123456789abcdefABCDEF"

KIND_EMPTY = "empty"
KIND_BINARY = "binary"
KIND_CHECKSUM_FILES = "checksum_files"
KIND_LONG_CHECKSUM_FILES = "long_checksum_files"
KIND_TEXT = "text"
KIND_LONG_TEXT = "long_text"

MAX_CHECKSUM_LIST_BYTES = 4096
MAX_TEXT_BYTES = 2000
_LINE_SCAN_LIMIT = MAX_CHECKSUM_LIST_BYTES + 80


class PayloadClassifier:
    """Classify a signed payload while iterating lines.

    After long_checksum_files or long_text is detected, data is no longer
    accumulated but scanning continues so a later non-checksum line can
    still switch the type to long_text.
    """

    def __init__(self):
        self.still_checksums = True
        self.found_slash = False
        self.entries = []
        self.text_parts = []
        self.checksum_bytes = 0
        self.text_bytes = 0
        self.accum_checksums = True
        self.accum_text = True
        self.saw_content = False
        self.binary = False
        self.line_buf = ""
        self.line_overflow = False

    def feed_bytes(self, data: bytes):
        if self.binary:
            return
        if contains_non_ascii(data):
            self._mark_binary()
            return
        try:
            self.feed_text(data.decode("ascii"))
        except Exception:
            self._mark_binary()

    def feed_text(self, text: str):
        if self.binary:
            return
        if "\n" not in text:
            room = _LINE_SCAN_LIMIT + 1 - len(self.line_buf)
            if len(text) > room:
                if room > 0:
                    self.line_buf += text[:room]
                self._handle_long_partial_line()
                return
            self.line_buf += text
            if len(self.line_buf) > _LINE_SCAN_LIMIT:
                self._handle_long_partial_line()
            return
        self.line_buf += text
        while True:
            idx = self.line_buf.find("\n")
            if idx < 0:
                if len(self.line_buf) > _LINE_SCAN_LIMIT:
                    self._handle_long_partial_line()
                break
            line = self.line_buf[:idx]
            self.line_buf = self.line_buf[idx + 1 :]
            self._handle_line(line)

    def finish(self) -> tuple:
        if self.line_buf:
            self._handle_line(self.line_buf)
            self.line_buf = ""
        if self.binary:
            return KIND_BINARY, None
        if not self.saw_content:
            return KIND_EMPTY, None
        if self.still_checksums and (self.entries or not self.accum_checksums):
            if self.found_slash:
                raise PGPSlashInFilenameError()
            if self.accum_checksums and self.entries:
                return KIND_CHECKSUM_FILES, self.entries
            return KIND_LONG_CHECKSUM_FILES, None
        if self.accum_text:
            return KIND_TEXT, "".join(self.text_parts).strip()
        return KIND_LONG_TEXT, None

    def _mark_binary(self):
        self.binary = True
        self.accum_text = False
        self.accum_checksums = False
        self.entries = []
        self.text_parts = []

    def _note_slash(self, text: str):
        if "/" in text or "\\" in text:
            self.found_slash = True

    def _handle_long_partial_line(self):
        prefix = self.line_buf[:_LINE_SCAN_LIMIT]
        self._note_slash(self.line_buf)
        parsed = _parse_checksum_line(prefix, partial=True)
        if parsed is None:
            self.still_checksums = False
        elif parsed != "skip":
            digest, name, has_slash = parsed
            if has_slash:
                self.found_slash = True
            self.checksum_bytes += 64 + len(name)
            if self.checksum_bytes > MAX_CHECKSUM_LIST_BYTES:
                self.accum_checksums = False
                self.entries = []
        self.accum_text = False
        self.text_parts = []
        self.line_overflow = True
        self.line_buf = ""
        self.saw_content = True

    def _handle_line(self, line: str):
        if self.line_overflow:
            self._note_slash(line)
            parsed = _parse_checksum_line(line, partial=True)
            if parsed is None:
                self.still_checksums = False
            elif parsed != "skip":
                _digest, _name, has_slash = parsed
                if has_slash:
                    self.found_slash = True
            self.line_overflow = False
            self.saw_content = True
            return

        if line.strip():
            self.saw_content = True

        parsed = _parse_checksum_line(line)
        if parsed is None:
            self.still_checksums = False
        elif parsed != "skip":
            digest, name, has_slash = parsed
            if has_slash:
                self.found_slash = True
            added = 64 + len(name)
            if self.accum_checksums and self.still_checksums:
                if self.checksum_bytes + added > MAX_CHECKSUM_LIST_BYTES:
                    self.accum_checksums = False
                    self.entries = []
                else:
                    self.checksum_bytes += added
                    self.entries.append((digest, name))
            else:
                self.checksum_bytes += added
                if self.checksum_bytes > MAX_CHECKSUM_LIST_BYTES:
                    self.accum_checksums = False

        if self.accum_text:
            extra = len(line) + 1
            if self.text_bytes + extra > MAX_TEXT_BYTES:
                self.accum_text = False
                self.text_parts = []
            else:
                if self.text_parts:
                    self.text_parts.append("\n")
                self.text_parts.append(line)
                self.text_bytes += extra


def _parse_checksum_line(line: str, partial: bool = False):
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return "skip"
    parts = raw.split(None, 1)
    if len(parts) != 2:
        if partial and len(parts) == 1:
            digest = parts[0]
            if len(digest) < 64:
                return None
            if len(digest) == 64:
                for char in digest:
                    if char not in _HEX:
                        return None
                return (digest.lower(), "", False)
        return None
    digest, name = parts
    if len(digest) != 64:
        return None
    for char in digest:
        if char not in _HEX:
            return None
    if name.startswith("*"):
        name = name[1:]
    name = name.strip()
    if not name or name in (".", ".."):
        return None
    has_slash = "/" in name or "\\" in name
    return (digest.lower(), name, has_slash)


def verify_checksum_files(entries: list, sha256_of) -> tuple:
    """
    sha256_of(name) returns a hex digest string, or None if the file
    cannot be opened. Returns (verified, missing, corrupt) name lists.
    """
    verified = []
    missing = []
    corrupt = []
    for digest, name in entries:
        got = sha256_of(name)
        if got is None:
            missing.append(name)
        elif got.lower() == digest:
            verified.append(name)
        else:
            corrupt.append(name)
    return verified, missing, corrupt


def unverified_files(sd_names: list, listed_names: list, exclude_names: list) -> list:
    listed = set(listed_names)
    exclude = set(exclude_names)
    extra = []
    for name in sd_names:
        if name in (".", ".."):
            continue
        if name not in listed and name not in exclude:
            extra.append(name)
    extra.sort()
    return extra
