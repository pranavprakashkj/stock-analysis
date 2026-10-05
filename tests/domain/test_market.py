"""Task 1.4: `Bar`, an unadjusted end-of-day bar keyed by InstrumentId (ADR-001, ADR-019 §3)."""

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading.domain.availability import Series
from trading.domain.identity import InstrumentId, Symbol
from trading.domain.market import Bar
from trading.domain.timing import IST

INSTRUMENT = InstrumentId("INS-0001")
DAY = date(2022, 12, 30)
PUBLISHED = datetime(2022, 12, 30, 18, 0, tzinfo=IST)
PRICE_FIELDS = ("open", "high", "low", "close")


def _bar(**overrides: Any) -> Bar:
    fields: dict[str, Any] = {
        "instrument_id": INSTRUMENT,
        "series": Series("EQ"),
        "observation_date": DAY,
        "open": Decimal("100.00"),
        "high": Decimal("105.50"),
        "low": Decimal("99.05"),
        "close": Decimal("101.50"),
        "volume": 1200,
        "traded_value": Decimal("121800.00"),
        "known_at": PUBLISHED,
    }
    fields.update(overrides)
    return Bar(**fields)


# --- valid bars -------------------------------------------------------------------------------


def test_valid_bar_keeps_every_field_exactly() -> None:
    bar = _bar()

    assert bar.instrument_id == INSTRUMENT
    assert bar.series == Series("EQ")
    assert bar.observation_date == DAY
    assert (bar.open, bar.high, bar.low, bar.close) == (
        Decimal("100.00"),
        Decimal("105.50"),
        Decimal("99.05"),
        Decimal("101.50"),
    )
    assert bar.volume == 1200
    assert bar.traded_value == Decimal("121800.00")
    assert bar.known_at == PUBLISHED


@pytest.mark.parametrize("series", ["EQ", "BE", "BZ"])
def test_bars_of_every_series_are_valid(series: str) -> None:
    """Series is data about the bar, never a filter at this level (ADR-019 §3)."""
    assert _bar(series=Series(series)).series == Series(series)


def test_flat_bar_with_all_prices_equal_is_valid() -> None:
    price = Decimal("50.00")

    assert _bar(open=price, high=price, low=price, close=price).high == price


@pytest.mark.parametrize(
    ("open_", "close"),
    [("105.50", "99.05"), ("99.05", "105.50")],
    ids=["open-at-high-close-at-low", "open-at-low-close-at-high"],
)
def test_open_and_close_may_sit_on_the_extremes(open_: str, close: str) -> None:
    assert _bar(open=Decimal(open_), close=Decimal(close)).low == Decimal("99.05")


def test_zero_volume_and_zero_traded_value_are_valid() -> None:
    assert _bar(volume=0, traded_value=Decimal("0")).volume == 0


def test_smallest_positive_price_is_valid() -> None:
    tiny = Decimal("0.01")

    assert _bar(open=tiny, high=tiny, low=tiny, close=tiny).close == tiny


def test_prices_are_not_rounded() -> None:
    assert _bar(close=Decimal("101.123456789")).close == Decimal("101.123456789")


def test_known_at_on_the_observation_date_itself_is_valid() -> None:
    first_instant = datetime(2022, 12, 30, 0, 0, tzinfo=IST)

    assert _bar(known_at=first_instant).known_at == first_instant


def test_known_at_may_be_in_any_timezone() -> None:
    same_instant = PUBLISHED.astimezone(UTC)

    assert _bar(known_at=same_instant) == _bar()


# --- OHLC invariants --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"high": Decimal("100.99")},  # below close 101.50
        {"high": Decimal("99.99")},  # below open 100.00 (and close)
        {"low": Decimal("100.01")},  # above open 100.00
        {"low": Decimal("101.51")},  # above close (and open)
        {"high": Decimal("99.00"), "low": Decimal("99.05")},  # high below low
    ],
    ids=["high<close", "high<open", "low>open", "low>close", "high<low"],
)
def test_inconsistent_ohlc_is_rejected(overrides: dict[str, Decimal]) -> None:
    with pytest.raises(ValueError, match=r"^(high|low) "):
        _bar(**overrides)


@pytest.mark.parametrize("field", PRICE_FIELDS)
@pytest.mark.parametrize("value", ["0", "-0.00", "-1.00"])
def test_non_positive_prices_are_rejected(field: str, value: str) -> None:
    prices = dict.fromkeys(PRICE_FIELDS, Decimal("1")) | {field: Decimal(value)}

    with pytest.raises(ValueError, match=f"{field} must be > 0"):
        _bar(**prices)


@pytest.mark.parametrize("field", [*PRICE_FIELDS, "traded_value"])
@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_non_finite_decimals_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=f"{field} must be finite"):
        _bar(**{field: Decimal(value)})


@pytest.mark.parametrize("field", [*PRICE_FIELDS, "traded_value"])
@pytest.mark.parametrize("value", [101.5, 101, "101.50", True], ids=["float", "int", "str", "bool"])
def test_prices_and_traded_value_must_be_decimals(field: str, value: object) -> None:
    """No implicit conversion: a float price would already carry binary rounding error."""
    with pytest.raises(TypeError, match=f"{field} must be a Decimal"):
        _bar(**{field: value})


def test_negative_volume_is_rejected() -> None:
    with pytest.raises(ValueError, match="volume must be >= 0"):
        _bar(volume=-1)


@pytest.mark.parametrize("value", [1200.0, Decimal("1200"), "1200", True], ids=repr)
def test_volume_must_be_an_int(value: object) -> None:
    with pytest.raises(TypeError, match="volume must be an int"):
        _bar(volume=value)


@pytest.mark.parametrize("value", ["-0.01", "-0", "-0.00"])
def test_negative_or_negative_zero_traded_value_is_rejected(value: str) -> None:
    """-0 equals 0 but prints differently, which would make representations non-deterministic."""
    with pytest.raises(ValueError, match="traded_value must be >= 0"):
        _bar(traded_value=Decimal(value))


class _SneakyDecimal(Decimal):
    """A Decimal subclass whose comparisons always say "fine"."""

    def __le__(self, other: object) -> bool:
        return False

    def __lt__(self, other: object) -> bool:
        return False

    def __gt__(self, other: object) -> bool:
        return False


class _Day(date):
    pass


def test_subclasses_cannot_bypass_the_price_invariants() -> None:
    negative = _SneakyDecimal("-5")

    with pytest.raises(TypeError, match="open must be a Decimal, not _SneakyDecimal"):
        _bar(open=negative, high=negative, low=negative, close=negative)


def test_int_subclasses_are_not_volumes() -> None:
    with pytest.raises(TypeError, match="volume must be an int, not HTTPStatus"):
        _bar(volume=HTTPStatus.OK)


def test_date_subclasses_are_not_observation_dates() -> None:
    with pytest.raises(TypeError, match="observation_date must be a date, not _Day"):
        _bar(observation_date=_Day(2022, 12, 30))


# --- identity, dates and knowledge time -------------------------------------------------------


def test_bar_must_be_keyed_by_instrument_id_not_symbol() -> None:
    with pytest.raises(TypeError, match="instrument_id must be an InstrumentId"):
        _bar(instrument_id=Symbol("INS-0001"))


def test_series_must_be_a_series() -> None:
    with pytest.raises(TypeError, match="series must be a Series"):
        _bar(series="EQ")


def test_observation_date_must_be_a_date_not_a_datetime() -> None:
    with pytest.raises(TypeError, match="observation_date must be a date"):
        _bar(observation_date=datetime(2022, 12, 30, 15, 30, tzinfo=IST))


def test_naive_knowledge_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _bar(known_at=datetime(2022, 12, 30, 18, 0))


def test_bar_cannot_be_known_before_its_observation_date() -> None:
    last_instant_before = datetime(2022, 12, 29, 23, 59, 59, 999999, tzinfo=IST)

    with pytest.raises(ValueError, match="known before its observation date"):
        _bar(known_at=last_instant_before)


def test_the_observation_date_boundary_is_in_ist() -> None:
    """00:30 IST on the 30th is 19:00 UTC on the 29th: still the 30th in IST, so valid."""
    assert _bar(known_at=datetime(2022, 12, 29, 19, 0, tzinfo=UTC)).observation_date == DAY
    with pytest.raises(ValueError, match="known before"):
        _bar(known_at=datetime(2022, 12, 29, 18, 29, tzinfo=UTC))


# --- value semantics --------------------------------------------------------------------------


def test_equal_bars_are_equal_and_hash_equal() -> None:
    assert _bar() == _bar()
    assert hash(_bar()) == hash(_bar())
    assert _bar() != _bar(series=Series("BE"))


def test_equality_is_by_decimal_value_not_by_trailing_zeros() -> None:
    assert _bar(close=Decimal("101.5")) == _bar(close=Decimal("101.50"))


def test_bar_fields_cannot_be_reassigned() -> None:
    name = "close"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(_bar(), name, Decimal("1"))


def test_bar_cannot_gain_attributes() -> None:
    """Frozen + slots: adding an attribute raises TypeError on Python 3.12."""
    name = "adjusted_close"
    with pytest.raises((AttributeError, TypeError)):
        setattr(_bar(), name, Decimal("1"))
    assert not hasattr(_bar(), name)


def test_representation_is_deterministic() -> None:
    assert repr(_bar()) == repr(_bar())
    assert repr(_bar()).startswith(
        "Bar(instrument_id=InstrumentId(value='INS-0001'), series=Series(code='EQ'), "
        "observation_date=datetime.date(2022, 12, 30), open=Decimal('100.00'), "
    )


# --- properties -------------------------------------------------------------------------------

_PRICES = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100000"), places=2)


@given(st.lists(_PRICES, min_size=4, max_size=4), st.booleans())
def test_any_consistent_ohlc_is_accepted(prices: list[Decimal], open_is_lower: bool) -> None:
    low, a, b, high = sorted(prices)
    open_, close = (a, b) if open_is_lower else (b, a)

    bar = _bar(open=open_, high=high, low=low, close=close)

    assert (bar.open, bar.high, bar.low, bar.close) == (open_, high, low, close)


@given(st.lists(_PRICES, min_size=4, max_size=4, unique=True), st.sampled_from(["high", "low"]))
def test_any_bar_with_high_below_or_low_above_the_body_is_rejected(
    prices: list[Decimal], broken: str
) -> None:
    low, open_, close, high = sorted(prices)
    if broken == "high":
        overrides = {"open": open_, "close": high, "high": close, "low": low}  # high < close
    else:
        overrides = {"open": low, "close": close, "high": high, "low": open_}  # low > open

    with pytest.raises(ValueError, match=broken):
        _bar(**overrides)
