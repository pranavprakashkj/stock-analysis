"""ADR-019 §1: InstrumentId is canonical; symbols are dated, display-only references.

The end of a symbol assignment is its own record with its own knowledge time (ADR-018 §2), so an
as-of view never shows an end that was not yet known.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading.domain.identity import (
    IdentityError,
    IdentityMap,
    IdentityMapEnd,
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
TICK = timedelta(microseconds=1)


def _entry(
    instrument: InstrumentId, symbol: str, valid_from: date, known_at: datetime = LISTED
) -> IdentityMapEntry:
    return IdentityMapEntry(instrument, Symbol(symbol), valid_from, known_at)


def _end(
    instrument: InstrumentId,
    symbol: str,
    valid_from: date,
    valid_to: date,
    known_at: datetime = LISTED,
) -> IdentityMapEnd:
    return IdentityMapEnd(instrument, Symbol(symbol), valid_from, valid_to, known_at)


RENAMED = IdentityMap(
    (
        _entry(INFRATEL, "INFRATEL", date(2012, 12, 28)),
        _entry(INFRATEL, "INDUSTOWER", date(2020, 12, 10), RENAME_ANNOUNCED),
    ),
    (_end(INFRATEL, "INFRATEL", date(2012, 12, 28), date(2020, 12, 9), RENAME_ANNOUNCED),),
)


# --- rename and identity semantics (unchanged) ------------------------------------------------


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
        (_entry(INFRATEL, "ABC", date(2011, 1, 3)), _entry(OTHER, "ABC", date(2018, 1, 1))),
        (_end(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 6, 30)),),
    )

    assert identity.resolve(Symbol("ABC"), date(2012, 1, 2)) == INFRATEL
    assert identity.resolve(Symbol("ABC"), date(2019, 1, 2)) == OTHER


def test_overlapping_assignment_of_one_symbol_is_rejected() -> None:
    with pytest.raises(IdentityError, match="overlap"):
        IdentityMap(
            (_entry(INFRATEL, "ABC", date(2011, 1, 3)), _entry(OTHER, "ABC", date(2015, 6, 30))),
            (_end(INFRATEL, "ABC", date(2011, 1, 3), date(2016, 1, 1)),),
        )


def test_overlapping_symbols_for_one_instrument_are_rejected() -> None:
    with pytest.raises(IdentityError, match="overlap"):
        IdentityMap(
            (_entry(INFRATEL, "OLD", date(2011, 1, 3)), _entry(INFRATEL, "NEW", date(2020, 1, 1)))
        )


def test_resolving_outside_every_entry_is_an_explicit_error() -> None:
    identity = IdentityMap(
        (_entry(INFRATEL, "ABC", date(2011, 1, 3)),),
        (_end(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 6, 30)),),
    )

    with pytest.raises(IdentityError, match="no instrument"):
        identity.resolve(Symbol("ABC"), date(2016, 1, 4))
    with pytest.raises(IdentityError, match="no instrument"):
        identity.resolve(Symbol("ABC"), date(2011, 1, 2))


def test_entry_requires_an_aware_knowledge_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _entry(INFRATEL, "ABC", date(2015, 1, 1), datetime(2014, 12, 1, 18, 0))


# --- the end of an assignment carries its own knowledge time ----------------------------------


def test_assignment_is_visible_open_ended_before_its_end_is_known() -> None:
    """1. Before the end is known, the assignment is visible and still open."""
    before = RENAMED.as_known_at(RENAME_ANNOUNCED - TICK)

    assert before.resolve(Symbol("INFRATEL"), date(2019, 1, 2)) == INFRATEL
    assert before.resolve(Symbol("INFRATEL"), date(2021, 1, 4)) == INFRATEL


def test_end_is_not_visible_before_its_knowledge_time() -> None:
    """2. One instant before the end is known, nothing reveals the coming end date."""
    before = RENAMED.as_known_at(RENAME_ANNOUNCED - TICK)

    assert before.symbol_on(INFRATEL, date(2020, 12, 10)) == Symbol("INFRATEL")
    assert before.symbol_on(INFRATEL, date(2030, 1, 1)) == Symbol("INFRATEL")
    assert before.ends() == ()


def test_end_becomes_visible_exactly_at_its_knowledge_time() -> None:
    """3. From the end's knowledge time, the assignment stops at valid_to."""
    at = RENAMED.as_known_at(RENAME_ANNOUNCED)

    assert at.resolve(Symbol("INFRATEL"), date(2020, 12, 9)) == INFRATEL
    with pytest.raises(IdentityError, match="no instrument"):
        at.resolve(Symbol("INFRATEL"), date(2020, 12, 10))
    assert at.ends() == RENAMED.ends()


def test_an_end_known_later_than_its_successor_cannot_be_hidden_by_it() -> None:
    """A delisting known after the fact: before then the symbol is still open; after, closed."""
    delisting_known = datetime(2016, 1, 5, 18, 0, tzinfo=IST)
    identity = IdentityMap(
        (_entry(INFRATEL, "ABC", date(2011, 1, 3)),),
        (_end(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 12, 31), delisting_known),),
    )

    assert (
        identity.as_known_at(delisting_known - TICK).resolve(Symbol("ABC"), date(2016, 1, 4))
        == INFRATEL
    )
    with pytest.raises(IdentityError, match="no instrument"):
        identity.as_known_at(delisting_known).resolve(Symbol("ABC"), date(2016, 1, 4))


_DAYS = st.integers(0, 40)


@given(_DAYS, _DAYS, st.integers(-3, 3), st.integers(-60, 60))
def test_no_as_of_view_reveals_an_unknown_end(
    start: int, length: int, end_known_offset: int, as_of_offset: int
) -> None:
    """4. Against an oracle that uses only records known by as_of, for every day and as_of."""
    base = date(2020, 1, 1)
    valid_from = base + timedelta(days=start)
    valid_to = valid_from + timedelta(days=length)
    entry_known = datetime(2019, 12, 1, 18, 0, tzinfo=IST)
    end_known = datetime.combine(valid_to, datetime.min.time(), IST) + timedelta(
        days=end_known_offset
    )
    end_known = max(end_known, entry_known)
    as_of = end_known + timedelta(hours=as_of_offset)
    identity = IdentityMap(
        (_entry(INFRATEL, "ABC", valid_from, entry_known),),
        (_end(INFRATEL, "ABC", valid_from, valid_to, end_known),),
    )

    view = identity.as_known_at(as_of)
    end_visible = end_known <= as_of
    for offset in range(-2, 85):
        day = base + timedelta(days=offset)
        expected = valid_from <= day and (not end_visible or day <= valid_to)
        if expected:
            assert view.resolve(Symbol("ABC"), day) == INFRATEL
        else:
            with pytest.raises(IdentityError):
                view.resolve(Symbol("ABC"), day)


# --- invalid ends -----------------------------------------------------------------------------


def test_end_without_its_assignment_is_rejected() -> None:
    with pytest.raises(IdentityError, match="ends no assignment"):
        IdentityMap(
            (_entry(INFRATEL, "ABC", date(2011, 1, 3)),),
            (_end(INFRATEL, "ABC", date(2011, 1, 4), date(2015, 6, 30)),),
        )


def test_assignment_ended_twice_is_rejected() -> None:
    with pytest.raises(IdentityError, match="ended more than once"):
        IdentityMap(
            (_entry(INFRATEL, "ABC", date(2011, 1, 3)),),
            (
                _end(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 6, 30)),
                _end(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 7, 31)),
            ),
        )


def test_end_known_before_its_assignment_is_rejected() -> None:
    with pytest.raises(IdentityError, match="known before the assignment it ends"):
        IdentityMap(
            (_entry(INFRATEL, "ABC", date(2011, 1, 3), RENAME_ANNOUNCED),),
            (_end(INFRATEL, "ABC", date(2011, 1, 3), date(2015, 6, 30), LISTED),),
        )


def test_end_before_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="valid_to"):
        _end(INFRATEL, "ABC", date(2015, 1, 1), date(2014, 12, 31))


def test_end_requires_an_aware_knowledge_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _end(INFRATEL, "ABC", date(2015, 1, 1), date(2015, 6, 1), datetime(2015, 6, 1, 18, 0))


def test_successor_known_before_the_old_end_would_overlap_in_that_view() -> None:
    """If the new symbol were public before the old one's end, the as-of view in between would map
    one instrument to two symbols. That is rejected rather than resolved by guessing."""
    with pytest.raises(IdentityError, match="overlapping identity entries as known at"):
        IdentityMap(
            (
                _entry(INFRATEL, "INFRATEL", date(2012, 12, 28)),
                _entry(INFRATEL, "INDUSTOWER", date(2020, 12, 10), RENAME_ANNOUNCED),
            ),
            (
                _end(
                    INFRATEL,
                    "INFRATEL",
                    date(2012, 12, 28),
                    date(2020, 12, 9),
                    RENAME_ANNOUNCED + timedelta(days=1),
                ),
            ),
        )


def test_every_as_of_view_of_a_valid_map_is_valid() -> None:
    for as_of in (LISTED - TICK, LISTED, RENAME_ANNOUNCED - TICK, RENAME_ANNOUNCED):
        RENAMED.as_known_at(as_of)  # constructs (and validates) the view


@pytest.mark.parametrize(
    "bad",
    ["", " INS-1", "INS 1", "INS-1\n", "INS\t1", "INS\u00a01", "INS\x001", "INS\x7f1"],
    ids=["empty", "leading-space", "space", "newline", "tab", "nbsp", "nul", "del"],
)
def test_instrument_id_rejects_blank_whitespace_or_control_characters(bad: str) -> None:
    with pytest.raises(ValueError, match="InstrumentId"):
        InstrumentId(bad)


@pytest.mark.parametrize(
    "bad",
    ["", "M M", " TCS", "TCS\n", "TC\x00S"],
    ids=["empty", "space", "leading-space", "newline", "nul"],
)
def test_symbol_rejects_blank_whitespace_or_control_characters(bad: str) -> None:
    with pytest.raises(ValueError, match="Symbol"):
        Symbol(bad)


@pytest.mark.parametrize("cls", [InstrumentId, Symbol, Isin])
@pytest.mark.parametrize("bad", [1, 1.0, b"INE121J01017", None, ["INS-1"]])
def test_identifiers_reject_non_strings(cls: Callable[[str], object], bad: object) -> None:
    with pytest.raises(TypeError, match="must be a str"):
        cls(cast("str", bad))  # deliberately wrong type


def test_symbol_is_not_normalised() -> None:
    """No exchange-specific normalisation is specified, so values are kept exactly."""
    assert Symbol("M&M").value == "M&M"
    assert Symbol("tcs") != Symbol("TCS")


def test_identifiers_have_value_equality_and_hash() -> None:
    assert InstrumentId("INS-1") == InstrumentId("INS-1")
    assert hash(InstrumentId("INS-1")) == hash(InstrumentId("INS-1"))
    assert InstrumentId("INS-1") != InstrumentId("INS-2")
    assert Symbol("TCS") == Symbol("TCS")
    assert Isin("INE121J01017") == Isin("INE121J01017")


def test_an_instrument_id_never_equals_a_symbol_with_the_same_text() -> None:
    """Identity is never symbol-based: the same text in the two roles is two different values.
    mypy (strict equality) already rejects this comparison; this checks the runtime too."""
    assert cast("object", InstrumentId("TCS")) != Symbol("TCS")
    assert len({InstrumentId("TCS"), Symbol("TCS")}) == 2


def test_representation_is_deterministic() -> None:
    assert repr(InstrumentId("INS-1")) == "InstrumentId(value='INS-1')"
    assert repr(Symbol("TCS")) == "Symbol(value='TCS')"
    assert repr(Isin("INE121J01017")) == "Isin(value='INE121J01017')"


@pytest.mark.parametrize(
    "value", [InstrumentId("INS-1"), Symbol("TCS"), Isin("INE121J01017")], ids=repr
)
def test_identifiers_are_immutable(value: object) -> None:
    field = "value"
    with pytest.raises(AttributeError):
        setattr(value, field, "OTHER")


@given(st.text(min_size=1).filter(lambda s: s.isprintable() and not any(c.isspace() for c in s)))
def test_any_printable_token_is_a_valid_instrument_id(text: str) -> None:
    assert InstrumentId(text).value == text


@given(st.text(), st.sampled_from([" ", "\t", "\n", "\u2003"]), st.text())
def test_any_text_containing_whitespace_is_rejected(prefix: str, space: str, suffix: str) -> None:
    with pytest.raises(ValueError, match="InstrumentId"):
        InstrumentId(prefix + space + suffix)


def test_isin_accepts_iso_6166_shape() -> None:
    assert Isin("INE121J01017").value == "INE121J01017"


def test_isin_check_digit_is_not_verified() -> None:
    """ADR-019 records ISINs as external identifiers; only the shape is checked."""
    assert Isin("INE121J01010").value == "INE121J01010"  # valid shape, wrong check digit


@pytest.mark.parametrize(
    "bad",
    ["INE121J0101", "ine121j01017", "1NE121J01017", "INE121J0101X", "INE121J01017 ", ""],
)
def test_isin_rejects_wrong_shape(bad: str) -> None:
    with pytest.raises(ValueError, match="ISIN"):
        Isin(bad)


def test_ends_are_listed_in_content_order_not_input_order() -> None:
    entries = (_entry(INFRATEL, "ABC", date(2011, 1, 3)), _entry(OTHER, "XYZ", date(2011, 1, 3)))
    ends = (
        _end(OTHER, "XYZ", date(2011, 1, 3), date(2012, 1, 1)),
        _end(INFRATEL, "ABC", date(2011, 1, 3), date(2013, 1, 1)),
    )

    assert IdentityMap(entries, ends).ends() == IdentityMap(entries, ends[::-1]).ends()
    assert [e.instrument_id for e in IdentityMap(entries, ends).ends()] == [INFRATEL, OTHER]
