"""Application ports for market data (task 1.6; ADR-001 D1, ADR-018 §1, ADR-019, ADR-020).

`MarketDataProvider` is what the application may ask; adapters (a file provider, a snapshot reader,
the test fake) answer it. Every query is keyed by `InstrumentId` and takes a keyword-only `as_of`:
- **Known by `as_of`:** a record is returned only if its `known_at <= as_of`. Observation dates,
  ex-dates and effective dates never grant visibility alone. Corporate actions are filtered by
  knowledge time, never by ex-date; an action with an unresolved knowledge time (`known_at=None`) is
  never returned, at any `as_of`, and no fallback time is invented (ADR-018 §2).
- **All series:** bars of every series are returned, tagged with their series (ADR-019 §3).
- **Typed absence:** absent observations are `Absence` records with their stated reason; a provider
  never upgrades or downgrades a reason, and never fills a gap with a manufactured bar. A session
  (per the trading calendar) with neither a bar nor an absence is a **missing observation**: the
  data-quality check (task 1.10) reports it; consumers never read the silence as "closed".
- **Series changes** are their own records, visible from their own knowledge time (not only from
  the absence they later cause), so a known move from EQ to BE is visible before it takes effect.
- **Explicit limits:** `UnknownInstrumentError` for an instrument not known by `as_of` (absent from
  the data, or its identity not yet public, so a query cannot reveal a future listing);
  `OutsideCoverageError` for dates the data does not cover; `KnowledgeUnavailableError` for an
  `as_of` later than the instant up to which the data is complete. Empty results mean "nothing
  known", never "not covered".
- Results are tuples in a deterministic order that depends only on the data's content.

Identity: an assignment and its end are separate records (`IdentityMapEntry`, `IdentityMapEnd`),
each with its own knowledge time, so an as-of identity view never shows an end not yet known.

Holdout access control (ADR-018 §3, task 4.0) wraps these queries from outside; the ports carry the
explicit `as_of` it needs and have no switch to bypass it. Provider details (files, tokens, URLs,
pagination, vendor objects) never appear here.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from trading.application.market_dataset import MarketDataset
from trading.domain.availability import Absence, SeriesChange
from trading.domain.corporate_actions import CorporateAction
from trading.domain.identity import IdentityMap, InstrumentId
from trading.domain.market import Bar
from trading.domain.universe import IndexMembershipChange, IndexName

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class MarketDataError(Exception):
    """A market-data query cannot be answered. Catch the specific subclasses."""


class UnknownInstrumentError(MarketDataError):
    """The instrument does not exist in the provider's data."""


class OutsideCoverageError(MarketDataError):
    """The requested dates lie outside the provider's coverage: the answer is unknown, not empty."""


class KnowledgeUnavailableError(MarketDataError):
    """`as_of` is later than the instant up to which the provider's data is complete."""


class UnknownSnapshotError(Exception):
    """No snapshot with this id exists in the store."""


@dataclass(frozen=True, slots=True)
class SnapshotId:
    """Canonical snapshot identity: lowercase SHA-256 hex of the canonical-v1 content (ADR-020)."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(f"SnapshotId must be a str, not {type(self.value).__name__}")
        if not _SHA256_HEX.fullmatch(self.value):
            raise ValueError(f"SnapshotId must be 64 lowercase hex characters: {self.value!r}")


class MarketDataProvider(Protocol):
    def identity_map(self, *, as_of: datetime) -> IdentityMap:
        """Symbol mapping entries known by `as_of` (Symbol is display only, ADR-019 §1)."""
        ...

    def bars(
        self, instrument_id: InstrumentId, start: date, end: date, *, as_of: datetime
    ) -> tuple[Bar, ...]:
        """Bars of every series observed from `start` to `end` (inclusive), known by `as_of`.
        Ordered by observation date, then series code."""
        ...

    def absences(
        self, instrument_id: InstrumentId, start: date, end: date, *, as_of: datetime
    ) -> tuple[Absence, ...]:
        """Typed absences for sessions from `start` to `end` (inclusive), known by `as_of`.
        Ordered by session."""
        ...

    def series_changes(
        self, instrument_id: InstrumentId, *, as_of: datetime
    ) -> tuple[SeriesChange, ...]:
        """Series changes known by `as_of`, whatever their effective date. Ordered by effective
        date."""
        ...

    def corporate_actions(
        self, instrument_id: InstrumentId, *, as_of: datetime
    ) -> tuple[CorporateAction, ...]:
        """Actions known by `as_of`, whatever their ex-date. Every returned action has a resolved
        `known_at`; unresolved ones are never returned. Ordered by ex-date, then content.

        Open (Phase 2): the return type still allows `known_at=None`, so the type checker cannot
        prove the guarantee and `effective_on` does not accept these records; callers filter by
        `ex_date` among the returned (known) actions."""
        ...

    def membership_changes(
        self, index: IndexName, *, as_of: datetime
    ) -> tuple[IndexMembershipChange, ...]:
        """Membership changes of `index` known by `as_of`, whatever their effective date.
        Ordered by effective date, then content."""
        ...


class SnapshotStore(Protocol):
    """Immutable, content-addressed storage of validated datasets. **Provisional**: task 1.11
    implements it and is expected to revise this signature.

    Intent: `write` returns the canonical id of the content (ADR-020), returns the same id for equal
    content and never overwrites; `read` returns the dataset written under that id, or raises
    `UnknownSnapshotError`. Open for 1.11 (recorded in tasks/todo.md):
    - ADR-020 defines the id of one table; a dataset is several tables plus origin, coverage and
      knowledge cut-off, so how they combine into one id needs an ADR-020 addendum;
    - provenance (source-file manifest) and snapshot metadata are not parameters yet;
    - `read` is unconditioned storage access; sealing by knowledge-time window (ADR-018, task 4.0)
      must sit in front of it before any real data is stored."""

    def write(self, dataset: MarketDataset) -> SnapshotId: ...

    def read(self, snapshot_id: SnapshotId) -> MarketDataset: ...
