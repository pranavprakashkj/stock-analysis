"""Typed corporate actions, stored exactly as published (task 1.4; ADR-007, ADR-019 §2).

Phase 1 applies no corporate-action rule and infers no knowledge time (ADR-007 register item 4).
Kind-specific terms (split ratios, dividend amounts) are not modelled yet; the parser task that
extracts them (1.12) adds them.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from trading.domain.availability import SourceRef
from trading.domain.checks import require_date, require_instance
from trading.domain.identity import InstrumentId
from trading.domain.timing import require_aware, start_of_date


class CorporateActionKind(Enum):
    """ADR-007 categories. OTHER is an unrecognised type: a data-quality failure (U28)."""

    SPLIT = "split"  # splits and consolidations
    BONUS = "bonus"
    DIVIDEND = "dividend"  # cash dividends, including special dividends
    MERGER = "merger"
    DEMERGER = "demerger"
    RIGHTS = "rights"
    BUYBACK = "buyback"
    OTHER = "other"


class ParseConfidence(Enum):
    """How confidently the source text was classified. LOW is a data-quality failure (task 1.10)."""

    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """A corporate action of one instrument with its published dates.

    - `ex_date` is the exchange-published ex-date, never derived from the record date (C1).
      It is the action's effective date (ADR-018 §1).
    - `record_date` and `announcement_date` are kept when published, else None (real records can
      lack a record date).
    - `known_at` is when the action became known. With an announcement date it is required and
      cannot precede that date; a date-only announcement is known at the end of that date
      (ADR-018 §1). A resolved action has a trustworthy `known_at`.
    - `known_at=None` is allowed only without an announcement date and means **unresolved**
      (ADR-007 C4, U1-U3; ADR-018 §2 clarification). An unresolved action:
      - is a parsed record only, never visible in any as-of context: the type checker refuses
        `known_by`/`effective_on` on this type, and at runtime they raise on a None knowledge time
        rather than treating it as known;
      - is never given a fallback timestamp;
      - influences no strategy, backtest, evaluation, paper trading or adjustment until resolved;
      - is a data-quality failure where a data-quality or evaluation boundary needs it (task 1.10).
    """

    instrument_id: InstrumentId
    kind: CorporateActionKind
    ex_date: date
    record_date: date | None
    announcement_date: date | None
    known_at: datetime | None
    source: SourceRef
    confidence: ParseConfidence

    def __post_init__(self) -> None:
        require_instance("instrument_id", self.instrument_id, InstrumentId)
        require_instance("kind", self.kind, CorporateActionKind)
        require_date("ex_date", self.ex_date)
        if self.record_date is not None:
            require_date("record_date", self.record_date)
        if self.announcement_date is not None:
            require_date("announcement_date", self.announcement_date)
        require_instance("source", self.source, SourceRef)
        require_instance("confidence", self.confidence, ParseConfidence)
        announced = self.announcement_date
        if announced is not None and self.known_at is None:
            raise ValueError("an action with an announcement date must carry its known_at")
        if self.known_at is not None:
            require_aware(self.known_at)
            if announced is not None and self.known_at < start_of_date(announced):
                raise ValueError(
                    f"action cannot be known before its announcement date {announced}: "
                    f"{self.known_at}"
                )

    @property
    def effective_date(self) -> date:
        return self.ex_date
