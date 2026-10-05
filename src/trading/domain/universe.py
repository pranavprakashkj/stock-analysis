"""Universe value objects (task 1.4; ADR-002, ADR-012 §2a)."""

from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from trading.domain.availability import SourceRef
from trading.domain.checks import require_date, require_finite_decimal, require_instance
from trading.domain.identity import InstrumentId
from trading.domain.timing import require_aware


class IndexName(Enum):
    """Indexes whose membership is modelled. Closed, so spelling variants cannot split one index."""

    NIFTY_100 = "NIFTY 100"  # the V1 universe (ADR-002)


class MembershipChange(Enum):
    ADDED = "added"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class IndexMembershipChange:
    """An instrument joins or leaves an index on `effective_date` (ADR-002 §1-2).

    Membership is a sequence of dated changes rather than spans, because each change has its own
    announcement (`known_at`) and source. Membership switches on the effective date, never on the
    announcement date; visibility depends on `known_at` (ADR-018 §1).
    """

    index: IndexName
    instrument_id: InstrumentId
    change: MembershipChange
    effective_date: date
    known_at: datetime
    source: SourceRef

    def __post_init__(self) -> None:
        require_instance("index", self.index, IndexName)
        require_instance("instrument_id", self.instrument_id, InstrumentId)
        require_instance("change", self.change, MembershipChange)
        require_date("effective_date", self.effective_date)
        require_aware(self.known_at)
        require_instance("source", self.source, SourceRef)


_FRACTIONS = frozenset({"max_participation", "order_liquidity_fraction"})


@dataclass(frozen=True, slots=True)
class LiquidityThresholds:
    """Data-derived liquidity safety thresholds (ADR-012 §2a). Shape only.

    Every field is required and has no default. Values come only from the locked config loader
    (ADR-017, task 4.0); this type is not wired to environment variables or general settings.
    `min_price` and `min_median_traded_value` are rupees; the other two are fractions in (0, 1]
    (0.005 means 0.5%).
    """

    min_price: Decimal
    min_median_traded_value: Decimal
    max_participation: Decimal
    order_liquidity_fraction: Decimal

    def __post_init__(self) -> None:
        for field in fields(self):
            value = require_finite_decimal(field.name, getattr(self, field.name))
            if value <= 0:
                raise ValueError(f"{field.name} must be > 0: {value}")
            if field.name in _FRACTIONS and value > 1:
                raise ValueError(f"{field.name} must be <= 1: {value}")
