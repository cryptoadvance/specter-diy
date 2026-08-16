"""
Pure logic for the SeedQR transcription viewer: canonical QR module matrix
generation plus zone/section geometry.

Deliberately free of any lvgl / hardware dependency (only ``math`` at import
time; ``qrcode`` -- the native usermod -- is imported lazily inside
``generate_matrix`` only) so this module can be unit-tested on a desktop
Python interpreter without a display or firmware build.

Section geometry mirrors SeedSigner's SeedQR transcription workflow
(https://github.com/SeedSigner/seedsigner/blob/dev/docs/seed_qr/README.md):
a 21x21 QR is grouped into 7x7-module sections (a 3x3 section grid); every
larger SeedQR size is grouped into 5x5-module sections.
"""
import math

# Row letters / column numbers used for section labels, e.g. "B-3".
ROW_LABELS = "ABCDEF"
COL_LABELS = "123456"

# Module values. Real QR modules are 0 (white) or 1 (black/dark). OUTSIDE
# marks a cell that lies past the edge of the real QR matrix -- present only
# in the partial final row/column of sections on non-square-divisible sizes
# (e.g. the 29x29 Standard 24-word SeedQR) -- so callers never confuse "no
# module here" with a valid white module.
MODULE_WHITE = 0
MODULE_BLACK = 1
MODULE_OUTSIDE = 2


class MatrixError(ValueError):
    """Raised when a QR payload can't be turned into a valid module matrix."""


def generate_matrix(payload):
    """
    Build the canonical QR module matrix for a SeedQR payload.

    ``payload`` must be either:
      - ``str``: Standard SeedQR digit string (numeric QR mode)
      - ``bytes``: Compact SeedQR raw entropy (binary QR mode)

    Returns a tuple of ``bytes`` rows (one element per module, 0 or 1). This
    is the single source of truth for both the overview and every zoomed
    section: it must never be regenerated separately for those two views.
    """
    import qrcode  # native firmware module (qrcodegen-backed)

    raw = qrcode.encode_to_string(payload)
    return parse_matrix(raw)


def parse_matrix(raw):
    """
    Parse the newline-separated '0'/'1' grid produced by
    ``qrcode.encode_to_string`` into a tuple of ``bytes`` rows.
    """
    rows = raw.strip("\n").split("\n")
    matrix = tuple(bytes(1 if c == "1" else 0 for c in row) for row in rows)
    validate_matrix(matrix)
    return matrix


def validate_matrix(matrix):
    """
    Raise MatrixError if ``matrix`` isn't a square, standards-compliant QR
    module grid (size = 21 + 4*(version-1), version 1..40). Returns the size.
    """
    size = len(matrix)
    if size == 0:
        raise MatrixError("Empty QR matrix")
    for row in matrix:
        if len(row) != size:
            raise MatrixError("QR matrix must be square")
    if size < 21 or size > 177 or (size - 21) % 4 != 0:
        raise MatrixError("Not a valid QR module count: %d" % size)
    return size


def modules_per_section(size):
    """Edge length (in modules) of one transcription section."""
    return 7 if size == 21 else 5


def num_sections(size):
    """Edge length (in sections) of the section grid, i.e. ceil(size / mps)."""
    return math.ceil(size / modules_per_section(size))


def section_label(row, col):
    """0-indexed (row, col) section coordinate -> 'A-1'-style label."""
    if not (0 <= row < len(ROW_LABELS)) or not (0 <= col < len(COL_LABELS)):
        raise ValueError("Section coordinate out of supported range: (%r, %r)" % (row, col))
    return "%s-%d" % (ROW_LABELS[row], col + 1)


def section_bounds(size, row, col):
    """
    Module-space bounding box of section (row, col) as (x0, y0, w, h), where
    x0/y0 are the top-left module coordinates and w/h are the number of REAL
    modules covered (< modules_per_section on a partial trailing row/column).
    """
    mps = modules_per_section(size)
    n = num_sections(size)
    if not (0 <= row < n) or not (0 <= col < n):
        raise ValueError("Section coordinate out of range: (%r, %r)" % (row, col))
    x0 = col * mps
    y0 = row * mps
    w = min(mps, size - x0)
    h = min(mps, size - y0)
    return x0, y0, w, h


def extract_section(matrix, row, col):
    """
    Extract section (row, col) from ``matrix`` as a tuple of
    ``modules_per_section(size)`` rows, each of that same length. Cells past
    the true QR matrix edge are filled with MODULE_OUTSIDE.
    """
    size = len(matrix)
    mps = modules_per_section(size)
    x0, y0, w, h = section_bounds(size, row, col)
    out = []
    for dy in range(mps):
        if dy < h:
            real = matrix[y0 + dy][x0:x0 + w]
            if w < mps:
                real = real + bytes([MODULE_OUTSIDE]) * (mps - w)
            out.append(real)
        else:
            out.append(bytes([MODULE_OUTSIDE]) * mps)
    return tuple(out)


def extract_real_section(matrix, row, col):
    """
    Extract section (row, col) from ``matrix`` as exactly its real modules
    -- h rows of w columns each, per ``section_bounds`` -- with no
    MODULE_OUTSIDE padding. Use this to render only the modules that
    actually exist (e.g. a partial trailing section shown at its true,
    smaller size) instead of a fixed modules_per_section(size) square with
    filler cells.
    """
    size = len(matrix)
    x0, y0, w, h = section_bounds(size, row, col)
    return tuple(matrix[y0 + dy][x0:x0 + w] for dy in range(h))


def neighbor_section(row, col, size, direction):
    """
    Returns the (row, col) of the section adjacent to (row, col) in
    ``direction`` ("up"/"down"/"left"/"right"), or None if that would fall
    outside the section grid.
    """
    n = num_sections(size)
    if direction == "up":
        row -= 1
    elif direction == "down":
        row += 1
    elif direction == "left":
        col -= 1
    elif direction == "right":
        col += 1
    else:
        raise ValueError("Unknown direction: %r" % direction)
    if 0 <= row < n and 0 <= col < n:
        return row, col
    return None


def fit_module_pixels(count, available_px):
    """
    Largest integer per-module pixel size such that ``count`` modules fit
    within ``available_px``, so modules render as crisp whole-pixel squares
    instead of being smoothed/interpolated to a fractional size. Always
    returns at least 1.
    """
    return max(1, int(available_px) // int(count))


def coord_to_module(px, py, size, module_px):
    """
    Map a touch point (px, py) -- given in whole pixels relative to the
    top-left corner of the rendered module grid, with any quiet zone already
    excluded by the caller -- to a (module_x, module_y) coordinate.

    ``module_px`` is the on-screen pixel edge length of a single module
    (matrix assumed square, uniform module size). Returns None if the point
    falls outside the matrix or entirely outside the [0, size) grid.
    """
    if module_px <= 0:
        raise ValueError("module_px must be positive")
    matrix_px_size = module_px * size
    if px < 0 or py < 0 or px >= matrix_px_size or py >= matrix_px_size:
        return None
    mx = min(px // module_px, size - 1)
    my = min(py // module_px, size - 1)
    return mx, my


def coord_to_section(px, py, size, module_px):
    """Map a touch point straight to its (row, col) section, or None."""
    m = coord_to_module(px, py, size, module_px)
    if m is None:
        return None
    mx, my = m
    mps = modules_per_section(size)
    return my // mps, mx // mps


def standard_payload(mnemonic):
    """
    Standard SeedQR payload: each BIP-39 word's wordlist index, zero-padded
    to 4 digits, concatenated with no separators. Equivalent to (and must
    stay equivalent to) RAMKeyStore.show_mnemonic()'s original inline
    computation -- this only relocates it so it can be unit-tested.
    """
    from embit import bip39

    words = mnemonic.split()
    return "".join("%04d" % bip39.WORDLIST.index(w) for w in words)


def compact_payload(mnemonic):
    """
    Compact SeedQR payload: the raw BIP-39 entropy bytes. Must never be
    hex-encoded before being handed to the QR encoder.
    """
    from embit import bip39

    return bip39.mnemonic_to_bytes(mnemonic)


class ZoomNavigator:
    """
    Tracks the section currently shown by the zoomed transcription view as
    the user pans around. Pure state machine (no lvgl dependency) so
    SeedQRZoomScreen can delegate all of its navigation bookkeeping here.
    """

    def __init__(self, size, row=0, col=0):
        self.size = size
        self.row = row
        self.col = col

    @property
    def section(self):
        return self.row, self.col

    @property
    def label(self):
        return section_label(self.row, self.col)

    def can_move(self, direction):
        return neighbor_section(self.row, self.col, self.size, direction) is not None

    def move(self, direction):
        """Move if possible; always returns the (possibly unchanged) section."""
        nxt = neighbor_section(self.row, self.col, self.size, direction)
        if nxt is not None:
            self.row, self.col = nxt
        return self.section
