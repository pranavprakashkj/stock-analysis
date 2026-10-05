"""Task 1.4: index-membership changes (ADR-002) and the LiquidityThresholds shape (ADR-012 §2a)."""

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading.domain.availability import SourceRef
from trading.domain.identity import InstrumentId, Symbol
from trading.domain.timing import IST, effective_on, known_by
from trading.domain.universe import (
    IndexMembershipChange,
    IndexName,
    LiquidityThresholds,
    MembershipChange,
)

INSTRUMENT = InstrumentId("INS-0001")
ANNOUNCED = datetime(2024, 2, 23, 20, 0, tzinfo=IST)
EFFECTIVE = date(2024, 3, 28)


def _change(**overrides: Any) -> IndexMembershipChange:
    fields: dict[str, Any] = {
        "index": IndexName.NIFTY_100,
        "instrument_id": INSTRUMENT,
        "change": MembershipChange.ADDED,
        "effective_date": EFFECTIVE,
        "known_at": ANNOUNCED,
        "source": SourceRef("synthetic:reconstitution-2024-02.pdf"),
    }
    fields.update(overrides)
    return IndexMembershipChange(**fields)


# --- IndexMembershipChange --------------------------------------------------------------------


def test_change_kinds_are_added_and_removed() -> None:
    assert {c.value for c in MembershipChange} == {"added", "removed"}


def test_valid_change_keeps_its_fields() -> None:
    change = _change(change=MembershipChange.REMOVED)

    assert change.index is IndexName.NIFTY_100
    assert change.instrument_id == INSTRUMENT
    assert change.change is MembershipChange.REMOVED
    assert change.effective_date == EFFECTIVE
    assert change.known_at == ANNOUNCED


def test_announced_change_is_known_before_it_takes_effect() -> None:
    """ADR-002 §1: membership switches on the effective date, not the announcement date."""
    change = _change()
    between = datetime(2024, 3, 1, 18, 0, tzinfo=IST)

    assert known_by([change], between) == [change]
    assert effective_on([change], date(2024, 3, 1), between) == []
    assert effective_on([change], EFFECTIVE, between) == [change]
    assert known_by([change], datetime(2024, 2, 23, 19, 59, tzinfo=IST)) == []


@pytest.mark.parametrize("bad", ["NIFTY 100", "Nifty 100", 100])
def test_index_must_be_an_index_name_member_not_free_text(bad: object) -> None:
    """Free text would let spelling variants ('Nifty 100') split one index into two."""
    with pytest.raises(TypeError, match="index must be an IndexName"):
        _change(index=bad)


def test_index_names_are_closed() -> None:
    assert {i.value for i in IndexName} == {"NIFTY 100"}


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("instrument_id", Symbol("INS-0001"), "InstrumentId"),
        ("change", "added", "MembershipChange"),
        ("source", "synthetic", "SourceRef"),
        ("effective_date", datetime(2024, 3, 28, 9, 15, tzinfo=IST), "date"),
    ],
)
def test_fields_must_have_their_domain_types(field: str, value: object, expected: str) -> None:
    with pytest.raises(TypeError, match=rf"{field} must be an? {expected}"):
        _change(**{field: value})


def test_naive_knowledge_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _change(known_at=datetime(2024, 2, 23, 20, 0))


@pytest.mark.parametrize("bad", [date(2024, 2, 23), "2024-02-23T20:00+05:30", None])
def test_knowledge_time_must_be_a_datetime(bad: object) -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        _change(known_at=bad)


def test_change_value_semantics_and_immutability() -> None:
    assert _change() == _change()
    assert hash(_change()) == hash(_change())
    assert _change() != _change(change=MembershipChange.REMOVED)
    field = "effective_date"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(_change(), field, date(2024, 4, 1))


# --- LiquidityThresholds ----------------------------------------------------------------------

LIQUIDITY_FIELDS = (
    "min_price",
    "min_median_traded_value",
    "max_participation",
    "order_liquidity_fraction",
)
FRACTIONS = ("max_participation", "order_liquidity_fraction")


def _thresholds(**overrides: Any) -> LiquidityThresholds:
    # Arbitrary test values: real values come only from the locked config (ADR-012 §2a, ADR-017).
    fields: dict[str, Any] = {
        "min_price": Decimal("7"),
        "min_median_traded_value": Decimal("3"),
        "max_participation": Decimal("0.3"),
        "order_liquidity_fraction": Decimal("0.2"),
    }
    fields.update(overrides)
    return LiquidityThresholds(**fields)


def test_liquidity_thresholds_have_exactly_the_adr_012_fields() -> None:
    assert tuple(f.name for f in dataclasses.fields(LiquidityThresholds)) == LIQUIDITY_FIELDS


def test_liquidity_thresholds_have_no_defaults() -> None:
    for f in dataclasses.fields(LiquidityThresholds):
        assert f.default is dataclasses.MISSING, f.name
        assert f.default_factory is dataclasses.MISSING, f.name


def test_liquidity_thresholds_cannot_be_built_without_values() -> None:
    untyped: Any = LiquidityThresholds  # deliberately calls it with missing arguments
    with pytest.raises(TypeError, match="missing 4 required positional arguments"):
        untyped()


@pytest.mark.parametrize("field", LIQUIDITY_FIELDS)
@pytest.mark.parametrize("value", ["0", "-0.01"])
def test_thresholds_must_be_positive(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=f"{field} must be > 0"):
        _thresholds(**{field: Decimal(value)})


@pytest.mark.parametrize("field", FRACTIONS)
def test_fractions_may_not_exceed_one(field: str) -> None:
    assert getattr(_thresholds(**{field: Decimal("1")}), field) == Decimal("1")
    with pytest.raises(ValueError, match=f"{field} must be <= 1"):
        _thresholds(**{field: Decimal("1.0001")})


def test_non_fraction_thresholds_are_not_capped_at_one() -> None:
    assert _thresholds(min_price=Decimal("2500")).min_price == Decimal("2500")


@pytest.mark.parametrize("field", LIQUIDITY_FIELDS)
@pytest.mark.parametrize("value", ["NaN", "Infinity"])
def test_thresholds_must_be_finite(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=f"{field} must be finite"):
        _thresholds(**{field: Decimal(value)})


@pytest.mark.parametrize("field", LIQUIDITY_FIELDS)
@pytest.mark.parametrize("value", [0.5, 1, "0.5"], ids=["float", "int", "str"])
def test_thresholds_must_be_decimals(field: str, value: object) -> None:
    with pytest.raises(TypeError, match=f"{field} must be a Decimal"):
        _thresholds(**{field: value})


_POSITIVE = st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("1e12"), places=4)
_FRACTION = st.decimals(min_value=Decimal("0.0001"), max_value=Decimal("1"), places=4)


@given(_POSITIVE, _POSITIVE, _FRACTION, _FRACTION)
def test_any_values_in_range_are_accepted(
    price: Decimal, value: Decimal, participation: Decimal, fraction: Decimal
) -> None:
    thresholds = LiquidityThresholds(price, value, participation, fraction)

    assert (thresholds.max_participation, thresholds.order_liquidity_fraction) == (
        participation,
        fraction,
    )


@given(
    st.sampled_from(FRACTIONS),
    st.decimals(min_value=Decimal("1.0001"), max_value=Decimal("1e6"), places=4),
)
def test_any_fraction_above_one_is_rejected(field: str, value: Decimal) -> None:
    with pytest.raises(ValueError, match=f"{field} must be <= 1"):
        _thresholds(**{field: value})


def test_thresholds_are_immutable_values() -> None:
    assert _thresholds() == _thresholds()
    field = "min_price"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(_thresholds(), field, Decimal("1"))
