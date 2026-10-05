"""Market-data value objects (task 1.4; ADR-001 D1, ADR-018 §1, ADR-019 §3)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from trading.domain.availability import Series
from trading.domain.checks import require_date, require_finite_decimal, require_instance
from trading.domain.identity import InstrumentId
from trading.domain.timing import require_aware, start_of_date

_PRICE_FIELDS = ("open", "high", "low", "close")


@dataclass(frozen=True, slots=True)
class Bar:
    """One unadjusted end-of-day bar of an instrument in one series, exactly as published.

    - Keyed by `InstrumentId`; `series` is data about the bar, not identity (ADR-019 §3).
    - Prices are rupees per share as published, never rounded. `traded_value` is the published
      total traded value in rupees (ADR-012 §2a measures its median).
    - `observation_date` is the session the bar describes; `known_at` is when it became available
      (publication of that session's file, ADR-018 §1). It cannot precede the observation date.
    - Only single-bar invariants are enforced here. Cross-field plausibility (e.g. traded value
      against volume and price range) is a data-quality rule (task 1.10).
    """

    instrument_id: InstrumentId
    series: Series
    observation_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    traded_value: Decimal
    known_at: datetime

    def __post_init__(self) -> None:
        require_instance("instrument_id", self.instrument_id, InstrumentId)
        require_instance("series", self.series, Series)
        require_date("observation_date", self.observation_date)
        for name in _PRICE_FIELDS:
            if require_finite_decimal(name, getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be > 0: {getattr(self, name)}")
        if self.high < max(self.open, self.close):
            raise ValueError(f"high {self.high} is below max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError(f"low {self.low} is above min(open, close)")
        if require_instance("volume", self.volume, int) < 0:
            raise ValueError(f"volume must be >= 0: {self.volume}")
        if require_finite_decimal("traded_value", self.traded_value).is_signed():
            # is_signed() also rejects -0, which equals 0 but would print differently.
            raise ValueError(f"traded_value must be >= 0 and not -0: {self.traded_value}")
        if require_aware(self.known_at) < start_of_date(self.observation_date):
            raise ValueError(
                f"bar of {self.observation_date} cannot be known before its observation date: "
                f"{self.known_at}"
            )
