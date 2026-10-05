"""Series changes and typed absence of observations (ADR-019 §3).

Legitimate absence (suspension, series change, delisting, not yet listed) must carry evidence.
Unexplained or unsourced absence is a data-quality failure, never silently treated as legitimate.
Every record carries a knowledge time, so it is sealed by window like any other data (ADR-018 §2).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from trading.domain.identity import InstrumentId
from trading.domain.timing import require_aware

_SERIES_SHAPE = re.compile(r"[A-Z0-9]{1,3}")


@dataclass(frozen=True, slots=True)
class Series:
    """NSE series code of a bar, e.g. EQ, BE, BZ. Data about the bar, not part of identity."""

    code: str

    def __post_init__(self) -> None:
        if not _SERIES_SHAPE.fullmatch(self.code):
            raise ValueError(f"not a series code: {self.code!r}")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Reference to the evidence for an event (exchange circular, announcement, file)."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("source reference must be non-empty")


@dataclass(frozen=True, slots=True)
class SeriesChange:
    """An instrument moves from one series to another on `effective_date`."""

    instrument_id: InstrumentId
    effective_date: date
    from_series: Series
    to_series: Series
    known_at: datetime
    source: SourceRef

    def __post_init__(self) -> None:
        require_aware(self.known_at)
        if self.from_series == self.to_series:
            raise ValueError("from_series and to_series must differ")


class AbsenceReason(Enum):
    SUSPENDED = "suspended"
    SERIES_CHANGED = "series_changed"
    DELISTED = "delisted"
    NOT_YET_LISTED = "not_yet_listed"
    DATA_UNAVAILABLE = "data_unavailable"
    MISSING_OBSERVATION = "missing_observation"


_LEGITIMATE = frozenset(
    {
        AbsenceReason.SUSPENDED,
        AbsenceReason.SERIES_CHANGED,
        AbsenceReason.DELISTED,
        AbsenceReason.NOT_YET_LISTED,
    }
)
_NEEDS_SOURCE = _LEGITIMATE - {AbsenceReason.SERIES_CHANGED}


@dataclass(frozen=True, slots=True)
class Absence:
    """No bar for `instrument_id` on `session`, with the reason stated explicitly.

    `known_at` is when the absence became observable (normally when that session's file is
    published). Date consistency is checked for series changes; dates of suspensions, delistings
    and listings are not checked here because listing dates are not modelled yet.
    """

    instrument_id: InstrumentId
    session: date
    reason: AbsenceReason
    known_at: datetime
    source: SourceRef | None = None
    series_change: SeriesChange | None = None

    def __post_init__(self) -> None:
        require_aware(self.known_at)
        if self.reason in _NEEDS_SOURCE and self.source is None:
            raise ValueError(f"{self.reason.value} absence requires a source reference")
        if self.reason is AbsenceReason.SERIES_CHANGED:
            change = self.series_change
            if change is None:
                raise ValueError("series_changed absence requires the linked series change")
            if change.instrument_id != self.instrument_id:
                raise ValueError("series change refers to a different instrument")
            if self.session < change.effective_date:
                raise ValueError("series_changed absence is dated before the series change")
            if change.known_at > self.known_at:
                raise ValueError("series change was not yet known when the absence was observed")
        elif self.series_change is not None:
            raise ValueError("series_change may only accompany a series_changed absence")

    @property
    def is_legitimate(self) -> bool:
        return self.reason in _LEGITIMATE

    @classmethod
    def classify(
        cls,
        instrument_id: InstrumentId,
        session: date,
        claimed: AbsenceReason,
        known_at: datetime,
        source: SourceRef | None = None,
        series_change: SeriesChange | None = None,
    ) -> "Absence":
        """Keep a claim that has its evidence; otherwise record MISSING_OBSERVATION."""
        try:
            return cls(instrument_id, session, claimed, known_at, source, series_change)
        except ValueError:
            if claimed not in _LEGITIMATE:
                raise
            return cls(instrument_id, session, AbsenceReason.MISSING_OBSERVATION, known_at)
