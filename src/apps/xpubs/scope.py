"""
Scoped multi-XPUB authorization.

Lets a host request permission, once, for a bounded, explicitly
enumerated set of BIP32 derivation paths (a "scope"). After a single
on-device confirmation, individual ``xpub <path>`` requests that fall
inside the approved scope are answered without asking again, while
anything outside the scope keeps requiring the normal per-request
confirmation. See docs/communication.md for the full protocol writeup.

Grammar
-------
::

    scope     := entry (";" entry)*
    entry     := "m" ("/" component)*
    component := index | range
    index     := digits ["h" | "H" | "'"]
    range     := "{" digits "-" digits "}" ["h" | "H" | "'"]

At most one ``range`` component is allowed per entry. Both digits in a
range are inclusive bounds on the (non-hardened) child index; a
trailing hardening marker, if present, applies to the whole range.
There is no wildcard, no open range and no recursive matching - every
scope denotes a finite, precomputable set of paths.

All limits below are enforced *before* any expansion or allocation
proportional to their value, so a hostile scope can't force a large
allocation or a slow/huge confirmation screen.
"""

from embit import bip32

MAX_SCOPE_LEN = 1024  # raw "begin <scope>" argument, bytes
# Hard cap on the whole "xpubauth ..." payload (the "begin <scope>" or
# "end" text after the command prefix) as it is read from the host.
# Enforced *before* the bytes are decoded to a str or parsed, so a
# multi-megabyte line from a hostile host cannot be materialized as a
# Python string first. "begin " is 6 bytes; the extra slack absorbs
# surrounding whitespace / EOL without ever letting scope_str itself
# exceed MAX_SCOPE_LEN (parse_scope still rejects anything longer).
MAX_SCOPE_COMMAND_LEN = MAX_SCOPE_LEN + 32
MAX_ENTRIES = 16  # scope entries per authorization
MAX_PATH_DEPTH = 8  # bip32 components per entry
MAX_RANGE_WIDTH = 200  # (hi - lo + 1) for a single range component
MAX_TOTAL_XPUBS = 200  # sum of counts across all entries - the request budget

HARDENED = bip32.HARDENED_INDEX

# purposes with a well-known coin-type slot at m/purpose'/coin_type'/...
STANDARD_PURPOSES = (44, 48, 49, 84, 86, 87)


class ScopeError(Exception):
    """Malformed, oversized, ambiguous or network-mismatched scope request."""


class ScopeEntry:
    """One normalized scope entry: an exact path, or a path with exactly
    one bounded range component. Also tracks, per possible value, whether
    it has already been silently exported once (Model A budget: every
    unique authorized path may be exported silently at most once)."""

    __slots__ = ("components", "range_index", "count", "consumed")

    def __init__(self, components, range_index, count):
        self.components = components  # tuple of: int, or ("range", lo, hi)
        self.range_index = range_index
        self.count = count
        self.consumed = bytearray((count + 7) // 8)

    def format(self):
        """Canonical display string, rendered from the parsed/normalized
        representation - never from the original request text - so what
        is shown on screen is always exactly what gets enforced."""
        parts = []
        for comp in self.components:
            if isinstance(comp, tuple):
                _, lo, hi = comp
                hardened = lo >= HARDENED
                lo_raw = lo - HARDENED if hardened else lo
                hi_raw = hi - HARDENED if hardened else hi
                parts.append("{%d-%d}%s" % (lo_raw, hi_raw, "h" if hardened else ""))
            else:
                hardened = comp >= HARDENED
                raw = comp - HARDENED if hardened else comp
                parts.append("%d%s" % (raw, "h" if hardened else ""))
        return "m/" + "/".join(parts)

    def match(self, components):
        """Returns the consumption-bitset index if the normalized bip32
        path `components` falls inside this entry, else None. Matching is
        purely on parsed integer components, never on raw text."""
        if len(components) != len(self.components):
            return None
        for i, comp in enumerate(self.components):
            v = components[i]
            if isinstance(comp, tuple):
                _, lo, hi = comp
                if v < lo or v > hi:
                    return None
            elif comp != v:
                return None
        if self.range_index is None:
            return 0
        _, lo, _ = self.components[self.range_index]
        return components[self.range_index] - lo

    def is_consumed(self, idx):
        return (self.consumed[idx // 8] >> (idx % 8)) & 1 == 1

    def consume(self, idx):
        self.consumed[idx // 8] |= 1 << (idx % 8)


def _parse_uint(s):
    if not s or len(s) > 10 or not s.isdigit():
        raise ScopeError("Invalid number: %r" % s)
    return int(s)


def _parse_component(text):
    if not text:
        raise ScopeError("Empty path component")
    if text[0] == "{":
        hardened = text[-1] in ("h", "H", "'")
        body = text[:-1] if hardened else text
        if body[:1] != "{" or body[-1:] != "}":
            raise ScopeError("Malformed range component: %r" % text)
        bounds = body[1:-1].split("-")
        if len(bounds) != 2:
            raise ScopeError("Malformed range component: %r" % text)
        lo_raw = _parse_uint(bounds[0])
        hi_raw = _parse_uint(bounds[1])
        if lo_raw > hi_raw:
            raise ScopeError("Invalid range (start > end): %r" % text)
        if hi_raw >= HARDENED:
            raise ScopeError("Range value out of bounds: %r" % text)
        if hi_raw - lo_raw + 1 > MAX_RANGE_WIDTH:
            raise ScopeError("Range too wide (max %d): %r" % (MAX_RANGE_WIDTH, text))
        offset = HARDENED if hardened else 0
        return ("range", lo_raw + offset, hi_raw + offset)
    hardened = text[-1] in ("h", "H", "'")
    raw_text = text[:-1] if hardened else text
    val = _parse_uint(raw_text)
    if val >= HARDENED:
        raise ScopeError("Path value out of bounds: %r" % text)
    return val + (HARDENED if hardened else 0)


def _parse_entry(text):
    text = text.strip()
    if not text.startswith("m"):
        raise ScopeError("Scope entry must start with 'm': %r" % text)
    rest = text[1:]
    if rest.startswith("/"):
        rest = rest[1:]
    elif rest != "":
        raise ScopeError("Malformed scope entry: %r" % text)
    rest = rest.rstrip("/")
    if not rest:
        raise ScopeError("Scope entry has no derivation components: %r" % text)
    parts = rest.split("/")
    if len(parts) > MAX_PATH_DEPTH:
        raise ScopeError("Path too deep (max %d): %r" % (MAX_PATH_DEPTH, text))
    components = []
    range_index = None
    for i, part in enumerate(parts):
        comp = _parse_component(part)
        if isinstance(comp, tuple):
            if range_index is not None:
                raise ScopeError("Only one range allowed per scope entry: %r" % text)
            range_index = i
        components.append(comp)
    if range_index is None:
        count = 1
    else:
        _, lo, hi = components[range_index]
        lo_raw = lo - HARDENED if lo >= HARDENED else lo
        hi_raw = hi - HARDENED if hi >= HARDENED else hi
        count = hi_raw - lo_raw + 1
    return ScopeEntry(tuple(components), range_index, count)


def _overlaps(a, b):
    """Two entries overlap iff their (per-component independent) value
    sets intersect at every component - since each entry varies at most
    one component, that per-component check is exact, not approximate."""
    if len(a.components) != len(b.components):
        return False
    for ca, cb in zip(a.components, b.components):
        lo_a, hi_a = (ca[1], ca[2]) if isinstance(ca, tuple) else (ca, ca)
        lo_b, hi_b = (cb[1], cb[2]) if isinstance(cb, tuple) else (cb, cb)
        if hi_a < lo_b or hi_b < lo_a:
            return False
    return True


def standard_path_coin_type_mismatch(path, expected_coin_type):
    """
    True if `path` (an already-parsed list of ints, e.g. from
    bip32.parse_path) is a standard-purpose path (44'/48'/49'/84'/86'/87')
    whose coin-type component does not equal `expected_coin_type` - the
    hardened BIP44 coin type of the network currently active on the
    device. This is the same rule _validate_standard_coin_type applies to
    an xpubauth scope entry, exposed here for a single concrete,
    non-scoped path (a plain `xpub <path>` request).

    False (nothing to enforce) for anything shorter than 2 components or
    with a non-standard purpose - such paths carry no implied network
    semantics.
    """
    if len(path) < 2:
        return False
    purpose = path[0]
    if purpose < HARDENED:
        return False
    if purpose - HARDENED not in STANDARD_PURPOSES:
        return False
    return path[1] != (expected_coin_type + HARDENED)


# Short, screen-friendly hint naming the network(s) a given BIP44 coin
# type belongs to, so a rejected request can tell the user which network
# to switch the device to. Coin type 1' is deliberately shared by several
# test networks, so it can only ever name the candidates.
_COIN_TYPE_NETWORK_HINTS = {
    0: "Mainnet",
    1: "Testnet, Signet or Regtest",
    1776: "Liquid",
}


def network_hint_for_path(path):
    """
    A short human string naming the network(s) `path` (already-parsed) is
    for, by its BIP44 coin type - e.g. "Mainnet", "Liquid", or
    "Testnet, Signet or Regtest". Returns None when there's no useful hint
    (path too short, non-hardened or unrecognized coin type).
    """
    if len(path) < 2:
        return None
    coin = path[1]
    if coin < HARDENED:
        return None
    return _COIN_TYPE_NETWORK_HINTS.get(coin - HARDENED)


def _validate_standard_coin_type(entry, network_name, expected_coin_type):
    """For recognizable standard purposes (44'/48'/49'/84'/86'/87'), the
    coin-type component must be a fixed value matching the currently
    active Specter network. Non-standard/custom paths are left alone -
    they carry no implied network semantics to enforce."""
    comps = entry.components
    if len(comps) < 2:
        return
    purpose = comps[0]
    if isinstance(purpose, tuple) or purpose < HARDENED:
        return
    if purpose - HARDENED not in STANDARD_PURPOSES:
        return
    coin = comps[1]
    expected = expected_coin_type + HARDENED
    if isinstance(coin, tuple) or coin != expected:
        raise ScopeError(
            "Scope entry does not match the active network (%s): %s"
            % (network_name, entry.format())
        )


def parse_scope(scope_str, network_name, expected_coin_type):
    """
    Parses, validates, normalizes and network-checks `scope_str`.
    Returns (entries, total_count). Raises ScopeError on any problem;
    never returns a partially valid scope.
    """
    if len(scope_str) > MAX_SCOPE_LEN:
        raise ScopeError("Scope request too large")
    raw_entries = [e.strip() for e in scope_str.split(";")]
    raw_entries = [e for e in raw_entries if e]
    if not raw_entries:
        raise ScopeError("Empty scope")
    if len(raw_entries) > MAX_ENTRIES:
        raise ScopeError("Too many scope entries (max %d)" % MAX_ENTRIES)

    entries = []
    total = 0
    for raw in raw_entries:
        entry = _parse_entry(raw)
        total += entry.count
        if total > MAX_TOTAL_XPUBS:
            raise ScopeError("Scope too large (max %d keys)" % MAX_TOTAL_XPUBS)
        entries.append(entry)

    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            if _overlaps(entries[i], entries[j]):
                raise ScopeError(
                    "Overlapping or duplicate scope entries are not allowed"
                )

    for entry in entries:
        _validate_standard_coin_type(entry, network_name, expected_coin_type)

    return entries, total


class Authorization:
    """A confirmed, volatile, network-bound scope permission.
    Exists only in RAM; never persisted to flash/SD/settings."""

    __slots__ = ("entries", "network", "remaining")

    def __init__(self, entries, network):
        self.entries = entries
        self.network = network
        self.remaining = sum(e.count for e in entries)

    def try_consume(self, network, components):
        """If `components` (a parsed bip32 path) is silently authorized
        right now, marks it consumed and returns True. Never widens or
        modifies the scope itself - only tracks per-path consumption."""
        if network != self.network:
            return False
        for entry in self.entries:
            idx = entry.match(components)
            if idx is None:
                continue
            if entry.is_consumed(idx):
                return False
            entry.consume(idx)
            self.remaining -= 1
            return True
        return False
