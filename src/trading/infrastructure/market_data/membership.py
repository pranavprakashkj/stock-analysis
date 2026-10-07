"""Index-membership reference files (task 1.13; ADR-002 §1-2, ADR-018 §1).

Format and rules: reference/universe/format.md. `load_membership` parses the text of one file
(no file access, no clock) against a trading calendar and returns a validated `MembershipHistory`:
a seed (the complete member set on the coverage start), dated `IndexMembershipChange` records and
sourced member-count exceptions.

Complete history (all records): G2 the seed takes effect on coverage_start; changes take effect
inside coverage and are applied after the seed in effective order; G3/O3 no `added` for a member
and no `removed` for a non-member; O2 no two changes for one instrument on one date; after all
changes of each effective date (and on coverage_start) the count is the index's normal count,
unless a sourced exception for that date states the actual count. G1 (every covered session has a
member set) is checked against the trading calendar, which must cover the coverage range.

As-of views (`members_on(day, as_of=...)`): a change is visible when known by `as_of` and effective
on or before `day`. Visible changes are applied in effective order, so the latest visible event for
an instrument decides its membership. Knowledge-limited views may hold a count other than the normal
one (e.g. a removal announced before its replacement); no count rule applies to them.
"""

import re
import tomllib
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from itertools import groupby
from typing import NoReturn

from trading.domain.availability import SourceRef
from trading.domain.calendar import OutsideCalendarError, TradingCalendar
from trading.domain.checks import require_date, require_instance
from trading.domain.identity import InstrumentId
from trading.domain.timing import end_of_date, is_known, require_aware
from trading.domain.universe import IndexMembershipChange, IndexName, MembershipChange

FORMAT = "index-membership-v1"
_MEMBER_COUNT = {IndexName.NIFTY_100: 100}
_TOP_REQUIRED = frozenset({"format", "index", "version", "coverage_start", "coverage_end", "seed"})
_TOP_OPTIONAL = frozenset({"changes", "exceptions"})
_SEED_KEYS = frozenset({"effective_date", "known_at", "source", "members"})
_CHANGE_KEYS = frozenset({"instrument_id", "change", "effective_date", "known_at", "source"})
_EXCEPTION_KEYS = frozenset({"effective_on", "expected_count", "source", "known_at"})
_TOKEN = re.compile(r"\S+")


class MembershipProblem(Enum):
    """Stable categories of a rejected membership file."""

    MALFORMED = "malformed"
    MISSING_SOURCE = "missing_source"
    MISSING_SEED = "missing_seed"  # G2
    COVERAGE_GAP = "coverage_gap"  # G1
    OUTSIDE_COVERAGE = "outside_coverage"  # a change or exception dated outside coverage
    INVALID_TRANSITION = "invalid_transition"  # G3 / O3
    CONFLICTING_CHANGE = "conflicting_change"  # O2
    MEMBER_COUNT = "member_count"  # count rule, including inconsistent exceptions


class MembershipFileError(Exception):
    """The membership file is rejected. `problem` is the stable category."""

    def __init__(self, problem: MembershipProblem, message: str) -> None:
        super().__init__(f"{problem.value}: {message}")
        self.problem = problem


class MembershipUnknownError(Exception):
    """The member set is unknown for this date and knowledge instant (not empty)."""


def _fail(problem: MembershipProblem, message: str) -> NoReturn:
    raise MembershipFileError(problem, message)


@dataclass(frozen=True, slots=True)
class MembershipSeed:
    """The complete member set on `effective_date` (the coverage start), sorted by id."""

    effective_date: date
    members: tuple[InstrumentId, ...]
    known_at: datetime
    source: SourceRef

    def __post_init__(self) -> None:
        require_date("effective_date", self.effective_date)
        members = require_instance("members", self.members, tuple)
        for position, member in enumerate(members):
            require_instance(f"members[{position}]", member, InstrumentId)
        if not members:
            _fail(MembershipProblem.MISSING_SEED, "the seed lists no members")
        duplicates = sorted(m.value for m, n in Counter(members).items() if n > 1)
        if duplicates:
            _fail(MembershipProblem.INVALID_TRANSITION, f"seed lists members twice: {duplicates}")
        if list(members) != sorted(members):
            _fail(MembershipProblem.MALFORMED, "seed members must be sorted")
        require_aware(self.known_at)
        require_instance("source", self.source, SourceRef)


@dataclass(frozen=True, slots=True)
class MemberCountException:
    """On `effective_on`, the member count is `expected_count` instead of the normal count."""

    effective_on: date
    expected_count: int
    source: SourceRef
    known_at: datetime

    def __post_init__(self) -> None:
        require_date("effective_on", self.effective_on)
        if require_instance("expected_count", self.expected_count, int) < 0:
            raise ValueError(f"expected_count must be >= 0: {self.expected_count}")
        require_instance("source", self.source, SourceRef)
        require_aware(self.known_at)


@dataclass(frozen=True, slots=True)
class MembershipHistory:
    """A validated membership history. `changes` are sorted by effective date, then instrument id;
    `exceptions` by effective date."""

    index: IndexName
    version: str
    coverage_start: date
    coverage_end: date
    seed: MembershipSeed
    changes: tuple[IndexMembershipChange, ...]
    exceptions: tuple[MemberCountException, ...]

    def __post_init__(self) -> None:
        require_instance("index", self.index, IndexName)
        version = require_instance("version", self.version, str)
        if not _TOKEN.fullmatch(version) or not version.isprintable():
            _fail(MembershipProblem.MALFORMED, f"version must be a non-empty token: {version!r}")
        require_date("coverage_start", self.coverage_start)
        require_date("coverage_end", self.coverage_end)
        if self.coverage_end < self.coverage_start:
            _fail(MembershipProblem.MALFORMED, "coverage_end is before coverage_start")
        if (
            require_instance("seed", self.seed, MembershipSeed).effective_date
            != self.coverage_start
        ):
            _fail(MembershipProblem.MISSING_SEED, "the seed must take effect on coverage_start")
        self._check_changes()
        self._check_exceptions()
        self._check_transitions_and_counts()

    def _covered(self, day: date) -> bool:
        return self.coverage_start <= day <= self.coverage_end

    def _check_changes(self) -> None:
        changes = require_instance("changes", self.changes, tuple)
        for position, change in enumerate(changes):
            require_instance(f"changes[{position}]", change, IndexMembershipChange)
            if change.index is not self.index:
                _fail(
                    MembershipProblem.MALFORMED, f"change for another index: {change.index.value}"
                )
            if not self._covered(change.effective_date):
                _fail(
                    MembershipProblem.OUTSIDE_COVERAGE,
                    f"{change.instrument_id.value} change effective {change.effective_date} is "
                    f"outside coverage {self.coverage_start}..{self.coverage_end}",
                )
        keys = [(c.effective_date, c.instrument_id.value) for c in changes]
        if keys != sorted(keys):
            _fail(MembershipProblem.MALFORMED, "changes must be sorted by date, then instrument")
        for (effective, instrument), count in Counter(keys).items():
            if count > 1:
                _fail(
                    MembershipProblem.CONFLICTING_CHANGE,
                    f"{count} changes for {instrument} effective {effective}",
                )

    def _check_exceptions(self) -> None:
        exceptions = require_instance("exceptions", self.exceptions, tuple)
        for position, exception in enumerate(exceptions):
            require_instance(f"exceptions[{position}]", exception, MemberCountException)
            if not self._covered(exception.effective_on):
                _fail(
                    MembershipProblem.OUTSIDE_COVERAGE,
                    f"count exception effective {exception.effective_on} is outside coverage",
                )
            if exception.expected_count == _MEMBER_COUNT[self.index]:
                _fail(
                    MembershipProblem.MEMBER_COUNT,
                    f"count exception on {exception.effective_on} states the normal count",
                )
        dates = [e.effective_on for e in exceptions]
        if dates != sorted(dates):
            _fail(MembershipProblem.MALFORMED, "exceptions must be sorted by effective date")
        for effective, count in Counter(dates).items():
            if count > 1:
                _fail(MembershipProblem.MEMBER_COUNT, f"{count} count exceptions for {effective}")

    def _check_transitions_and_counts(self) -> None:
        """Complete history: seed, then each effective date's changes; then the count rule."""
        members = set(self.seed.members)
        by_date = {k: list(g) for k, g in groupby(self.changes, key=lambda c: c.effective_date)}
        exceptions = {e.effective_on: e for e in self.exceptions}
        checked = sorted({self.coverage_start, *by_date})
        for effective in checked:
            for change in by_date.get(effective, []):
                active = change.instrument_id in members
                if change.change is MembershipChange.ADDED and active:
                    _fail(
                        MembershipProblem.INVALID_TRANSITION,
                        f"{change.instrument_id.value} added on {effective} while a member",
                    )
                if change.change is MembershipChange.REMOVED and not active:
                    _fail(
                        MembershipProblem.INVALID_TRANSITION,
                        f"{change.instrument_id.value} removed on {effective} while not a member",
                    )
                if change.change is MembershipChange.ADDED:
                    members.add(change.instrument_id)
                else:
                    members.remove(change.instrument_id)
            expected = _MEMBER_COUNT[self.index]
            exception = exceptions.get(effective)
            if exception is not None:
                expected = exception.expected_count
            if len(members) != expected:
                _fail(
                    MembershipProblem.MEMBER_COUNT,
                    f"{len(members)} members on {effective}, expected {expected}"
                    + ("" if exception is None else " (sourced exception)"),
                )
        unused = sorted(set(exceptions) - set(checked))
        if unused:
            _fail(
                MembershipProblem.MEMBER_COUNT,
                f"count exceptions for dates with no change: {[str(d) for d in unused]}",
            )

    def members_on(self, day: date, *, as_of: datetime) -> frozenset[InstrumentId]:
        """Members on `day` as known at `as_of`: the seed, then the changes known by `as_of` and
        effective on or before `day`, in effective order. Unknown (raises) outside the coverage
        range or before the seed is known. May hold a non-normal count while knowledge is
        partial."""
        require_date("day", day)
        require_aware(as_of)
        if not self._covered(day):
            raise MembershipUnknownError(
                f"{day} is outside coverage {self.coverage_start}..{self.coverage_end}"
            )
        if not is_known(self.seed.known_at, as_of):
            raise MembershipUnknownError(f"the seed is not known at {as_of}")
        members = set(self.seed.members)
        for change in self.changes:
            if change.effective_date > day:
                break
            if not is_known(change.known_at, as_of):
                continue
            if change.change is MembershipChange.ADDED:
                members.add(change.instrument_id)
            else:
                members.discard(change.instrument_id)
        return frozenset(members)

    def count_exception(
        self, effective_on: date, *, as_of: datetime
    ) -> MemberCountException | None:
        """The sourced count exception for `effective_on`, if one exists and is known by `as_of`."""
        require_date("effective_on", effective_on)
        require_aware(as_of)
        for exception in self.exceptions:
            if exception.effective_on == effective_on and is_known(exception.known_at, as_of):
                return exception
        return None


# --- parsing ----------------------------------------------------------------------------------


def _table(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        _fail(MembershipProblem.MALFORMED, f"{where} must be a table")
    return value


def _check_keys(
    table: Mapping[str, object],
    required: frozenset[str],
    where: str,
    optional: frozenset[str] = frozenset(),
) -> None:
    unknown = sorted(set(table) - required - optional)
    if unknown:
        _fail(MembershipProblem.MALFORMED, f"unknown keys in {where}: {unknown}")
    missing = sorted(required - set(table))
    if "source" in missing:
        _fail(MembershipProblem.MISSING_SOURCE, f"{where} has no source")
    if missing:
        _fail(MembershipProblem.MALFORMED, f"{where} is missing {missing}")


def _date(value: object, where: str) -> date:
    if type(value) is not date:
        _fail(MembershipProblem.MALFORMED, f"{where} must be a TOML date")
    return value


def _known_at(value: object, where: str) -> datetime:
    """An offset date-time as given; a date means the end of that date in IST (ADR-018 §1)."""
    if type(value) is datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            _fail(MembershipProblem.MALFORMED, f"{where} must carry an offset")
        return value
    if type(value) is date:
        return end_of_date(value)
    _fail(MembershipProblem.MALFORMED, f"{where} must be a TOML offset date-time or date")


def _text(value: object, where: str) -> str:
    if not isinstance(value, str):
        _fail(MembershipProblem.MALFORMED, f"{where} must be a string")
    return value


def _source(value: object, where: str) -> SourceRef:
    text = _text(value, where)
    if not text.strip():
        _fail(MembershipProblem.MISSING_SOURCE, f"{where} is blank")
    return SourceRef(text)


def _instrument(value: object, where: str) -> InstrumentId:
    try:
        return InstrumentId(_text(value, where))
    except ValueError:
        _fail(MembershipProblem.MALFORMED, f"{where} is not an instrument id")


def _index(value: object) -> IndexName:
    text = _text(value, "index")
    for index in IndexName:
        if index.value == text:
            return index
    _fail(MembershipProblem.MALFORMED, f"unknown index {text!r}")


def _change_kind(value: object, where: str) -> MembershipChange:
    text = _text(value, where)
    for kind in MembershipChange:
        if kind.value == text:
            return kind
    _fail(MembershipProblem.MALFORMED, f"{where} must be 'added' or 'removed'")


def _count(value: object, where: str) -> int:
    if type(value) is not int or value < 0:
        _fail(MembershipProblem.MALFORMED, f"{where} must be a non-negative integer")
    return value


def _tables(raw: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        _fail(MembershipProblem.MALFORMED, f"{key} must be an array of tables")
    return [_table(entry, f"{key}[{position}]") for position, entry in enumerate(value)]


def load_membership(text: str, calendar: TradingCalendar) -> MembershipHistory:
    """Parse and validate one membership file; raise `MembershipFileError` with its category."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise MembershipFileError(MembershipProblem.MALFORMED, f"invalid TOML: {error}") from None
    if "seed" not in raw:
        _fail(MembershipProblem.MISSING_SEED, "the file has no seed")
    _check_keys(raw, _TOP_REQUIRED, "the file", _TOP_OPTIONAL)
    if _text(raw["format"], "format") != FORMAT:
        _fail(MembershipProblem.MALFORMED, f"format must be {FORMAT!r}")
    index = _index(raw["index"])
    version = _text(raw["version"], "version")
    coverage_start = _date(raw["coverage_start"], "coverage_start")
    coverage_end = _date(raw["coverage_end"], "coverage_end")
    if coverage_end < coverage_start:  # checked before asking the calendar for the range
        _fail(MembershipProblem.MALFORMED, "coverage_end is before coverage_start")

    seed = _table(raw["seed"], "seed")
    if "members" not in seed:
        _fail(MembershipProblem.MISSING_SEED, "the seed lists no members")
    _check_keys(seed, _SEED_KEYS, "the seed")
    seed_effective = _date(seed["effective_date"], "seed.effective_date")
    try:
        sessions = calendar.sessions_between(coverage_start, coverage_end)
    except OutsideCalendarError:
        _fail(MembershipProblem.COVERAGE_GAP, "the calendar does not cover the coverage range")
    if seed_effective > coverage_start and any(s < seed_effective for s in sessions):
        _fail(
            MembershipProblem.COVERAGE_GAP,
            f"sessions from {coverage_start} have no member set before the seed ({seed_effective})",
        )
    members = seed["members"]
    if not isinstance(members, list):
        _fail(MembershipProblem.MALFORMED, "seed.members must be a list")
    seed_record = MembershipSeed(
        seed_effective,
        tuple(sorted(_instrument(m, "seed.members[]") for m in members)),
        _known_at(seed["known_at"], "seed.known_at"),
        _source(seed["source"], "seed.source"),
    )

    changes = []
    for position, entry in enumerate(_tables(raw, "changes")):
        where = f"changes[{position}]"
        _check_keys(entry, _CHANGE_KEYS, where)
        changes.append(
            IndexMembershipChange(
                index,
                _instrument(entry["instrument_id"], f"{where}.instrument_id"),
                _change_kind(entry["change"], f"{where}.change"),
                _date(entry["effective_date"], f"{where}.effective_date"),
                _known_at(entry["known_at"], f"{where}.known_at"),
                _source(entry["source"], f"{where}.source"),
            )
        )
    exceptions = []
    for position, entry in enumerate(_tables(raw, "exceptions")):
        where = f"exceptions[{position}]"
        _check_keys(entry, _EXCEPTION_KEYS, where)
        exceptions.append(
            MemberCountException(
                _date(entry["effective_on"], f"{where}.effective_on"),
                _count(entry["expected_count"], f"{where}.expected_count"),
                _source(entry["source"], f"{where}.source"),
                _known_at(entry["known_at"], f"{where}.known_at"),
            )
        )
    changes.sort(key=lambda c: (c.effective_date, c.instrument_id.value))
    exceptions.sort(key=lambda e: e.effective_on)
    return MembershipHistory(
        index,
        version,
        coverage_start,
        coverage_end,
        seed_record,
        tuple(changes),
        tuple(exceptions),
    )
