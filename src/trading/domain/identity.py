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
    """From `valid_from`, `symbol` refers to `instrument_id`, open-ended until an `IdentityMapEnd`.

    `known_at` is when the assignment became public (e.g. the listing or symbol-change
    announcement), so identity changes inside a sealed window are sealed like any other
    information (ADR-018 §2).
    """

    instrument_id: InstrumentId
    symbol: Symbol
    valid_from: date
    known_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.known_at)


@dataclass(frozen=True, slots=True)
class IdentityMapEnd:
    """The assignment (`instrument_id`, `symbol`, `valid_from`) ends on `valid_to` (inclusive).

    A separate record because the end of an assignment (a rename, a delisting) usually becomes
    known long after the assignment itself. With a single knowledge time per assignment, an as-of
    view could show an end date before anyone knew it (ADR-018 §2 seals each record by its own
    knowledge time). Before `known_at`, the assignment is open-ended in every as-of view.
    """

    instrument_id: InstrumentId
    symbol: Symbol
    valid_from: date
    valid_to: date
    known_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.known_at)
        if self.valid_to < self.valid_from:
            raise ValueError(f"valid_to {self.valid_to} is before valid_from {self.valid_from}")


type _AssignmentKey = tuple[InstrumentId, Symbol, date]


def _key(record: IdentityMapEntry | IdentityMapEnd) -> _AssignmentKey:
    return (record.instrument_id, record.symbol, record.valid_from)


def _overlap(start_a: date, end_a: date | None, start_b: date, end_b: date | None) -> bool:
    return (end_b is None or start_a <= end_b) and (end_a is None or start_b <= end_a)


class IdentityMap:
    """Dated symbol ↔ instrument mapping (ADR-019 §1). A symbol change never creates a new
    instrument.

    Each assignment is an `IdentityMapEntry`, optionally ended by an `IdentityMapEnd`. Validation
    guarantees every as-of view is consistent: two assignments of one symbol or one instrument
    must not overlap in the view where both are first known (with only the ends known by then).
    """

    def __init__(
        self, entries: Iterable[IdentityMapEntry], ends: Iterable[IdentityMapEnd] = ()
    ) -> None:
        self._entries = tuple(entries)
        # Content order, so `ends()` never depends on the order records were supplied in.
        self._ends = tuple(
            sorted(ends, key=lambda e: (e.instrument_id.value, e.symbol.value, e.valid_from))
        )
        by_key = {_key(entry): entry for entry in self._entries}
        self._end_of: dict[_AssignmentKey, IdentityMapEnd] = {}
        for end in self._ends:
            entry = by_key.get(_key(end))
            if entry is None:
                raise IdentityError(f"identity end ends no assignment: {end}")
            if _key(end) in self._end_of:
                raise IdentityError(f"assignment ended more than once: {entry}")
            if end.known_at < entry.known_at:
                raise IdentityError(f"identity end known before the assignment it ends: {end}")
            self._end_of[_key(end)] = end
        for index, entry in enumerate(self._entries):
            for other in self._entries[index + 1 :]:
                if entry.symbol != other.symbol and entry.instrument_id != other.instrument_id:
                    continue
                both_known = max(entry.known_at, other.known_at)
                if _overlap(
                    entry.valid_from,
                    self._valid_to(entry, both_known),
                    other.valid_from,
                    self._valid_to(other, both_known),
                ):
                    raise IdentityError(
                        f"overlapping identity entries as known at {both_known}: "
                        f"{entry} and {other}"
                    )

    def _valid_to(self, entry: IdentityMapEntry, as_of: datetime | None = None) -> date | None:
        """The assignment's end as known at `as_of` (None = open); all known ends if no as_of."""
        end = self._end_of.get(_key(entry))
        if end is None or (as_of is not None and not is_known(end.known_at, as_of)):
            return None
        return end.valid_to

    def _covers(self, entry: IdentityMapEntry, day: date) -> bool:
        valid_to = self._valid_to(entry)
        return entry.valid_from <= day and (valid_to is None or day <= valid_to)

    def ends(self) -> tuple[IdentityMapEnd, ...]:
        return self._ends

    def as_known_at(self, as_of: datetime) -> "IdentityMap":
        """The mapping as known at `as_of`: assignments and ends announced later are excluded."""
        return IdentityMap(
            (entry for entry in self._entries if is_known(entry.known_at, as_of)),
            (end for end in self._ends if is_known(end.known_at, as_of)),
        )

    def resolve(self, symbol: Symbol, day: date) -> InstrumentId:
        for entry in self._entries:
            if entry.symbol == symbol and self._covers(entry, day):
                return entry.instrument_id
        raise IdentityError(f"no instrument for symbol {symbol.value} on {day}")

    def symbol_on(self, instrument_id: InstrumentId, day: date) -> Symbol:
        for entry in self._entries:
            if entry.instrument_id == instrument_id and self._covers(entry, day):
                return entry.symbol
        raise IdentityError(f"no symbol for {instrument_id.value} on {day}")
