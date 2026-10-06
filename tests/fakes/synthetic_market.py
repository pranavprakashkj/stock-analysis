"""A small synthetic market dataset (January 2030). No real symbols, prices, actions or memberships.

Instruments:
- INS-A: symbol AAA until 7 Jan, renamed AAB from 8 Jan (rename announced 3 Jan); one known split
  with an ex-date after coverage, one unresolved dividend (no announcement, known_at None).
- INS-B: EQ until 7 Jan, BE from 8 Jan (series change; the EQ bar is absent as SERIES_CHANGED).
- INS-C: suspended 9 Jan (sourced), missing on 10 Jan (an unsourced suspension claim, downgraded),
  not covered by the source on 11 Jan, delisted from 14 Jan (symbol CCC ends 13 Jan; that end is
  announced 10 Jan).
- INS-D: not yet listed on 2 Jan; listed from 3 Jan.
Every bar is known at 18:00 IST on its observation date.

The fixture is deliberately incomplete: many instrument-days have neither a bar nor an absence
(e.g. INS-A after 8 Jan, every instrument on 4 Jan). Providers return nothing for them; deciding
whether such a day was a session with a missing observation is task 1.10 (with the calendar).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from trading.application.market_dataset import DataOrigin, MarketDataset
from trading.domain.availability import Absence, AbsenceReason, Series, SeriesChange, SourceRef
from trading.domain.corporate_actions import CorporateAction, CorporateActionKind, ParseConfidence
from trading.domain.identity import IdentityMapEnd, IdentityMapEntry, InstrumentId, Symbol
from trading.domain.market import Bar
from trading.domain.timing import IST
from trading.domain.universe import IndexMembershipChange, IndexName, MembershipChange

A, B, C, D = (InstrumentId(f"INS-{x}") for x in "ABCD")
EQ, BE = Series("EQ"), Series("BE")
COVERAGE_START, COVERAGE_END = date(2030, 1, 2), date(2030, 1, 14)
KNOWLEDGE_CUTOFF = datetime(2030, 1, 14, 20, 0, tzinfo=IST)
LISTED = datetime(2029, 12, 1, 18, 0, tzinfo=IST)
RENAME_ANNOUNCED = datetime(2030, 1, 3, 19, 0, tzinfo=IST)
SPLIT_ANNOUNCED = datetime(2030, 1, 5, 18, 0, tzinfo=IST)
REMOVAL_ANNOUNCED = datetime(2030, 1, 8, 20, 0, tzinfo=IST)
DELISTING_ANNOUNCED = datetime(2030, 1, 10, 18, 0, tzinfo=IST)


def day(n: int) -> date:
    return date(2030, 1, n)


def published(n: int) -> datetime:
    """Knowledge time of the bar (or absence) observed on 2030-01-n."""
    return datetime(2030, 1, n, 18, 0, tzinfo=IST)


def bar(instrument: InstrumentId, series: Series, n: int, close: str = "100.00") -> Bar:
    price = Decimal(close)
    return Bar(instrument, series, day(n), price, price, price, price, 10, price * 10, published(n))


def source(text: str) -> SourceRef:
    return SourceRef(f"synthetic:{text}")


SERIES_CHANGE_B = SeriesChange(B, day(8), EQ, BE, published(7), source("series-change-b"))

IDENTITY = (
    IdentityMapEntry(A, Symbol("AAA"), date(2029, 12, 1), LISTED),
    IdentityMapEntry(A, Symbol("AAB"), day(8), RENAME_ANNOUNCED),
    IdentityMapEntry(B, Symbol("BBB"), date(2029, 12, 1), LISTED),
    IdentityMapEntry(C, Symbol("CCC"), date(2029, 12, 1), LISTED),
    IdentityMapEntry(D, Symbol("DDD"), day(3), published(2)),
)
# Ends are separate records with their own knowledge time (ADR-018 §2): AAA ends with the rename,
# CCC with the delisting announced on 10 Jan.
IDENTITY_ENDS = (
    IdentityMapEnd(A, Symbol("AAA"), date(2029, 12, 1), day(7), RENAME_ANNOUNCED),
    IdentityMapEnd(C, Symbol("CCC"), date(2029, 12, 1), day(13), DELISTING_ANNOUNCED),
)

BARS = (
    *(bar(A, EQ, n) for n in (2, 3, 7, 8)),
    *(bar(B, EQ, n) for n in (2, 3, 7)),
    bar(B, BE, 8, "90.00"),
    *(bar(C, EQ, n) for n in (2, 3, 7, 8)),
    *(bar(D, EQ, n) for n in (3, 7, 8)),
)

ABSENCES = (
    Absence(B, day(8), AbsenceReason.SERIES_CHANGED, published(8), series_change=SERIES_CHANGE_B),
    Absence(C, day(9), AbsenceReason.SUSPENDED, published(9), source("suspension-c")),
    Absence.classify(C, day(10), AbsenceReason.SUSPENDED, published(10)),  # unsourced -> missing
    Absence(C, day(11), AbsenceReason.DATA_UNAVAILABLE, published(11)),
    Absence(C, day(14), AbsenceReason.DELISTED, published(14), source("delisting-c")),
    Absence(D, day(2), AbsenceReason.NOT_YET_LISTED, published(2), source("listing-d")),
)

SPLIT_A = CorporateAction(
    A,
    CorporateActionKind.SPLIT,
    ex_date=date(2030, 1, 20),
    record_date=date(2030, 1, 20),
    announcement_date=day(5),
    known_at=SPLIT_ANNOUNCED,
    source=source("split-a"),
    confidence=ParseConfidence.HIGH,
)
UNRESOLVED_DIVIDEND_A = CorporateAction(
    A,
    CorporateActionKind.DIVIDEND,
    ex_date=day(9),
    record_date=day(9),
    announcement_date=None,
    known_at=None,
    source=source("dividend-a"),
    confidence=ParseConfidence.HIGH,
)

MEMBERSHIP = (
    IndexMembershipChange(
        IndexName.NIFTY_100, A, MembershipChange.ADDED, day(2), LISTED, source("index-2029-12")
    ),
    IndexMembershipChange(
        IndexName.NIFTY_100,
        C,
        MembershipChange.REMOVED,
        date(2030, 1, 15),
        REMOVAL_ANNOUNCED,
        source("index-2030-01"),
    ),
)


def dataset(**overrides: Any) -> MarketDataset:
    fields: dict[str, Any] = {
        "origin": DataOrigin.SYNTHETIC,
        "coverage_start": COVERAGE_START,
        "coverage_end": COVERAGE_END,
        "knowledge_cutoff": KNOWLEDGE_CUTOFF,
        "identity": IDENTITY,
        "identity_ends": IDENTITY_ENDS,
        "bars": BARS,
        "absences": ABSENCES,
        "series_changes": (SERIES_CHANGE_B,),
        "corporate_actions": (SPLIT_A, UNRESOLVED_DIVIDEND_A),
        "membership": MEMBERSHIP,
    }
    fields.update(overrides)
    return MarketDataset(**fields)
