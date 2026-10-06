"""Task 1.6: MarketDataset, one validated body of market data behind the ports.

Malformed fixtures are rejected at construction, so no adapter (fake or real) can hide them.
"""

import dataclasses
from datetime import date, datetime, timedelta

import pytest
from fakes.synthetic_market import (
    ABSENCES,
    BARS,
    BE,
    EQ,
    IDENTITY,
    IDENTITY_ENDS,
    KNOWLEDGE_CUTOFF,
    LISTED,
    SERIES_CHANGE_B,
    SPLIT_A,
    A,
    B,
    C,
    bar,
    dataset,
    day,
    published,
    source,
)

from trading.application.market_dataset import DataOrigin
from trading.domain.availability import Absence, AbsenceReason, Series, SeriesChange
from trading.domain.identity import (
    IdentityError,
    IdentityMapEnd,
    IdentityMapEntry,
    InstrumentId,
    Symbol,
)
from trading.domain.timing import IST
from trading.domain.universe import IndexMembershipChange, IndexName, MembershipChange

UNKNOWN = InstrumentId("INS-Z")
TICK = timedelta(microseconds=1)


def test_synthetic_dataset_is_valid() -> None:
    assert dataset().origin is DataOrigin.SYNTHETIC


def test_origins_are_synthetic_and_real() -> None:
    """ADR-017 §1: every snapshot carries origin = synthetic | real."""
    assert {o.value for o in DataOrigin} == {"synthetic", "real"}


# --- duplicates and conflicts -----------------------------------------------------------------


def test_duplicate_bar_is_rejected_naming_its_key_not_its_values() -> None:
    with pytest.raises(ValueError, match="duplicate bar: INS-A EQ 2030-01-02") as caught:
        dataset(bars=(*BARS, bar(A, EQ, 2, "101.37")))

    assert "101.37" not in str(caught.value)


def test_bars_of_two_series_on_one_day_are_not_duplicates() -> None:
    assert len(dataset(bars=(*BARS, bar(A, BE, 2))).bars) == len(BARS) + 1


def test_duplicate_absence_is_rejected() -> None:
    again = Absence(C, day(9), AbsenceReason.DATA_UNAVAILABLE, published(9))

    with pytest.raises(ValueError, match="duplicate absence: INS-C 2030-01-09"):
        dataset(absences=(*ABSENCES, again))


def test_absence_contradicting_a_bar_is_rejected() -> None:
    with pytest.raises(ValueError, match="INS-A 2030-01-02 has both a bar and a suspended absence"):
        dataset(
            absences=(
                *ABSENCES,
                Absence(A, day(2), AbsenceReason.SUSPENDED, published(2), source("s")),
            )
        )


def test_series_changed_absence_may_accompany_the_new_series_bar() -> None:
    """ADR-019 §3: no bar in the old series, and the new-series bar is returned."""
    assert (B, BE, day(8)) in {
        (b.instrument_id, b.series, b.observation_date) for b in dataset().bars
    }


def test_series_changed_absence_conflicts_with_an_old_series_bar() -> None:
    with pytest.raises(ValueError, match="has both a bar and a series_changed absence"):
        dataset(bars=(*BARS, bar(B, EQ, 8)))


def test_identical_corporate_action_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate corporate action: INS-A split ex 2030-01-20"):
        dataset(corporate_actions=(SPLIT_A, SPLIT_A))


def test_duplicate_membership_change_is_rejected() -> None:
    change = dataset().membership[0]

    with pytest.raises(ValueError, match="duplicate or conflicting membership change"):
        dataset(membership=(change, change))


def test_added_and_removed_on_the_same_effective_date_conflict() -> None:
    added = dataset().membership[0]
    removed = dataclasses.replace(added, change=MembershipChange.REMOVED)

    with pytest.raises(
        ValueError, match="duplicate or conflicting membership change: NIFTY 100 INS-A 2030-01-02"
    ):
        dataset(membership=(added, removed))


def test_two_series_changes_on_one_date_conflict() -> None:
    other = dataclasses.replace(SERIES_CHANGE_B, to_series=Series("BZ"))

    with pytest.raises(ValueError, match="duplicate series change: INS-B 2030-01-08"):
        dataset(series_changes=(SERIES_CHANGE_B, other))


def test_series_changed_absence_requires_its_change_among_series_changes() -> None:
    """Otherwise the known change would be visible only from the later absence."""
    with pytest.raises(ValueError, match="linked series change is missing from series_changes"):
        dataset(series_changes=())


def test_conflicting_identity_mapping_is_rejected() -> None:
    clash = IdentityMapEntry(B, Symbol("AAA"), day(2), LISTED)  # AAA is INS-A's until 7 Jan

    with pytest.raises(IdentityError, match="overlapping identity entries"):
        dataset(identity=(*IDENTITY, clash))


# --- references, coverage and knowledge cut-off -----------------------------------------------


@pytest.mark.parametrize(
    "field", ["bars", "absences", "series_changes", "corporate_actions", "membership"]
)
def test_records_of_unmapped_instruments_are_rejected(field: str) -> None:
    record = {
        "bars": bar(UNKNOWN, EQ, 2),
        "absences": Absence(UNKNOWN, day(2), AbsenceReason.DATA_UNAVAILABLE, published(2)),
        "series_changes": dataclasses.replace(SERIES_CHANGE_B, instrument_id=UNKNOWN),
        "corporate_actions": dataclasses.replace(SPLIT_A, instrument_id=UNKNOWN),
        "membership": IndexMembershipChange(
            IndexName.NIFTY_100, UNKNOWN, MembershipChange.ADDED, day(2), published(2), source("x")
        ),
    }[field]
    existing = getattr(dataset(), field)

    with pytest.raises(ValueError, match="INS-Z is not in the identity map"):
        dataset(**{field: (*existing, record)})


@pytest.mark.parametrize("outside", [date(2030, 1, 1), date(2030, 1, 15)], ids=["before", "after"])
def test_observations_outside_coverage_are_rejected(outside: date) -> None:
    early = bar(A, EQ, 2)
    stray = dataclasses.replace(early, observation_date=outside, known_at=published(outside.day))

    with pytest.raises(ValueError, match=r"outside coverage 2030-01-02\.\.2030-01-14"):
        dataset(bars=(*BARS, stray))


def test_corporate_action_ex_date_may_lie_beyond_coverage() -> None:
    """A known action with a later ex-date is legitimately visible (ADR-018 §1)."""
    assert SPLIT_A.ex_date > dataset().coverage_end


@pytest.mark.parametrize(
    "field", ["bars", "absences", "series_changes", "corporate_actions", "membership"]
)
def test_records_known_after_the_cutoff_are_rejected(field: str) -> None:
    late = datetime(2030, 1, 14, 20, 0, 1, tzinfo=IST)
    record = {
        "bars": dataclasses.replace(bar(A, EQ, 14), known_at=late),
        "absences": Absence(A, day(14), AbsenceReason.DATA_UNAVAILABLE, late),
        "series_changes": SeriesChange(A, day(20), EQ, BE, late, source("x")),
        "corporate_actions": dataclasses.replace(SPLIT_A, known_at=late),
        "membership": IndexMembershipChange(
            IndexName.NIFTY_100, B, MembershipChange.ADDED, day(20), late, source("x")
        ),
    }[field]
    existing = getattr(dataset(), field)

    with pytest.raises(ValueError, match="known after the knowledge cut-off"):
        dataset(**{field: (*existing, record)})


def test_identity_entry_known_after_the_cutoff_is_rejected() -> None:
    late = IdentityMapEntry(
        InstrumentId("INS-E"), Symbol("EEE"), day(14), datetime(2030, 1, 15, tzinfo=IST)
    )

    with pytest.raises(ValueError, match="known after the knowledge cut-off"):
        dataset(identity=(*IDENTITY, late))


def test_identity_end_known_after_the_cutoff_is_rejected() -> None:
    late = IdentityMapEnd(B, Symbol("BBB"), date(2029, 12, 1), day(14), KNOWLEDGE_CUTOFF + TICK)

    with pytest.raises(ValueError, match="known after the knowledge cut-off"):
        dataset(identity_ends=(*IDENTITY_ENDS, late))


def test_identity_end_without_its_assignment_is_rejected() -> None:
    stray = IdentityMapEnd(B, Symbol("XXX"), date(2029, 12, 1), day(14), LISTED)

    with pytest.raises(IdentityError, match="ends no assignment"):
        dataset(identity_ends=(*IDENTITY_ENDS, stray))


def test_record_known_exactly_at_the_cutoff_is_accepted() -> None:
    at_cutoff = dataclasses.replace(bar(A, EQ, 14), known_at=KNOWLEDGE_CUTOFF)

    assert at_cutoff in dataset(bars=(*BARS, at_cutoff)).bars


# --- malformed fields -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "identity",
        "identity_ends",
        "bars",
        "absences",
        "series_changes",
        "corporate_actions",
        "membership",
    ],
)
def test_collections_must_be_tuples(field: str) -> None:
    with pytest.raises(TypeError, match=f"{field} must be a tuple"):
        dataset(**{field: list(getattr(dataset(), field))})


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("identity", "IdentityMapEntry"),
        ("identity_ends", "IdentityMapEnd"),
        ("bars", "Bar"),
        ("absences", "Absence"),
        ("series_changes", "SeriesChange"),
        ("corporate_actions", "CorporateAction"),
        ("membership", "IndexMembershipChange"),
    ],
)
def test_collection_entries_must_have_the_right_type(field: str, expected: str) -> None:
    with pytest.raises(TypeError, match=rf"{field}\[0\] must be an? {expected}"):
        dataset(**{field: ("not a record",)})


def test_coverage_must_not_end_before_it_starts() -> None:
    with pytest.raises(ValueError, match="coverage_end 2030-01-01 is before coverage_start"):
        dataset(coverage_start=day(2), coverage_end=day(1), bars=(), absences=())


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("origin", "synthetic", TypeError),
        ("coverage_start", datetime(2030, 1, 2, tzinfo=IST), TypeError),
        ("knowledge_cutoff", datetime(2030, 1, 14, 20, 0), ValueError),
        ("knowledge_cutoff", day(14), TypeError),
    ],
    ids=["origin-str", "coverage-datetime", "cutoff-naive", "cutoff-date"],
)
def test_scalar_fields_are_validated(field: str, value: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        dataset(**{field: value})


def test_dataset_is_immutable() -> None:
    name = "bars"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(dataset(), name, ())
