"""Task 1.4: typed corporate actions stored exactly as published (ADR-007, ADR-019 §2).

Phase 1 applies no corporate-action rule and infers no knowledge time (ADR-007 register item 4).
"""

import dataclasses
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading.domain.availability import SourceRef
from trading.domain.corporate_actions import CorporateAction, CorporateActionKind, ParseConfidence
from trading.domain.identity import InstrumentId, Symbol
from trading.domain.timing import IST, effective_on, end_of_date, is_known, known_by

INSTRUMENT = InstrumentId("INS-0001")
EX_DATE = date(2024, 3, 15)
ANNOUNCED = date(2024, 3, 1)
KNOWN = datetime(2024, 3, 1, 18, 0, tzinfo=IST)
SOURCE = SourceRef("synthetic:ca-2024-03.csv#12")


def _action(**overrides: Any) -> CorporateAction:
    fields: dict[str, Any] = {
        "instrument_id": INSTRUMENT,
        "kind": CorporateActionKind.SPLIT,
        "ex_date": EX_DATE,
        "record_date": EX_DATE,
        "announcement_date": ANNOUNCED,
        "known_at": KNOWN,
        "source": SOURCE,
        "confidence": ParseConfidence.HIGH,
    }
    fields.update(overrides)
    return CorporateAction(**fields)


def test_kinds_are_the_adr_007_categories() -> None:
    assert {kind.value for kind in CorporateActionKind} == {
        "split",
        "bonus",
        "dividend",
        "merger",
        "demerger",
        "rights",
        "buyback",
        "other",
    }


def test_confidence_is_high_or_low() -> None:
    assert {c.value for c in ParseConfidence} == {"high", "low"}


def test_valid_action_keeps_the_published_fields_exactly() -> None:
    action = _action()

    assert (action.ex_date, action.record_date, action.announcement_date) == (
        EX_DATE,
        EX_DATE,
        ANNOUNCED,
    )
    assert action.source == SOURCE
    assert action.confidence is ParseConfidence.HIGH


def test_effective_date_is_the_published_ex_date_not_the_record_date() -> None:
    action = _action(ex_date=date(2019, 6, 13), record_date=date(2019, 6, 14))

    assert action.effective_date == date(2019, 6, 13)


@pytest.mark.parametrize("kind", list(CorporateActionKind))
def test_every_kind_can_be_represented(kind: CorporateActionKind) -> None:
    assert _action(kind=kind).kind is kind


def test_record_and_announcement_dates_are_optional() -> None:
    action = _action(record_date=None, announcement_date=None, known_at=None)

    assert (action.record_date, action.announcement_date, action.known_at) == (None, None, None)


def test_ex_date_and_record_date_are_stored_as_given_not_derived() -> None:
    """ADR-007 C1: the published ex-date is used; it is never derived from the record date."""
    action = _action(ex_date=date(2019, 6, 13), record_date=date(2019, 6, 14))

    assert (action.ex_date, action.record_date) == (date(2019, 6, 13), date(2019, 6, 14))


def test_unresolved_knowledge_time_is_explicit_none() -> None:
    """Without an announcement date, knowledge time is ADR-007 U1-U3 policy, not inferred here."""
    assert _action(announcement_date=None, known_at=None).known_at is None


@pytest.mark.parametrize(
    "as_of",
    [
        datetime(1990, 1, 1, tzinfo=IST),
        datetime(2024, 3, 15, 18, 0, tzinfo=IST),
        datetime.max.replace(tzinfo=UTC),
    ],
    ids=["long-before", "on-ex-date", "far-future"],
)
def test_unresolved_action_is_never_treated_as_known(as_of: datetime) -> None:
    """Invariant (ADR-018 §2 clarification): known_at=None is visible at no as_of. The type checker
    refuses these calls; if it is bypassed, they fail closed instead of returning the action."""
    unresolved = _action(announcement_date=None, known_at=None)
    untyped: Any = [unresolved]

    with pytest.raises(TypeError, match="must be a datetime"):
        known_by(untyped, as_of)
    with pytest.raises(TypeError, match="must be a datetime"):
        effective_on(untyped, EX_DATE, as_of)


def test_known_action_with_a_later_ex_date_is_visible_before_its_ex_date() -> None:
    """Visibility is by knowledge time, never by ex-date (ADR-019 §2). `known_at` may be None, so
    the type checker refuses `known_by`/`effective_on` on CorporateAction: callers must decide
    explicitly what an unresolved knowledge time means."""
    action = _action()
    as_of = datetime(2024, 3, 5, 18, 0, tzinfo=IST)

    assert action.known_at is not None
    assert is_known(action.known_at, as_of)
    assert action.effective_date > as_of.date()
    assert not is_known(action.known_at, datetime(2024, 3, 1, 17, 59, tzinfo=IST))


def test_knowledge_time_cannot_precede_the_announcement_date() -> None:
    with pytest.raises(ValueError, match="known before its announcement date"):
        _action(known_at=datetime(2024, 2, 29, 23, 59, tzinfo=IST))


def test_knowledge_time_at_the_start_of_the_announcement_date_is_valid() -> None:
    start = datetime(2024, 3, 1, 0, 0, tzinfo=IST)

    assert _action(known_at=start).known_at == start


def test_announcement_boundary_is_in_ist() -> None:
    first_ist_instant = datetime(2024, 2, 29, 18, 30, tzinfo=UTC)  # 00:00 IST on 1 Mar

    assert _action(known_at=first_ist_instant).known_at == first_ist_instant
    with pytest.raises(ValueError, match="known before"):
        _action(known_at=datetime(2024, 2, 29, 18, 29, tzinfo=UTC))  # 23:59 IST on 29 Feb


def test_announcement_date_without_a_knowledge_time_is_rejected() -> None:
    """A date-only announcement is known at the end of that date (ADR-018 §1); it is never
    silently left unresolved, which would hide a known action."""
    with pytest.raises(ValueError, match="announcement date must carry its known_at"):
        _action(known_at=None)


def test_naive_knowledge_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _action(known_at=datetime(2024, 3, 1, 18, 0))


@pytest.mark.parametrize("bad", [date(2024, 3, 1), "2024-03-01T18:00+05:30"])
def test_knowledge_time_must_be_a_datetime(bad: object) -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        _action(known_at=bad)


@given(st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)), st.integers(-3, 3))
def test_knowledge_is_valid_exactly_from_the_announcement_date(announced: date, days: int) -> None:
    known_at = end_of_date(announced + timedelta(days=days))

    if days < 0:
        with pytest.raises(ValueError, match="known before"):
            _action(announcement_date=announced, known_at=known_at)
    else:
        assert _action(announcement_date=announced, known_at=known_at).known_at == known_at


@pytest.mark.parametrize("field", ["ex_date", "record_date", "announcement_date"])
def test_dates_must_be_dates_not_datetimes(field: str) -> None:
    with pytest.raises(TypeError, match=f"{field} must be a date"):
        _action(**{field: datetime(2024, 3, 1, 9, 0, tzinfo=IST)})


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("instrument_id", Symbol("INS-0001"), "InstrumentId"),
        ("kind", "split", "CorporateActionKind"),
        ("source", "synthetic", "SourceRef"),
        ("confidence", "high", "ParseConfidence"),
        ("ex_date", "2024-03-15", "date"),
    ],
)
def test_fields_must_have_their_domain_types(field: str, value: object, expected: str) -> None:
    with pytest.raises(TypeError, match=rf"{field} must be an? {expected}"):
        _action(**{field: value})


def test_ex_date_is_required() -> None:
    with pytest.raises(TypeError, match="ex_date must be a date"):
        _action(ex_date=None)


def test_value_semantics_and_immutability() -> None:
    assert _action() == _action()
    assert hash(_action()) == hash(_action())
    assert _action() != _action(kind=CorporateActionKind.BONUS)
    field = "ex_date"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(_action(), field, date(2024, 3, 16))


def test_representation_is_deterministic() -> None:
    assert repr(_action()) == repr(_action())
    assert "kind=<CorporateActionKind.SPLIT: 'split'>" in repr(_action())
