"""Trading calendar: session arithmetic over an explicit, versioned session list (task 1.5).

- The calendar knows only the sessions it is given. No weekday rule, holiday list or special-session
  rule is built in; the reference list (reference/calendar/format.md) states every session.
- Every query must lie within the coverage range. Outside it the answer is unknown, so the query
  raises `OutsideCalendarError` instead of guessing. The same applies when the previous or next
  session would lie outside the coverage range.
- Dates are session dates (ADR-018 §1 observation dates). The calendar never uses the clock, and
  "today" is not special.
- No knowledge-time filtering here. ADR-018 §2 seals calendar overrides by knowledge time, and the
  knowledge time of calendar entries is unresolved (reference/calendar/format.md); it belongs to the
  provider and snapshot tasks. The calendar holds no global state.
- Catch `OutsideCalendarError` and `NotASessionError` separately, never the `CalendarError` base:
  "outside coverage" means unknown, not closed.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date
from enum import Enum
from itertools import pairwise

from trading.domain.checks import require_date, require_instance


class CalendarError(Exception):
    """A calendar question has no answer, e.g. the kind of a date that is not a session."""


class OutsideCalendarError(CalendarError):
    """The answer depends on dates outside the calendar's coverage range: it is unknown.

    Never catch `CalendarError` to mean "closed": that would turn "unknown" into "no session".
    """


class NotASessionError(CalendarError):
    """The date is covered but is not a session, so it has no session kind."""


class SessionKind(Enum):
    REGULAR = "regular"
    SPECIAL = "special"  # a session the reference list marks as special, e.g. on a weekend


@dataclass(frozen=True, slots=True)
class Session:
    day: date
    kind: SessionKind

    def __post_init__(self) -> None:
        require_date("day", self.day)
        require_instance("kind", self.kind, SessionKind)


def _session_day(session: Session) -> date:
    return session.day


@dataclass(frozen=True, slots=True)
class TradingCalendar:
    """Sessions of one calendar version, strictly increasing, within [coverage_start, coverage_end].

    Days inside the coverage range that are not listed are known non-sessions.
    """

    version: str
    coverage_start: date
    coverage_end: date
    sessions: tuple[Session, ...]

    def __post_init__(self) -> None:
        version = require_instance("version", self.version, str)
        if not version or not version.isprintable() or any(c.isspace() for c in version):
            raise ValueError(
                f"version must be non-empty printable text without whitespace: {version!r}"
            )
        require_date("coverage_start", self.coverage_start)
        require_date("coverage_end", self.coverage_end)
        if self.coverage_end < self.coverage_start:
            raise ValueError(
                f"coverage_end {self.coverage_end} is before coverage_start {self.coverage_start}"
            )
        sessions = require_instance("sessions", self.sessions, tuple)
        if not sessions:
            raise ValueError("a calendar needs at least one session")
        for index, session in enumerate(sessions):
            require_instance(f"sessions[{index}]", session, Session)
        for earlier, later in pairwise(sessions):
            if later.day == earlier.day:
                raise ValueError(f"duplicate session {later.day}")
            if later.day < earlier.day:
                raise ValueError(
                    f"sessions must be in increasing date order: {later.day} after {earlier.day}"
                )
        first, last = sessions[0].day, sessions[-1].day
        if first < self.coverage_start or last > self.coverage_end:
            raise ValueError(
                f"sessions {first}..{last} lie outside coverage "
                f"{self.coverage_start}..{self.coverage_end}"
            )

    @property
    def first_session(self) -> date:
        return self.sessions[0].day

    @property
    def last_session(self) -> date:
        return self.sessions[-1].day

    def _check_covered(self, name: str, day: object) -> date:
        checked = require_date(name, day)
        if not self.coverage_start <= checked <= self.coverage_end:
            raise OutsideCalendarError(
                f"{checked} is outside calendar {self.version} "
                f"({self.coverage_start}..{self.coverage_end})"
            )
        return checked

    def _index(self, day: date) -> int:
        """Position of the first session on or after `day`."""
        return bisect_left(self.sessions, day, key=_session_day)

    def _find(self, day: date) -> Session | None:
        index = self._index(day)
        if index < len(self.sessions) and self.sessions[index].day == day:
            return self.sessions[index]
        return None

    def is_session(self, day: date) -> bool:
        return self._find(self._check_covered("day", day)) is not None

    def kind_of(self, day: date) -> SessionKind:
        day = self._check_covered("day", day)
        session = self._find(day)
        if session is None:
            raise NotASessionError(f"{day} is not a session in calendar {self.version}")
        return session.kind

    def next_session(self, day: date) -> date:
        """The first session strictly after `day`, which need not itself be a session."""
        day = self._check_covered("day", day)
        index = bisect_right(self.sessions, day, key=_session_day)
        if index == len(self.sessions):
            raise OutsideCalendarError(
                f"no session after {day} within calendar {self.version} (ends {self.coverage_end})"
            )
        return self.sessions[index].day

    def previous_session(self, day: date) -> date:
        """The last session strictly before `day`, which need not itself be a session."""
        day = self._check_covered("day", day)
        index = self._index(day)
        if index == 0:
            raise OutsideCalendarError(
                f"no session before {day} within calendar {self.version} "
                f"(starts {self.coverage_start})"
            )
        return self.sessions[index - 1].day

    def sessions_between(self, start: date, end: date) -> tuple[date, ...]:
        """Session dates from `start` to `end`, both inclusive, in order. Empty if none."""
        start = self._check_covered("start", start)
        end = self._check_covered("end", end)
        if start > end:
            raise ValueError(f"start {start} is after end {end}")
        low = self._index(start)
        high = bisect_right(self.sessions, end, key=_session_day)
        return tuple(session.day for session in self.sessions[low:high])
