"""Task 1.13: index-membership reference format and loader (reference/universe/format.md).

Owner-decided semantics: G1 coverage, G2 seed, G3/O3 transitions, O2 conflicts, exactly 100 members
after all changes of an effective date, per-change knowledge time (ADR-018 §1). Synthetic data only.
"""

import dataclasses
import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from trading.domain.calendar import Session, SessionKind, TradingCalendar
from trading.domain.identity import InstrumentId
from trading.domain.timing import IST, end_of_date
from trading.domain.universe import IndexName
from trading.infrastructure.market_data.membership import (
    FORMAT,
    MembershipFileError,
    MembershipHistory,
    MembershipProblem,
    MembershipUnknownError,
    load_membership,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/universe/nifty100-synthetic.toml"
TICK = timedelta(microseconds=1)
LATE = datetime(2030, 1, 31, tzinfo=IST)  # after every announcement in the fixture
MEMBERS = [f"INS-{n:03d}" for n in range(1, 101)]


def d(day: int) -> date:
    return date(2030, 1, day)


def ins(n: int) -> InstrumentId:
    return InstrumentId(f"INS-{n:03d}")


# Synthetic calendar: closed on 1, 4 (a weekday), 5-6, 12-13 and 15 Jan.
SESSION_DAYS = (2, 3, 7, 8, 9, 10, 11, 14)
CALENDAR = TradingCalendar(
    "synthetic-2030-01",
    d(1),
    d(15),
    tuple(Session(d(n), SessionKind.REGULAR) for n in SESSION_DAYS),
)


def change(
    instrument: str, kind: str, effective: str, known: str, source: str | None = "synthetic: n"
) -> dict[str, str | None]:
    return {
        "instrument_id": instrument,
        "change": kind,
        "effective_date": effective,
        "known_at": known,
        "source": source,
    }


CHANGES = [
    change("INS-050", "removed", "2030-01-05", "2030-01-02T19:00:00+05:30"),
    change("INS-101", "added", "2030-01-05", "2030-01-02T19:00:00+05:30"),
    change("INS-007", "removed", "2030-01-08", "2030-01-03"),
    change("INS-102", "added", "2030-01-08", "2030-01-03"),
    change("INS-102", "removed", "2030-01-14", "2030-01-10T12:30:00Z"),
    change("INS-103", "added", "2030-01-14", "2030-01-10T12:30:00Z"),
]


def toml(
    *,
    members: list[str] | None = None,
    changes: list[dict[str, str | None]] | None = None,
    seed: dict[str, str | None] | None = None,
    header: dict[str, str] | None = None,
    omit_seed: bool = False,
    exceptions: list[dict[str, str | None]] | None = None,
    extra: str = "",
) -> str:
    """Render a membership file. Values in `seed`/`header`/changes are TOML literals, except that
    string fields are quoted here; None omits the field."""
    head = {
        "format": f'"{FORMAT}"',
        "index": '"NIFTY 100"',
        "version": '"synthetic-2030-01"',
        "coverage_start": "2030-01-01",
        "coverage_end": "2030-01-15",
    } | (header or {})
    lines = [f"{key} = {value}" for key, value in head.items()]
    if not omit_seed:
        defaults: dict[str, str | None] = {
            "effective_date": "2030-01-01",
            "known_at": "2029-12-20",
            "source": '"synthetic: seed"',
        }
        seed_fields = defaults | (seed or {})
        lines.append("[seed]")
        lines += [f"{key} = {value}" for key, value in seed_fields.items() if value is not None]
        member_list = MEMBERS if members is None else members
        lines.append("members = [" + ", ".join(f'"{m}"' for m in member_list) + "]")
    for entry in CHANGES if changes is None else changes:
        lines.append("[[changes]]")
        for key, value in entry.items():
            if value is None:
                continue
            quoted = key in ("instrument_id", "change", "source")
            lines.append(f'{key} = "{value}"' if quoted else f"{key} = {value}")
    for entry in exceptions or []:
        lines.append("[[exceptions]]")
        for key, value in entry.items():
            if value is not None:
                lines.append(f'{key} = "{value}"' if key == "source" else f"{key} = {value}")
    return "\n".join(lines) + "\n" + extra


def exception(
    effective: str, count: str, known: str, source: str | None = "synthetic: index notice"
) -> dict[str, str | None]:
    return {"effective_on": effective, "expected_count": count, "known_at": known, "source": source}


def load(text: str, calendar: TradingCalendar = CALENDAR) -> MembershipHistory:
    return load_membership(text, calendar)


def problem_of(text: str, calendar: TradingCalendar = CALENDAR) -> MembershipProblem:
    with pytest.raises(MembershipFileError) as caught:
        load(text, calendar)
    return caught.value.problem


# --- valid history and the golden fixture -----------------------------------------------------


def test_fixture_file_loads_and_matches_the_rendered_equivalent() -> None:
    from_file, rendered = load(FIXTURE.read_text(encoding="utf-8")), load(toml())

    def facts(history: MembershipHistory) -> list[tuple[object, ...]]:
        return [(c.effective_date, c.instrument_id, c.change, c.known_at) for c in history.changes]

    assert facts(from_file) == facts(rendered)  # same events; only the source texts differ
    assert from_file.seed.members == rendered.seed.members
    assert from_file.seed.known_at == rendered.seed.known_at
    assert all(c.source.value.startswith("synthetic: ") for c in from_file.changes)
    assert from_file.exceptions == ()
    assert from_file.index is IndexName.NIFTY_100
    assert from_file.version == "synthetic-2030-01"
    assert (from_file.coverage_start, from_file.coverage_end) == (d(1), d(15))


def test_seed_is_retained_as_the_complete_initial_state() -> None:
    history = load(toml(members=MEMBERS[::-1]))

    assert history.seed.effective_date == d(1)
    assert history.seed.members == tuple(sorted(map(InstrumentId, MEMBERS)))
    assert history.seed.known_at == end_of_date(date(2029, 12, 20))
    assert history.seed.source.value == "synthetic: seed"
    assert len(history.changes) == len(CHANGES)  # the seed is not mixed into the changes


def test_members_on_the_coverage_start_are_the_seed() -> None:
    assert load(toml()).members_on(d(2), as_of=LATE) == frozenset(map(InstrumentId, MEMBERS))


def test_every_covered_session_has_a_complete_membership_set() -> None:
    history = load(toml())

    for session in CALENDAR.sessions_between(d(1), d(15)):
        assert len(history.members_on(session, as_of=LATE)) == 100


def test_members_on_follow_the_effective_dates() -> None:
    history = load(toml())

    on_3rd, on_7th, on_8th = (history.members_on(d(n), as_of=LATE) for n in (3, 7, 8))
    assert ins(50) in on_3rd and ins(101) not in on_3rd
    assert ins(50) not in on_7th and ins(101) in on_7th
    assert ins(7) in on_7th and ins(102) not in on_7th
    assert ins(7) not in on_8th and ins(102) in on_8th


def test_a_change_effective_on_a_non_session_applies_from_that_date() -> None:
    """5 Jan is a Saturday: the state for the 7 Jan session (and for 5 Jan itself) includes it."""
    history = load(toml())

    assert not CALENDAR.is_session(d(5))
    assert ins(101) in history.members_on(d(5), as_of=LATE)
    assert ins(101) not in history.members_on(d(4), as_of=LATE)


def test_dates_outside_coverage_are_unknown_not_empty() -> None:
    history = load(toml())

    with pytest.raises(MembershipUnknownError, match="outside coverage"):
        history.members_on(d(16), as_of=LATE)
    with pytest.raises(MembershipUnknownError, match="outside coverage"):
        history.members_on(date(2029, 12, 31), as_of=LATE)


def test_multiple_valid_changes_on_one_effective_date() -> None:
    changes = [
        *(change(f"INS-{n:03d}", "removed", "2030-01-09", "2030-01-04") for n in (1, 2, 3)),
        *(change(f"INS-{n:03d}", "added", "2030-01-09", "2030-01-04") for n in (201, 202, 203)),
    ]
    members = load(toml(changes=changes)).members_on(d(9), as_of=LATE)

    assert {ins(1), ins(2), ins(3)}.isdisjoint(members)
    assert {ins(201), ins(202), ins(203)} <= members


def test_a_removed_instrument_may_rejoin_later() -> None:
    changes = [
        change("INS-050", "removed", "2030-01-05", "2030-01-02"),
        change("INS-101", "added", "2030-01-05", "2030-01-02"),
        change("INS-101", "removed", "2030-01-09", "2030-01-04"),
        change("INS-050", "added", "2030-01-09", "2030-01-04"),
    ]
    history = load(toml(changes=changes))

    assert ins(50) not in history.members_on(d(7), as_of=LATE)
    assert ins(50) in history.members_on(d(9), as_of=LATE)


# --- knowledge time ---------------------------------------------------------------------------


def test_a_date_only_announcement_is_known_at_the_end_of_that_date() -> None:
    history = load(toml())
    known = end_of_date(d(3))

    before = history.members_on(d(8), as_of=known - TICK)
    at = history.members_on(d(8), as_of=known)
    assert ins(7) in before and ins(102) not in before
    assert ins(7) not in at and ins(102) in at


def test_an_offset_announcement_is_known_from_that_instant() -> None:
    history = load(toml())
    known = datetime(2030, 1, 2, 19, 0, tzinfo=IST)

    assert ins(101) not in history.members_on(d(7), as_of=known - TICK)
    assert ins(101) in history.members_on(d(7), as_of=known)


def test_a_change_known_later_does_not_affect_earlier_answers() -> None:
    """A replacement effective on 9 Jan, announced only on 11 Jan: before then, every answer for
    every covered date equals the history without it; from then on, it takes effect on 9 Jan."""
    late = [
        change("INS-010", "removed", "2030-01-09", "2030-01-11"),
        change("INS-210", "added", "2030-01-09", "2030-01-11"),
    ]
    base, perturbed = load(toml()), load(toml(changes=[*CHANGES, *late]))
    announced = end_of_date(d(11))

    for n in range(1, 16):
        for as_of in (end_of_date(d(3)), announced - TICK):
            assert perturbed.members_on(d(n), as_of=as_of) == base.members_on(d(n), as_of=as_of)
    assert ins(210) in perturbed.members_on(d(9), as_of=announced)
    assert ins(210) not in perturbed.members_on(d(8), as_of=announced)


@pytest.mark.parametrize(
    "zone", [UTC, timezone(timedelta(hours=14)), timezone(timedelta(hours=-11))]
)
def test_the_same_instant_in_any_zone_gives_the_same_answer(zone: timezone) -> None:
    history = load(toml())
    for instant in (end_of_date(d(3)) - TICK, end_of_date(d(3)), LATE):
        assert history.members_on(d(8), as_of=instant.astimezone(zone)) == history.members_on(
            d(8), as_of=instant
        )


def test_an_as_of_before_the_seed_is_known_is_unknown_not_empty() -> None:
    seed_known = end_of_date(date(2029, 12, 20))

    with pytest.raises(MembershipUnknownError, match="seed"):
        load(toml()).members_on(d(2), as_of=seed_known - TICK)
    assert len(load(toml()).members_on(d(2), as_of=seed_known)) == 100


@pytest.mark.parametrize(
    ("first_known", "second_known", "partial_count"),
    [("2030-01-03", "2030-01-07", 99), ("2030-01-07", "2030-01-03", 101)],
    ids=["removal-known-first-99", "addition-known-first-101"],
)
def test_partial_knowledge_may_show_a_temporary_non_100_state_without_an_exception(
    first_known: str, second_known: str, partial_count: int
) -> None:
    """Owner decision: the 100-member rule applies to the complete history; a knowledge-limited
    as-of view may hold 99 or 101 members until the rest of the reconstitution is known."""
    changes = [
        change("INS-001", "removed", "2030-01-09", first_known),
        change("INS-201", "added", "2030-01-09", second_known),
    ]
    history = load(toml(changes=changes))

    assert history.exceptions == ()
    partial = history.members_on(d(9), as_of=datetime(2030, 1, 5, tzinfo=IST))
    assert len(partial) == partial_count
    assert len(history.members_on(d(9), as_of=LATE)) == 100


def test_a_later_effective_change_known_first_is_valid_and_hidden_until_known() -> None:
    """Effective date and knowledge time are independent: INS-101's removal (effective 9 Jan) is
    announced on 3 Jan, before its addition (effective 5 Jan) on 4 Jan. Each is visible only from
    its own knowledge time, and the visible changes apply in effective order."""
    changes = [
        change("INS-050", "removed", "2030-01-05", "2030-01-04"),
        change("INS-101", "added", "2030-01-05", "2030-01-04"),
        change("INS-101", "removed", "2030-01-09", "2030-01-03"),
        change("INS-050", "added", "2030-01-09", "2030-01-03"),
    ]
    history = load(toml(changes=changes))
    removal_known, addition_known = end_of_date(d(3)), end_of_date(d(4))

    assert ins(101) not in history.members_on(d(7), as_of=removal_known)  # addition not known
    assert ins(101) not in history.members_on(d(9), as_of=removal_known)
    assert ins(101) in history.members_on(d(7), as_of=addition_known)
    assert ins(101) not in history.members_on(d(9), as_of=addition_known)
    assert ins(101) not in history.members_on(d(7), as_of=removal_known - TICK)
    assert ins(50) in history.members_on(d(7), as_of=addition_known - TICK)


def test_members_on_requires_a_date_and_an_aware_instant() -> None:
    history = load(toml())
    untyped: Any = datetime(2030, 1, 8, tzinfo=IST)

    with pytest.raises(TypeError, match="day must be a date"):
        history.members_on(untyped, as_of=LATE)
    with pytest.raises(ValueError, match="timezone-aware"):
        history.members_on(d(8), as_of=datetime(2030, 1, 8))


# --- G1 coverage and G2 seed ------------------------------------------------------------------


def test_missing_seed_is_rejected() -> None:
    assert problem_of(toml(omit_seed=True)) is MembershipProblem.MISSING_SEED


def test_seed_starting_after_a_covered_session_leaves_a_gap() -> None:
    """Coverage starts 1 Jan; a seed effective 3 Jan leaves the 2 Jan session undefined."""
    assert problem_of(toml(seed={"effective_date": "2030-01-03"})) is MembershipProblem.COVERAGE_GAP


def test_seed_not_effective_on_the_coverage_start_is_rejected_even_without_a_session_gap() -> None:
    """2 Jan is the first session, so no session is undefined, but G2 still requires the seed on
    the coverage start."""
    assert problem_of(toml(seed={"effective_date": "2030-01-02"})) is MembershipProblem.MISSING_SEED
    assert problem_of(toml(seed={"effective_date": "2029-12-31"})) is MembershipProblem.MISSING_SEED


def test_coverage_beyond_the_calendar_is_a_gap() -> None:
    """Sessions outside the calendar are unknown, so they cannot be shown to have a member set."""
    late_end = toml(header={"coverage_end": "2030-01-16"})

    assert problem_of(late_end) is MembershipProblem.COVERAGE_GAP


def test_coverage_must_not_end_before_it_starts() -> None:
    reversed_coverage = toml(header={"coverage_start": "2030-01-15", "coverage_end": "2030-01-01"})

    assert problem_of(reversed_coverage) is MembershipProblem.MALFORMED


# --- G3 / O3 transitions and O2 conflicts -----------------------------------------------------


def test_adding_a_current_member_is_rejected() -> None:
    changes = [
        change("INS-001", "added", "2030-01-08", "2030-01-03"),
        change("INS-002", "removed", "2030-01-08", "2030-01-03"),
    ]
    assert problem_of(toml(changes=changes)) is MembershipProblem.INVALID_TRANSITION


def test_removing_a_non_member_is_rejected() -> None:
    changes = [
        change("INS-999", "removed", "2030-01-08", "2030-01-03"),
        change("INS-201", "added", "2030-01-08", "2030-01-03"),
    ]
    assert problem_of(toml(changes=changes)) is MembershipProblem.INVALID_TRANSITION


def test_duplicate_seed_member_is_rejected() -> None:
    members = [*MEMBERS[:99], MEMBERS[0]]

    assert problem_of(toml(members=members, changes=[])) is MembershipProblem.INVALID_TRANSITION


@pytest.mark.parametrize(
    "pair",
    [
        ("added", "removed"),
        ("removed", "removed"),
    ],
    ids=["contradictory", "duplicate"],
)
def test_two_changes_for_one_instrument_on_one_date_conflict(pair: tuple[str, str]) -> None:
    changes = [change("INS-050", kind, "2030-01-08", "2030-01-03") for kind in pair]

    assert problem_of(toml(changes=changes)) is MembershipProblem.CONFLICTING_CHANGE


@pytest.mark.parametrize("effective", ["2029-12-31", "2030-01-16"], ids=["before", "after"])
def test_changes_must_take_effect_inside_coverage(effective: str) -> None:
    changes = [
        change("INS-050", "removed", effective, "2029-12-20"),
        change("INS-201", "added", effective, "2029-12-20"),
    ]
    assert problem_of(toml(changes=changes)) is MembershipProblem.OUTSIDE_COVERAGE


@pytest.mark.parametrize("effective", ["2030-01-01", "2030-01-15"], ids=["start", "end"])
def test_changes_on_the_coverage_boundaries_are_inside(effective: str) -> None:
    changes = [
        change("INS-050", "removed", effective, "2029-12-20"),
        change("INS-201", "added", effective, "2029-12-20"),
    ]
    assert ins(201) in load(toml(changes=changes)).members_on(d(15), as_of=LATE)


def test_seed_plus_valid_changes_on_the_coverage_start() -> None:
    """Owner decision: the seed is the initial state on coverage_start; changes effective that
    day then apply under the normal rules, and the count is checked after all of them."""
    replace_on_start = [
        change("INS-050", "removed", "2030-01-01", "2029-12-21"),
        change("INS-201", "added", "2030-01-01", "2029-12-21"),
    ]
    history = load(toml(changes=replace_on_start))
    on_start = history.members_on(d(1), as_of=LATE)

    assert ins(50) not in on_start and ins(201) in on_start and len(on_start) == 100
    assert ins(50) in history.members_on(d(1), as_of=end_of_date(d(1)) - timedelta(days=12))
    short_seed_completed = [change("INS-201", "added", "2030-01-01", "2029-12-21")]
    assert (
        len(
            load(toml(members=MEMBERS[:99], changes=short_seed_completed)).members_on(
                d(1), as_of=LATE
            )
        )
        == 100
    )


def test_changes_on_the_coverage_start_follow_the_transition_rules() -> None:
    adds_seed_member = [
        change("INS-001", "added", "2030-01-01", "2029-12-21"),
        change("INS-050", "removed", "2030-01-01", "2029-12-21"),
    ]
    removes_non_member = [
        change("INS-999", "removed", "2030-01-01", "2029-12-21"),
        change("INS-201", "added", "2030-01-01", "2029-12-21"),
    ]
    assert problem_of(toml(changes=adds_seed_member)) is MembershipProblem.INVALID_TRANSITION
    assert problem_of(toml(changes=removes_non_member)) is MembershipProblem.INVALID_TRANSITION


# --- member count -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("removed", "added"),
    [("INS-050", "INS-201"), ("INS-050", "INS-000")],
    ids=["removal-sorts-first", "addition-sorts-first"],
)
def test_count_is_checked_after_all_changes_of_an_effective_date(removed: str, added: str) -> None:
    """Changes are applied in (date, instrument) order, so one replacement passes through 99 and the
    other through 101 members mid-date; both are valid because the count is checked per date."""
    replacement = [
        change(removed, "removed", "2030-01-08", "2030-01-03"),
        change(added, "added", "2030-01-08", "2030-01-03"),
    ]
    assert len(load(toml(changes=replacement)).members_on(d(8), as_of=LATE)) == 100


@pytest.mark.parametrize(
    "changes",
    [
        [change("INS-050", "removed", "2030-01-08", "2030-01-03")],
        [change("INS-201", "added", "2030-01-08", "2030-01-03")],
        [
            change("INS-050", "removed", "2030-01-08", "2030-01-03"),
            change("INS-201", "added", "2030-01-09", "2030-01-03"),
        ],
    ],
    ids=["removal-only", "addition-only", "replacement-on-different-dates"],
)
def test_a_count_other_than_100_after_an_effective_date_is_rejected(
    changes: list[dict[str, str | None]],
) -> None:
    assert problem_of(toml(changes=changes)) is MembershipProblem.MEMBER_COUNT


def test_a_seed_without_exactly_100_members_is_rejected() -> None:
    assert problem_of(toml(members=MEMBERS[:99], changes=[])) is MembershipProblem.MEMBER_COUNT


# --- sourced member-count exceptions ----------------------------------------------------------

REMOVAL_ONLY = [change("INS-050", "removed", "2030-01-08", "2030-01-03")]


def test_a_sourced_exception_allows_the_stated_count_on_its_date() -> None:
    history = load(
        toml(changes=REMOVAL_ONLY, exceptions=[exception("2030-01-08", "99", "2030-01-03")])
    )

    assert len(history.members_on(d(8), as_of=LATE)) == 99
    (recorded,) = history.exceptions
    assert (recorded.effective_on, recorded.expected_count) == (d(8), 99)
    assert recorded.source.value == "synthetic: index notice"
    assert recorded.known_at == end_of_date(d(3))


def test_an_exception_on_the_coverage_start_covers_the_seed_state() -> None:
    history = load(
        toml(
            members=MEMBERS[:99],
            changes=[],
            exceptions=[exception("2030-01-01", "99", "2029-12-20")],
        )
    )

    assert len(history.members_on(d(2), as_of=LATE)) == 99


def test_the_normal_state_needs_no_exception() -> None:
    assert load(toml()).exceptions == ()


@pytest.mark.parametrize(
    ("effective", "count", "problem"),
    [
        ("2030-01-09", "99", MembershipProblem.MEMBER_COUNT),  # wrong date: 8 Jan unexcused
        ("2030-01-08", "98", MembershipProblem.MEMBER_COUNT),  # states another count
        ("2030-01-16", "99", MembershipProblem.OUTSIDE_COVERAGE),
    ],
    ids=["other-date", "wrong-count", "outside-coverage"],
)
def test_an_exception_must_match_its_effective_date_and_count(
    effective: str, count: str, problem: MembershipProblem
) -> None:
    text = toml(changes=REMOVAL_ONLY, exceptions=[exception(effective, count, "2030-01-03")])

    assert problem_of(text) is problem


def test_an_exception_for_a_date_without_a_change_is_rejected() -> None:
    """With the count already excused on 8 Jan, an exception for 9 Jan (no change) is orphaned."""
    exceptions = [
        exception("2030-01-08", "99", "2030-01-03"),
        exception("2030-01-09", "99", "2030-01-03"),
    ]

    assert problem_of(toml(changes=REMOVAL_ONLY, exceptions=exceptions)) is (
        MembershipProblem.MEMBER_COUNT
    )


def test_two_exceptions_for_one_date_are_rejected() -> None:
    exceptions = [
        exception("2030-01-08", "99", "2030-01-03"),
        exception("2030-01-08", "99", "2030-01-04"),
    ]

    assert problem_of(toml(changes=REMOVAL_ONLY, exceptions=exceptions)) is (
        MembershipProblem.MEMBER_COUNT
    )


@pytest.mark.parametrize("value", [None, "", "   "], ids=["missing", "empty", "blank"])
def test_an_exception_without_a_source_is_rejected(value: str | None) -> None:
    text = toml(
        changes=REMOVAL_ONLY, exceptions=[exception("2030-01-08", "99", "2030-01-03", value)]
    )

    assert problem_of(text) is MembershipProblem.MISSING_SOURCE


@pytest.mark.parametrize(
    "count", ["-1", "99.0", "true", '"99"'], ids=["negative", "float", "bool", "str"]
)
def test_an_exception_count_must_be_a_non_negative_integer(count: str) -> None:
    text = toml(changes=REMOVAL_ONLY, exceptions=[exception("2030-01-08", count, "2030-01-03")])

    assert problem_of(text) is MembershipProblem.MALFORMED


def test_an_exception_is_visible_only_from_its_knowledge_time() -> None:
    history = load(
        toml(
            changes=REMOVAL_ONLY,
            exceptions=[exception("2030-01-08", "99", "2030-01-04T10:00:00+05:30")],
        )
    )
    known = datetime(2030, 1, 4, 10, 0, tzinfo=IST)

    assert history.count_exception(d(8), as_of=known - TICK) is None
    assert history.count_exception(d(8), as_of=known) == history.exceptions[0]
    assert history.count_exception(d(8), as_of=known.astimezone(UTC)) == history.exceptions[0]
    assert history.count_exception(d(9), as_of=LATE) is None  # exact effective-date match only


# --- sources ----------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, '""', '"   "'], ids=["missing", "empty", "blank"])
def test_seed_without_a_source_is_rejected(value: str | None) -> None:
    assert problem_of(toml(seed={"source": value})) is MembershipProblem.MISSING_SOURCE


@pytest.mark.parametrize("value", [None, "", "   "], ids=["missing", "empty", "blank"])
def test_change_without_a_source_is_rejected(value: str | None) -> None:
    changes = [
        change("INS-050", "removed", "2030-01-08", "2030-01-03", source=value),
        change("INS-201", "added", "2030-01-08", "2030-01-03"),
    ]
    assert problem_of(toml(changes=changes)) is MembershipProblem.MISSING_SOURCE


# --- malformed files --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "format = ",
        toml(header={"format": '"index-membership-v2"'}),
        toml(header={"index": '"NIFTY 50"'}),
        toml(header={"version": '"v 1"'}),
        toml(header={"coverage_start": '"2030-01-01"'}),
        toml(header={"coverage_start": "2030-01-01T00:00:00+05:30"}),
        toml(seed={"known_at": "2029-12-20T18:00:00"}),
        toml(seed={"known_at": "18:00:00"}),
        toml(members=["INS 001", *MEMBERS[1:]]),
        toml(changes=[change("INS-050", "add", "2030-01-08", "2030-01-03")]),
        toml(extra="unexpected = 1\n"),
        toml(seed={"extra_field": '"x"'}),
        toml(changes=[{**change("INS-050", "removed", "2030-01-08", "2030-01-03"), "note": "x"}]),
    ],
    ids=[
        "invalid-toml",
        "unknown-format",
        "unknown-index",
        "bad-version",
        "date-as-string",
        "datetime-as-date",
        "naive-known-at",
        "time-only-known-at",
        "bad-instrument-id",
        "unknown-change-kind",
        "unknown-top-level-key",
        "unknown-seed-key",
        "unknown-change-key",
    ],
)
def test_malformed_files_are_rejected(text: str) -> None:
    assert problem_of(text) is MembershipProblem.MALFORMED


def test_errors_name_no_more_than_keys() -> None:
    with pytest.raises(MembershipFileError) as caught:
        load(toml(changes=[change("INS-999", "removed", "2030-01-08", "2030-01-03")]))

    assert "INS-999" in str(caught.value)
    assert caught.value.problem is MembershipProblem.INVALID_TRANSITION


# --- determinism ------------------------------------------------------------------------------


def test_change_order_in_the_file_does_not_matter() -> None:
    assert load(toml(changes=CHANGES[::-1])) == load(toml())
    assert load(toml(members=MEMBERS[::-1])) == load(toml())


def test_changes_are_sorted_by_effective_date_then_instrument() -> None:
    changes = load(toml()).changes
    keys = [(c.effective_date, c.instrument_id.value) for c in changes]

    assert keys == sorted(keys)


_PROBE = """
import sys
from datetime import date, datetime
from trading.domain.calendar import Session, SessionKind, TradingCalendar
from trading.domain.timing import IST
from trading.infrastructure.market_data.membership import load_membership
days = (2, 3, 7, 8, 9, 10, 11, 14)
cal = TradingCalendar("c", date(2030, 1, 1), date(2030, 1, 15),
                      tuple(Session(date(2030, 1, n), SessionKind.REGULAR) for n in days))
history = load_membership(sys.stdin.read(), cal)
for n in days:
    for as_of in (datetime(2030, 1, 3, 23, tzinfo=IST), datetime(2030, 1, 31, tzinfo=IST)):
        print(n, sorted(m.value for m in history.members_on(date(2030, 1, n), as_of=as_of)))
print([(c.effective_date, c.instrument_id.value, c.change.value) for c in history.changes])
"""


def test_answers_do_not_depend_on_timezone_locale_or_hash_seed() -> None:
    text = FIXTURE.read_text(encoding="utf-8")
    outputs = set()
    for tz, locale, seed in (("UTC", "C", "0"), ("Pacific/Kiritimati", "en_US.UTF-8", "77")):
        env = {**os.environ, "TZ": tz, "LC_ALL": locale, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            input=text,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.add(result.stdout)

    assert len(outputs) == 1


# --- the history validates itself, not only through the loader --------------------------------


def _direct(**overrides: Any) -> MembershipProblem:
    valid = load(toml())
    fields: dict[str, Any] = {
        "index": valid.index,
        "version": valid.version,
        "coverage_start": valid.coverage_start,
        "coverage_end": valid.coverage_end,
        "seed": valid.seed,
        "changes": valid.changes,
        "exceptions": valid.exceptions,
    } | overrides
    with pytest.raises(MembershipFileError) as caught:
        MembershipHistory(**fields)
    return caught.value.problem


def test_a_directly_built_history_is_validated_too() -> None:
    valid = load(toml())
    before_start = dataclasses.replace(valid.changes[0], effective_date=date(2029, 12, 31))
    late_seed = dataclasses.replace(valid.seed, effective_date=d(2))
    unsorted_seed_members = tuple(reversed(valid.seed.members))

    assert _direct(changes=valid.changes[::-1]) is MembershipProblem.MALFORMED  # not sorted
    assert _direct(seed=late_seed) is MembershipProblem.MISSING_SEED
    assert _direct(changes=(before_start, *valid.changes[1:])) is MembershipProblem.OUTSIDE_COVERAGE
    with pytest.raises(MembershipFileError, match="sorted"):
        dataclasses.replace(valid.seed, members=unsorted_seed_members)
    assert (
        MembershipHistory(
            valid.index,
            valid.version,
            valid.coverage_start,
            valid.coverage_end,
            valid.seed,
            valid.changes,
            valid.exceptions,
        )
        == valid
    )


# --- knowledge time relative to the seed, TOML shapes ------------------------------------------


def test_a_change_announced_before_the_seed_list_was_published_is_accepted() -> None:
    """No as-of view before the seed is known is answerable, so a replacement announced on
    15 Dec (seed known 20 Dec) is visible together with the seed in every answerable view."""
    changes = [
        change("INS-050", "removed", "2030-01-08", "2029-12-15"),
        change("INS-201", "added", "2030-01-08", "2029-12-15"),
    ]
    history = load(toml(changes=changes))
    seed_known = end_of_date(date(2029, 12, 20))

    assert ins(201) in history.members_on(d(8), as_of=seed_known)
    assert ins(50) not in history.members_on(d(8), as_of=seed_known)


def test_changes_of_one_instrument_known_at_the_same_instant_are_accepted() -> None:
    changes = [
        change("INS-050", "removed", "2030-01-05", "2030-01-02"),
        change("INS-101", "added", "2030-01-05", "2030-01-02"),
        change("INS-101", "removed", "2030-01-09", "2030-01-02"),
        change("INS-050", "added", "2030-01-09", "2030-01-02"),
    ]
    history = load(toml(changes=changes))

    assert ins(101) in history.members_on(d(7), as_of=LATE)
    assert ins(101) not in history.members_on(d(9), as_of=LATE)


def test_a_seed_published_after_the_coverage_start_is_accepted_and_unknown_before() -> None:
    history = load(toml(seed={"known_at": "2030-01-02T18:00:00+05:30"}))
    published = datetime(2030, 1, 2, 18, 0, tzinfo=IST)

    with pytest.raises(MembershipUnknownError, match="seed"):
        history.members_on(d(1), as_of=published - TICK)
    assert len(history.members_on(d(1), as_of=published)) == 100


@pytest.mark.parametrize(
    "text",
    [
        toml(omit_seed=True, extra="[[seed]]\neffective_date = 2030-01-01\n"),
        toml(changes=[]) + '[changes]\ninstrument_id = "INS-050"\n',
        toml(seed={"source": "true"}),
        toml(members=[], changes=[]).replace("members = []", 'members = [["INS-001"]]'),
    ],
    ids=["seed-as-array", "changes-as-table", "boolean-source", "nested-member-list"],
)
def test_toml_shape_errors_are_malformed(text: str) -> None:
    assert problem_of(text) is MembershipProblem.MALFORMED


def test_an_exception_stating_the_normal_count_is_rejected_even_where_it_matches() -> None:
    """8 Jan already has 100 members (a replacement); an exception stating 100 excuses nothing."""
    text = toml(exceptions=[exception("2030-01-08", "100", "2030-01-03")])

    assert problem_of(text) is MembershipProblem.MEMBER_COUNT


@pytest.mark.parametrize(
    "exceptions",
    [[], [exception("2030-01-01", "0", "2029-12-20")]],
    ids=["no-exception", "with-zero-count-exception"],
)
def test_an_empty_seed_is_a_missing_seed(exceptions: list[dict[str, str | None]]) -> None:
    text = toml(members=[], changes=[], exceptions=exceptions)

    assert problem_of(text) is MembershipProblem.MISSING_SEED
