"""ADR-019 §1: InstrumentId is canonical; symbols are dated, display-only references."""

from datetime import date, datetime

import pytest

from trading.domain.identity import (
    IdentityError,
    IdentityMap,
    IdentityMapEntry,
    InstrumentId,
    Isin,
    Symbol,
)
from trading.domain.timing import IST

INFRATEL = InstrumentId("INS-0001")
OTHER = InstrumentId("INS-0002")
LISTED = datetime(2012, 12, 20, 18, 0, tzinfo=IST)
RENAME_ANNOUNCED = datetime(2020, 12, 1, 18, 0, tzinfo=IST)


def _entry(
    instrument: InstrumentId,
    symbol: str,
    valid_from: date,
    valid_to: date | None,
    known_at: datetime = LISTED,
) -> IdentityMapEntry:
    return IdentityMapEntry(instrument, Symbol(symbol), valid_from, valid_to, known_at)


RENAMED = IdentityMap(
    (
        _entry(INFRATEL, "INFRATEL", date(2012, 12, 28), date(2020, 12, 9)),
        _entry(INFRATEL, "INDUSTOWER", date(2020, 12, 10), None, RENAME_ANNOUNCED),
    )
)


def test_symbol_change_keeps_the_same_instrument_identity() -> None:
    assert RENAMED.resolve(Symbol("INFRATEL"), date(2019, 1, 2)) == INFRATEL
    assert RENAMED.resolve(Symbol("INDUSTOWER"), date(2021, 1, 4)) == INFRATEL
    assert RENAMED.symbol_on(INFRATEL, date(2019, 1, 2)) == Symbol("INFRATEL")
    assert RENAMED.symbol_on(INFRATEL, date(2021, 1, 4)) == Symbol("INDUSTOWER")


def test_a_rename_is_invisible_before_it_was_announced() -> None:
    before = RENAMED.as_known_at(datetime(2020, 11, 30, 20, 0, tzinfo=IST))

    with pytest.raises(IdentityError, match="no instrument"):
        before.resolve(Symbol("INDUSTOWER"), date(2021, 1, 4))
    assert before.resolve(Symbol("INFRATEL"), date(2019, 1, 2)) == INFRATEL


def test_a_symbol_may_be_reused_by_a_different_instrument_at_a_different_time() -> None:
    identity = IdentityMap(
        (
            _entry(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 6, 30)),
            _entry(OTHER, "ABC", date(2018, 1, 1), None),
        )
    )

    assert identity.resolve(Symbol("ABC"), date(2012, 1, 2)) == INFRATEL
    assert identity.resolve(Symbol("ABC"), date(2019, 1, 2)) == OTHER


def test_overlapping_assignment_of_one_symbol_is_rejected() -> None:
    with pytest.raises(IdentityError, match="overlap"):
        IdentityMap(
            (
                _entry(INFRATEL, "ABC", date(2011, 1, 3), date(2016, 1, 1)),
                _entry(OTHER, "ABC", date(2015, 6, 30), None),
            )
        )


def test_overlapping_symbols_for_one_instrument_are_rejected() -> None:
    with pytest.raises(IdentityError, match="overlap"):
        IdentityMap(
            (
                _entry(INFRATEL, "OLD", date(2011, 1, 3), None),
                _entry(INFRATEL, "NEW", date(2020, 1, 1), None),
            )
        )


def test_resolving_outside_every_entry_is_an_explicit_error() -> None:
    identity = IdentityMap((_entry(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 6, 30)),))

    with pytest.raises(IdentityError, match="no instrument"):
        identity.resolve(Symbol("ABC"), date(2016, 1, 4))


def test_entry_with_end_before_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="valid_to"):
        _entry(INFRATEL, "ABC", date(2015, 1, 1), date(2014, 1, 1))


def test_entry_requires_an_aware_knowledge_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _entry(INFRATEL, "ABC", date(2015, 1, 1), None, datetime(2014, 12, 1, 18, 0))


@pytest.mark.parametrize("bad", ["", " INS-1", "INS 1"])
def test_instrument_id_rejects_blank_or_whitespace(bad: str) -> None:
    with pytest.raises(ValueError, match="InstrumentId"):
        InstrumentId(bad)


@pytest.mark.parametrize("bad", ["", "M M", " TCS"])
def test_symbol_rejects_blank_or_whitespace(bad: str) -> None:
    with pytest.raises(ValueError, match="Symbol"):
        Symbol(bad)


def test_isin_accepts_iso_6166_shape() -> None:
    assert Isin("INE121J01017").value == "INE121J01017"


@pytest.mark.parametrize("bad", ["INE121J0101", "ine121j01017", "1NE121J01017", "INE121J0101X"])
def test_isin_rejects_wrong_shape(bad: str) -> None:
    with pytest.raises(ValueError, match="ISIN"):
        Isin(bad)
