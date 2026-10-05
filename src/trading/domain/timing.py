"""Information timing (ADR-018 §1, ADR-019 §2).

A record is visible at `as_of` only if its knowledge time is at or before `as_of`. Observation and
effective dates never decide visibility on their own.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol

# IST is a fixed UTC+05:30 offset with no daylight saving, so no tz database is needed.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


class HasKnowledgeTime(Protocol):
    @property
    def known_at(self) -> datetime: ...


class HasKnowledgeAndEffectiveDate(HasKnowledgeTime, Protocol):
    @property
    def effective_date(self) -> date: ...


def require_aware(moment: datetime) -> datetime:
    if not isinstance(moment, datetime):
        raise TypeError(f"knowledge time must be a datetime, not {type(moment).__name__}")
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"datetime must be timezone-aware: {moment!r}")
    return moment


def start_of_date(day: date) -> datetime:
    """The first instant of `day` in IST, the trading calendar's timezone."""
    return datetime.combine(day, time.min, tzinfo=IST)


def end_of_date(day: date) -> datetime:
    """Knowledge time for information dated `day` without a time: the last instant of that day."""
    return datetime.combine(day, time.max, tzinfo=IST)


def is_known(known_at: datetime, as_of: datetime) -> bool:
    return require_aware(known_at) <= require_aware(as_of)


def known_by[KnownT: HasKnowledgeTime](records: Iterable[KnownT], as_of: datetime) -> list[KnownT]:
    """Records available at `as_of`, whatever their observation or effective date."""
    return [record for record in records if is_known(record.known_at, as_of)]


def effective_on[EffectiveT: HasKnowledgeAndEffectiveDate](
    records: Iterable[EffectiveT], day: date, as_of: datetime
) -> list[EffectiveT]:
    """Records known at `as_of` that take effect on `day`."""
    return [record for record in known_by(records, as_of) if record.effective_date == day]
