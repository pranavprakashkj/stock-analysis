"""Task 1.5: session arithmetic over an explicit, versioned session list.

The fixture is synthetic (January 2030), chosen so that no weekday rule could produce it: a closed
Friday, a special Saturday session, and closed days at both ends of the coverage range.
"""

import dataclasses
import os
import subprocess
import sys
from datetime import date, datetime
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from trading.domain.calendar import (
    CalendarError,
    NotASessionError,
    OutsideCalendarError,
    Session,
    SessionKind,
    TradingCalendar,
)
from trading.domain.timing import IST

REGULAR, SPECIAL = SessionKind.REGULAR, SessionKind.SPECIAL


def d(day: int) -> date:
    return date(2030, 1, day)


SESSIONS = (
    Session(d(2), REGULAR),  # Wed: first session (1 Jan, a Tuesday, is closed)
    Session(d(3), REGULAR),  # Thu; Fri 4 Jan is a synthetic weekday closure
    Session(d(5), SPECIAL),  # Sat: special session
    Session(d(7), REGULAR),
    Session(d(8), REGULAR),
    Session(d(9), REGULAR),
    Session(d(10), REGULAR),
    Session(d(11), REGULAR),  # weekend 12-13 Jan closed
    Session(d(14), REGULAR),  # Mon: last session (15 Jan, a Tuesday, is closed)
)
CALENDAR = TradingCalendar("synthetic-2030-01", d(1), d(15), SESSIONS)
BEFORE_COVERAGE = date(2029, 12, 31)
AFTER_COVERAGE = d(16)


def _calendar(**overrides: Any) -> TradingCalendar:
    fields: dict[str, Any] = {
        "version": "synthetic-2030-01",
        "coverage_start": d(1),
        "coverage_end": d(15),
        "sessions": SESSIONS,
    }
    fields.update(overrides)
    return TradingCalendar(**fields)


# --- session membership -----------------------------------------------------------------------


def test_regular_session_is_a_session() -> None:
    assert CALENDAR.is_session(d(2))
    assert CALENDAR.kind_of(d(2)) is REGULAR


def test_special_weekend_session_is_a_session() -> None:
    assert CALENDAR.is_session(d(5))
    assert CALENDAR.kind_of(d(5)) is SPECIAL


def test_a_weekday_is_not_assumed_to_be_a_session() -> None:
    assert d(4).weekday() == 4  # Friday
    assert not CALENDAR.is_session(d(4))


def test_weekend_without_a_session_is_not_a_session() -> None:
    assert not CALENDAR.is_session(d(6))
    assert not CALENDAR.is_session(d(12))


def test_closed_days_at_both_ends_of_coverage_are_known_non_sessions() -> None:
    assert not CALENDAR.is_session(d(1))  # immediately before the first session
    assert not CALENDAR.is_session(d(15))  # immediately after the last session


@pytest.mark.parametrize("outside", [BEFORE_COVERAGE, AFTER_COVERAGE], ids=["before", "after"])
def test_dates_outside_coverage_raise_rather_than_guess(outside: date) -> None:
    with pytest.raises(OutsideCalendarError, match="outside calendar synthetic-2030-01"):
        CALENDAR.is_session(outside)
    with pytest.raises(OutsideCalendarError, match="outside calendar synthetic-2030-01"):
        CALENDAR.kind_of(outside)


@pytest.mark.parametrize("day", [d(4), d(1), d(15)], ids=["closed-friday", "start", "end"])
def test_kind_of_a_covered_non_session_is_not_a_session_error(day: date) -> None:
    with pytest.raises(NotASessionError, match="not a session"):
        CALENDAR.kind_of(day)


def test_not_a_session_and_outside_coverage_are_distinct_errors() -> None:
    """Catching NotASessionError must never also swallow "unknown" (outside coverage)."""
    assert issubclass(NotASessionError, CalendarError)
    assert issubclass(OutsideCalendarError, CalendarError)
    assert not issubclass(OutsideCalendarError, NotASessionError)
    assert not issubclass(NotASessionError, OutsideCalendarError)


# --- ordering ---------------------------------------------------------------------------------


def test_first_and_last_session() -> None:
    assert CALENDAR.first_session == d(2)
    assert CALENDAR.last_session == d(14)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (d(1), d(2)),  # from the closed day before the first session
        (d(2), d(3)),
        (d(3), d(5)),  # skips the closed Friday, lands on the special Saturday
        (d(4), d(5)),  # from a non-session
        (d(5), d(7)),  # skips Sunday
        (d(11), d(14)),  # skips the weekend
    ],
)
def test_next_session_is_the_first_session_strictly_after(day: date, expected: date) -> None:
    assert CALENDAR.next_session(day) == expected


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (d(15), d(14)),  # from the closed day after the last session
        (d(14), d(11)),
        (d(7), d(5)),
        (d(6), d(5)),  # from a non-session
        (d(5), d(3)),
        (d(3), d(2)),
    ],
)
def test_previous_session_is_the_last_session_strictly_before(day: date, expected: date) -> None:
    assert CALENDAR.previous_session(day) == expected


@pytest.mark.parametrize("day", [d(14), d(15)], ids=["last-session", "after-last-session"])
def test_no_next_session_within_coverage_raises(day: date) -> None:
    """The next session may exist beyond the loaded range; it is unknown, not absent."""
    with pytest.raises(OutsideCalendarError, match="no session after"):
        CALENDAR.next_session(day)


@pytest.mark.parametrize("day", [d(2), d(1)], ids=["first-session", "before-first-session"])
def test_no_previous_session_within_coverage_raises(day: date) -> None:
    with pytest.raises(OutsideCalendarError, match="no session before"):
        CALENDAR.previous_session(day)


@pytest.mark.parametrize("outside", [BEFORE_COVERAGE, AFTER_COVERAGE], ids=["before", "after"])
def test_next_and_previous_from_outside_coverage_raise(outside: date) -> None:
    with pytest.raises(OutsideCalendarError, match="outside calendar"):
        CALENDAR.next_session(outside)
    with pytest.raises(OutsideCalendarError, match="outside calendar"):
        CALENDAR.previous_session(outside)


# --- ranges -----------------------------------------------------------------------------------


def test_single_day_range_on_a_session() -> None:
    assert CALENDAR.sessions_between(d(2), d(2)) == (d(2),)


def test_single_day_range_on_a_non_session_is_empty() -> None:
    assert CALENDAR.sessions_between(d(4), d(4)) == ()


def test_multi_day_range_is_inclusive_and_ordered() -> None:
    assert CALENDAR.sessions_between(d(3), d(8)) == (d(3), d(5), d(7), d(8))


def test_range_containing_no_sessions_is_empty() -> None:
    assert CALENDAR.sessions_between(d(12), d(13)) == ()


def test_whole_coverage_range_returns_every_session() -> None:
    assert CALENDAR.sessions_between(d(1), d(15)) == tuple(s.day for s in SESSIONS)


def test_reversed_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="start 2030-01-08 is after end 2030-01-03"):
        CALENDAR.sessions_between(d(8), d(3))


@pytest.mark.parametrize(
    ("start", "end"),
    [(BEFORE_COVERAGE, d(3)), (d(3), AFTER_COVERAGE), (BEFORE_COVERAGE, AFTER_COVERAGE)],
    ids=["start-outside", "end-outside", "both-outside"],
)
def test_range_reaching_outside_coverage_raises(start: date, end: date) -> None:
    with pytest.raises(OutsideCalendarError, match="outside calendar"):
        CALENDAR.sessions_between(start, end)


def test_sessions_property_is_the_ordered_immutable_session_list() -> None:
    assert CALENDAR.sessions == SESSIONS
    assert isinstance(CALENDAR.sessions, tuple)


# --- invalid queries --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [datetime(2030, 1, 2, 9, 15, tzinfo=IST), "2030-01-02", 20300102, None],
    ids=["datetime", "str", "int", "none"],
)
def test_queries_take_dates_only(bad: object) -> None:
    untyped: Any = bad
    queries = (
        CALENDAR.is_session,
        CALENDAR.kind_of,
        CALENDAR.next_session,
        CALENDAR.previous_session,
    )
    for query in queries:
        with pytest.raises(TypeError, match="must be a date"):
            query(untyped)
    with pytest.raises(TypeError, match="must be a date"):
        CALENDAR.sessions_between(untyped, d(3))


# --- invalid calendars ------------------------------------------------------------------------


def test_duplicate_sessions_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate session 2030-01-03"):
        _calendar(sessions=(Session(d(2), REGULAR), Session(d(3), REGULAR), Session(d(3), SPECIAL)))


def test_unsorted_sessions_are_rejected_not_reordered() -> None:
    """A reference list out of order signals a curation error, so it is rejected."""
    with pytest.raises(ValueError, match="sessions must be in increasing date order"):
        _calendar(sessions=(Session(d(3), REGULAR), Session(d(2), REGULAR)))


@pytest.mark.parametrize("day", [BEFORE_COVERAGE, AFTER_COVERAGE], ids=["before", "after"])
def test_sessions_outside_coverage_are_rejected(day: date) -> None:
    sessions = tuple(sorted((*SESSIONS, Session(day, REGULAR)), key=lambda s: s.day))

    with pytest.raises(ValueError, match="outside coverage"):
        _calendar(sessions=sessions)


def test_coverage_must_not_end_before_it_starts() -> None:
    with pytest.raises(ValueError, match="coverage_end 2030-01-01 is before coverage_start"):
        _calendar(coverage_start=d(2), coverage_end=d(1), sessions=(SESSIONS[0],))


def test_calendar_needs_at_least_one_session() -> None:
    with pytest.raises(ValueError, match="at least one session"):
        _calendar(sessions=())


def test_single_day_coverage_with_one_session_is_valid() -> None:
    calendar = _calendar(coverage_start=d(2), coverage_end=d(2), sessions=(SESSIONS[0],))

    assert (calendar.first_session, calendar.last_session) == (d(2), d(2))


@pytest.mark.parametrize(
    "bad", [list(SESSIONS), iter(SESSIONS), None], ids=["list", "iter", "none"]
)
def test_sessions_must_be_a_tuple(bad: object) -> None:
    """A tuple cannot be changed by the caller after construction."""
    with pytest.raises(TypeError, match="sessions must be a tuple"):
        _calendar(sessions=bad)


def test_session_entries_must_be_sessions() -> None:
    with pytest.raises(TypeError, match=r"sessions\[1\] must be a Session"):
        _calendar(sessions=(SESSIONS[0], d(3)))


@pytest.mark.parametrize("field", ["coverage_start", "coverage_end"])
def test_coverage_bounds_must_be_dates(field: str) -> None:
    with pytest.raises(TypeError, match=f"{field} must be a date"):
        _calendar(**{field: datetime(2030, 1, 1, tzinfo=IST)})


@pytest.mark.parametrize("bad", ["", " v1", "v 1", "v1\n", "v1\x00"])
def test_version_must_be_a_non_empty_printable_token(bad: str) -> None:
    with pytest.raises(ValueError, match="version must be non-empty printable text"):
        _calendar(version=bad)


def test_version_must_be_a_string() -> None:
    with pytest.raises(TypeError, match="version must be a str"):
        _calendar(version=1)


def test_session_validates_its_fields() -> None:
    untyped: Any = Session  # deliberately wrong argument types
    with pytest.raises(TypeError, match="day must be a date"):
        untyped(datetime(2030, 1, 2, tzinfo=IST), REGULAR)
    with pytest.raises(TypeError, match="kind must be a SessionKind"):
        untyped(d(2), "regular")


# --- value semantics and determinism ----------------------------------------------------------


def test_calendar_and_sessions_are_immutable_values() -> None:
    assert _calendar() == CALENDAR
    assert hash(_calendar()) == hash(CALENDAR)
    assert _calendar(version="synthetic-2030-01b") != CALENDAR
    for target, name in ((CALENDAR, "sessions"), (SESSIONS[0], "kind")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(target, name, None)


def test_kinds_are_regular_and_special() -> None:
    assert {k.value for k in SessionKind} == {"regular", "special"}


_PROBE = """
from datetime import date
from trading.domain.calendar import Session, SessionKind, TradingCalendar
days = [date(2030, 1, n) for n in (2, 3, 5, 7, 8, 9, 10, 11, 14)]
cal = TradingCalendar("v", date(2030, 1, 1), date(2030, 1, 15),
                      tuple(Session(x, SessionKind.REGULAR) for x in days))
print([cal.is_session(date(2030, 1, n)) for n in range(1, 16)])
print(cal.sessions_between(date(2030, 1, 1), date(2030, 1, 15)))
print(cal.next_session(date(2030, 1, 4)), cal.previous_session(date(2030, 1, 6)))
print(repr(cal))
"""


def test_answers_do_not_depend_on_timezone_locale_or_hash_seed() -> None:
    """Runs the same queries in fresh interpreters under different TZ, locale and hash seed.
    The calendar takes no clock: wall-clock independence is enforced by the DC3 ban."""
    outputs = set()
    environments = (
        ("UTC", "C", "0"),
        ("Pacific/Kiritimati", "en_US.UTF-8", "1"),
        ("America/Adak", "de_DE.UTF-8", "12345"),
    )
    for tz, locale, seed in environments:
        env = {**os.environ, "TZ": tz, "LC_ALL": locale, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", _PROBE], env=env, capture_output=True, text=True, check=True
        )
        outputs.add(result.stdout)

    assert len(outputs) == 1, outputs


# --- properties -------------------------------------------------------------------------------

_DAY_OFFSETS = st.lists(st.integers(0, 60), min_size=1, max_size=40, unique=True)


def _day(offset: int) -> date:
    return date.fromordinal(date(2030, 3, 1).toordinal() + offset)


@given(_DAY_OFFSETS, st.integers(0, 60), st.integers(0, 60))
def test_every_query_agrees_with_a_brute_force_oracle(
    offsets: list[int], start_offset: int, length: int
) -> None:
    """Every covered day, session or not, is checked against a direct scan of the session list."""
    days = sorted(_day(o) for o in offsets)
    calendar = TradingCalendar("p", _day(0), _day(60), tuple(Session(x, REGULAR) for x in days))

    for x in (_day(o) for o in range(61)):
        assert calendar.is_session(x) == (x in days)
        later = [s for s in days if s > x]
        earlier = [s for s in days if s < x]
        if later:
            assert calendar.next_session(x) == later[0]
        else:
            with pytest.raises(OutsideCalendarError):
                calendar.next_session(x)
        if earlier:
            assert calendar.previous_session(x) == earlier[-1]
        else:
            with pytest.raises(OutsideCalendarError):
                calendar.previous_session(x)

    start, end = _day(start_offset), _day(min(start_offset + length, 60))
    assert calendar.sessions_between(start, end) == tuple(x for x in days if start <= x <= end)
