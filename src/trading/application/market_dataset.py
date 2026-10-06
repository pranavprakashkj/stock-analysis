"""One validated body of market data, as stored behind the ports (task 1.6).

A `MarketDataset` is what a snapshot holds (`SnapshotStore`) and what a provider answers from. Its
invariants hold for every adapter, so a malformed fixture or import is rejected here, not hidden:
- every record refers to an instrument in the identity map (keyed by `InstrumentId`, not `Symbol`);
- bars and absences are observations inside the coverage range (corporate-action ex-dates and
  membership or series-change effective dates may lie beyond it: a known future event is valid);
- every resolved knowledge time is at or before `knowledge_cutoff`, the instant up to which the
  data is complete; unresolved corporate actions (`known_at=None`) are stored but never visible;
- uniqueness: one bar per (instrument, series, date), one absence per (instrument, date), one
  series change per (instrument, effective date), one membership change per (index, instrument,
  effective date); identical corporate actions are rejected (two different actions on one ex-date
  can be legitimate, so near-duplicates are a data-quality question for task 1.10);
- every SERIES_CHANGED absence's linked change is itself one of `series_changes`, so a known change
  is visible from its own knowledge time, not only from the absence it causes;
- no absence on a day that has a bar, except a SERIES_CHANGED absence next to the new-series bar.
Cross-record plausibility (e.g. a bar in the old series after a change, a bar outside the symbol's
validity) is task 1.10. Record order carries no meaning. `origin` is ADR-017 §1's label.
Error messages name record keys only, never prices or other values.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from trading.domain.availability import Absence, Series, SeriesChange
from trading.domain.checks import require_date, require_instance
from trading.domain.corporate_actions import CorporateAction
from trading.domain.identity import IdentityMap, IdentityMapEnd, IdentityMapEntry, InstrumentId
from trading.domain.market import Bar
from trading.domain.timing import require_aware
from trading.domain.universe import IndexMembershipChange


class DataOrigin(Enum):
    SYNTHETIC = "synthetic"
    REAL = "real"


def _records[RecordT](name: str, value: object, record_type: type[RecordT]) -> tuple[RecordT, ...]:
    records = require_instance(name, value, tuple)
    for index, record in enumerate(records):
        require_instance(f"{name}[{index}]", record, record_type)
    return records


def _reject_duplicates(kind: str, keyed: Iterable[tuple[object, str]]) -> None:
    """`keyed` yields (uniqueness key, short label naming the record without its values)."""
    seen: set[object] = set()
    for key, label in keyed:
        if key in seen:
            raise ValueError(f"duplicate {kind}: {label}")
        seen.add(key)


@dataclass(frozen=True, slots=True)
class MarketDataset:
    origin: DataOrigin
    coverage_start: date
    coverage_end: date
    knowledge_cutoff: datetime
    identity: tuple[IdentityMapEntry, ...]
    identity_ends: tuple[IdentityMapEnd, ...]
    bars: tuple[Bar, ...]
    absences: tuple[Absence, ...]
    series_changes: tuple[SeriesChange, ...]
    corporate_actions: tuple[CorporateAction, ...]
    membership: tuple[IndexMembershipChange, ...]

    def __post_init__(self) -> None:
        require_instance("origin", self.origin, DataOrigin)
        require_date("coverage_start", self.coverage_start)
        require_date("coverage_end", self.coverage_end)
        if self.coverage_end < self.coverage_start:
            raise ValueError(
                f"coverage_end {self.coverage_end} is before coverage_start {self.coverage_start}"
            )
        require_aware(self.knowledge_cutoff)
        identity = _records("identity", self.identity, IdentityMapEntry)
        identity_ends = _records("identity_ends", self.identity_ends, IdentityMapEnd)
        bars = _records("bars", self.bars, Bar)
        absences = _records("absences", self.absences, Absence)
        changes = _records("series_changes", self.series_changes, SeriesChange)
        actions = _records("corporate_actions", self.corporate_actions, CorporateAction)
        membership = _records("membership", self.membership, IndexMembershipChange)

        # Raises IdentityError on overlapping, conflicting or unmatched assignments and ends.
        IdentityMap(identity, identity_ends)
        instruments = frozenset(entry.instrument_id for entry in identity)
        referenced: list[InstrumentId] = [
            *(r.instrument_id for r in bars),
            *(r.instrument_id for r in absences),
            *(r.instrument_id for r in changes),
            *(r.instrument_id for r in actions),
            *(r.instrument_id for r in membership),
        ]
        for instrument in referenced:
            if instrument not in instruments:
                raise ValueError(f"{instrument.value} is not in the identity map")

        for observed in (*(b.observation_date for b in bars), *(a.session for a in absences)):
            if not self.coverage_start <= observed <= self.coverage_end:
                raise ValueError(
                    f"observation {observed} outside coverage "
                    f"{self.coverage_start}..{self.coverage_end}"
                )

        known_times = [
            *(e.known_at for e in identity),
            *(e.known_at for e in identity_ends),
            *(b.known_at for b in bars),
            *(a.known_at for a in absences),
            *(s.known_at for s in changes),
            *(c.known_at for c in actions if c.known_at is not None),
            *(m.known_at for m in membership),
        ]
        for known_at in known_times:
            if known_at > self.knowledge_cutoff:
                raise ValueError(
                    f"record known after the knowledge cut-off {self.knowledge_cutoff}: {known_at}"
                )

        _reject_duplicates(
            "bar",
            (
                (
                    (b.instrument_id, b.series, b.observation_date),
                    f"{b.instrument_id.value} {b.series.code} {b.observation_date}",
                )
                for b in bars
            ),
        )
        _reject_duplicates(
            "absence",
            (
                ((a.instrument_id, a.session), f"{a.instrument_id.value} {a.session}")
                for a in absences
            ),
        )
        _reject_duplicates(
            "series change",
            (
                ((s.instrument_id, s.effective_date), f"{s.instrument_id.value} {s.effective_date}")
                for s in changes
            ),
        )
        _reject_duplicates(
            "corporate action",
            ((c, f"{c.instrument_id.value} {c.kind.value} ex {c.ex_date}") for c in actions),
        )
        _reject_duplicates(
            "or conflicting membership change",
            (
                (
                    (m.index, m.instrument_id, m.effective_date),
                    f"{m.index.value} {m.instrument_id.value} {m.effective_date}",
                )
                for m in membership
            ),
        )

        known_changes = set(changes)
        for absence in absences:
            if absence.series_change is not None and absence.series_change not in known_changes:
                raise ValueError(
                    f"{absence.instrument_id.value} {absence.session}: the linked series change "
                    "is missing from series_changes"
                )

        series_by_day: dict[tuple[InstrumentId, date], set[Series]] = {}
        for b in bars:
            series_by_day.setdefault((b.instrument_id, b.observation_date), set()).add(b.series)
        for absence in absences:
            series = series_by_day.get((absence.instrument_id, absence.session))
            if series is None:
                continue
            change = absence.series_change
            if change is not None and series == {change.to_series}:
                continue  # SERIES_CHANGED: no old-series bar; the new-series bar is returned
            raise ValueError(
                f"{absence.instrument_id.value} {absence.session} has both a bar and a "
                f"{absence.reason.value} absence"
            )
