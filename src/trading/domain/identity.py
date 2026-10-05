"""Instrument identity (ADR-019 §1): InstrumentId is canonical; Symbol and Isin are external."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from trading.domain.timing import is_known, require_aware

_ISIN_SHAPE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


class IdentityError(Exception):
    """An identity mapping is inconsistent, or a lookup has no answer."""


def _require_token(kind: str, value: str) -> None:
    """Non-empty printable text without whitespace. No normalisation (case, punctuation) applied."""
    if not isinstance(value, str):
        raise TypeError(f"{kind} must be a str, not {type(value).__name__}")
    if not value or not value.isprintable() or any(c.isspace() for c in value):
        raise ValueError(f"{kind} must be non-empty printable text without whitespace: {value!r}")


@dataclass(frozen=True, slots=True, order=True)
class InstrumentId:
    """Canonical internal identity of an equity instrument. Stable and never reused."""

    value: str

    def __post_init__(self) -> None:
        _require_token("InstrumentId", self.value)


@dataclass(frozen=True, slots=True, order=True)
class Symbol:
    """NSE trading symbol. Display/external reference only: it may change or be reused."""

    value: str

    def __post_init__(self) -> None:
        _require_token("Symbol", self.value)


@dataclass(frozen=True, slots=True)
class Isin:
    """ISIN, ISO 6166 shape (2 letters, 9 alphanumerics, 1 digit). Check digit not verified."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(f"Isin must be a str, not {type(self.value).__name__}")
        if not _ISIN_SHAPE.fullmatch(self.value):
            raise ValueError(f"not an ISIN-shaped identifier: {self.value!r}")


@dataclass(frozen=True, slots=True)
class IdentityMapEntry:
    """`symbol` refers to `instrument_id` from `valid_from` to `valid_to` (inclusive; None=open).

    `known_at` is when the mapping became public (e.g. the symbol-change announcement), so identity
    changes inside a sealed window are sealed like any other information (ADR-018 §2).
    """

    instrument_id: InstrumentId
    symbol: Symbol
    valid_from: date
    valid_to: date | None
    known_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.known_at)
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError(f"valid_to {self.valid_to} is before valid_from {self.valid_from}")

    def covers(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)

    def overlaps(self, other: "IdentityMapEntry") -> bool:
        starts_before_other_ends = other.valid_to is None or self.valid_from <= other.valid_to
        other_starts_before_this_ends = self.valid_to is None or other.valid_from <= self.valid_to
        return starts_before_other_ends and other_starts_before_this_ends


class IdentityMap:
    """Dated symbol ↔ instrument mapping. A symbol change never creates a new instrument."""

    def __init__(self, entries: Iterable[IdentityMapEntry]) -> None:
        self._entries = tuple(entries)
        for index, entry in enumerate(self._entries):
            for other in self._entries[index + 1 :]:
                same_symbol = entry.symbol == other.symbol
                same_instrument = entry.instrument_id == other.instrument_id
                if (same_symbol or same_instrument) and entry.overlaps(other):
                    raise IdentityError(f"overlapping identity entries: {entry} and {other}")

    def as_known_at(self, as_of: datetime) -> "IdentityMap":
        """The mapping as it was known at `as_of` (entries announced later are excluded)."""
        return IdentityMap(entry for entry in self._entries if is_known(entry.known_at, as_of))

    def resolve(self, symbol: Symbol, day: date) -> InstrumentId:
        for entry in self._entries:
            if entry.symbol == symbol and entry.covers(day):
                return entry.instrument_id
        raise IdentityError(f"no instrument for symbol {symbol.value} on {day}")

    def symbol_on(self, instrument_id: InstrumentId, day: date) -> Symbol:
        for entry in self._entries:
            if entry.instrument_id == instrument_id and entry.covers(day):
                return entry.symbol
        raise IdentityError(f"no symbol for {instrument_id.value} on {day}")
