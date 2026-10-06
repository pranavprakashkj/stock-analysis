"""In-memory MarketDataProvider over an explicit MarketDataset (task 1.6).

It answers only from the records it is given: no clock, randomness, environment, files or network,
and it never manufactures an observation. Results depend only on the dataset's content: records are
sorted on explicit field values (instants compared as instants), never on `repr` or input order.
"""

from datetime import UTC, date, datetime

from trading.application.market_dataset import MarketDataset
from trading.application.ports import (
    KnowledgeUnavailableError,
    OutsideCoverageError,
    UnknownInstrumentError,
)
from trading.domain.availability import Absence, SeriesChange
from trading.domain.checks import require_date, require_instance
from trading.domain.corporate_actions import CorporateAction
from trading.domain.identity import IdentityMap, InstrumentId
from trading.domain.market import Bar
from trading.domain.timing import is_known, require_aware
from trading.domain.universe import IndexMembershipChange, IndexName


def _action_key(c: CorporateAction) -> tuple[object, ...]:
    assert c.known_at is not None  # only resolved actions are ever returned
    return (
        c.ex_date,
        c.kind.value,
        c.known_at.astimezone(UTC),
        c.record_date or date.min,
        c.announcement_date or date.min,
        c.source.value,
        c.confidence.value,
    )


def _membership_key(m: IndexMembershipChange) -> tuple[object, ...]:
    return (m.effective_date, m.instrument_id.value, m.change.value, m.known_at.astimezone(UTC))


class FakeMarketData:
    def __init__(self, dataset: MarketDataset) -> None:
        self._data = require_instance("dataset", dataset, MarketDataset)

    def _as_of(self, as_of: datetime) -> datetime:
        require_aware(as_of)
        if as_of > self._data.knowledge_cutoff:
            raise KnowledgeUnavailableError(
                f"as_of {as_of} is after the knowledge cut-off {self._data.knowledge_cutoff}"
            )
        return as_of

    def _instrument(self, instrument_id: InstrumentId, as_of: datetime) -> InstrumentId:
        """Known only once its identity is public, so a query cannot reveal a future listing."""
        require_instance("instrument_id", instrument_id, InstrumentId)
        if not any(
            e.instrument_id == instrument_id and is_known(e.known_at, as_of)
            for e in self._data.identity
        ):
            raise UnknownInstrumentError(f"unknown instrument {instrument_id.value} at {as_of}")
        return instrument_id

    def _range(self, start: date, end: date) -> tuple[date, date]:
        require_date("start", start)
        require_date("end", end)
        if start > end:
            raise ValueError(f"start {start} is after end {end}")
        first, last = self._data.coverage_start, self._data.coverage_end
        if start < first or end > last:
            raise OutsideCoverageError(f"{start}..{end} is outside coverage {first}..{last}")
        return start, end

    def identity_map(self, *, as_of: datetime) -> IdentityMap:
        as_of = self._as_of(as_of)
        return IdentityMap(self._data.identity, self._data.identity_ends).as_known_at(as_of)

    def bars(
        self, instrument_id: InstrumentId, start: date, end: date, *, as_of: datetime
    ) -> tuple[Bar, ...]:
        as_of = self._as_of(as_of)
        instrument_id = self._instrument(instrument_id, as_of)
        start, end = self._range(start, end)
        found = [
            b
            for b in self._data.bars
            if b.instrument_id == instrument_id
            and start <= b.observation_date <= end
            and is_known(b.known_at, as_of)
        ]
        return tuple(sorted(found, key=lambda b: (b.observation_date, b.series.code)))

    def absences(
        self, instrument_id: InstrumentId, start: date, end: date, *, as_of: datetime
    ) -> tuple[Absence, ...]:
        as_of = self._as_of(as_of)
        instrument_id = self._instrument(instrument_id, as_of)
        start, end = self._range(start, end)
        found = [
            a
            for a in self._data.absences
            if a.instrument_id == instrument_id
            and start <= a.session <= end
            and is_known(a.known_at, as_of)
        ]
        return tuple(sorted(found, key=lambda a: a.session))

    def series_changes(
        self, instrument_id: InstrumentId, *, as_of: datetime
    ) -> tuple[SeriesChange, ...]:
        as_of = self._as_of(as_of)
        instrument_id = self._instrument(instrument_id, as_of)
        found = [
            s
            for s in self._data.series_changes
            if s.instrument_id == instrument_id and is_known(s.known_at, as_of)
        ]
        return tuple(sorted(found, key=lambda s: s.effective_date))

    def corporate_actions(
        self, instrument_id: InstrumentId, *, as_of: datetime
    ) -> tuple[CorporateAction, ...]:
        as_of = self._as_of(as_of)
        instrument_id = self._instrument(instrument_id, as_of)
        found = [
            c
            for c in self._data.corporate_actions
            if c.instrument_id == instrument_id
            and c.known_at is not None  # unresolved: visible at no as_of, no fallback time
            and is_known(c.known_at, as_of)
        ]
        return tuple(sorted(found, key=_action_key))

    def membership_changes(
        self, index: IndexName, *, as_of: datetime
    ) -> tuple[IndexMembershipChange, ...]:
        as_of = self._as_of(as_of)
        require_instance("index", index, IndexName)
        found = [
            m for m in self._data.membership if m.index is index and is_known(m.known_at, as_of)
        ]
        return tuple(sorted(found, key=_membership_key))
