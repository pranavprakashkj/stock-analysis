"""ADR-018 §1 / ADR-019 §2: visibility depends on knowledge time, not on observation or ex-date."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from trading.domain.timing import IST, effective_on, end_of_date, is_known, known_by


@dataclass(frozen=True)
class Announcement:
    name: str
    known_at: datetime
    effective_date: date


ANNOUNCED_EARLY = Announcement("split", datetime(2022, 12, 20, 17, 0, tzinfo=IST), date(2023, 1, 5))
ANNOUNCED_LATE = Announcement("bonus", datetime(2023, 1, 6, 10, 0, tzinfo=IST), date(2023, 1, 5))
AS_OF = datetime(2022, 12, 30, 20, 0, tzinfo=IST)


def test_action_announced_before_as_of_is_known_even_though_ex_date_is_later() -> None:
    assert known_by((ANNOUNCED_EARLY, ANNOUNCED_LATE), AS_OF) == [ANNOUNCED_EARLY]


def test_effective_on_returns_only_known_events_effective_that_day() -> None:
    as_of_ex_date = datetime(2023, 1, 5, 20, 0, tzinfo=IST)

    assert effective_on((ANNOUNCED_EARLY, ANNOUNCED_LATE), date(2023, 1, 5), as_of_ex_date) == [
        ANNOUNCED_EARLY
    ]


def test_filtering_by_ex_date_alone_would_differ_from_knowledge_time() -> None:
    by_ex_date = [
        a for a in (ANNOUNCED_EARLY, ANNOUNCED_LATE) if a.effective_date <= date(2023, 1, 5)
    ]

    assert by_ex_date != known_by(
        (ANNOUNCED_EARLY, ANNOUNCED_LATE), datetime(2023, 1, 5, 20, 0, tzinfo=IST)
    )


def test_knowledge_exactly_at_as_of_is_visible() -> None:
    assert is_known(AS_OF, AS_OF)


def test_same_instant_in_different_zones_compares_equal() -> None:
    assert is_known(datetime(2022, 12, 30, 14, 30, tzinfo=UTC), AS_OF)


def test_date_only_knowledge_is_conservatively_end_of_that_date() -> None:
    known = end_of_date(date(2022, 12, 30))

    assert not is_known(known, AS_OF)
    assert is_known(known, datetime(2022, 12, 31, 0, 0, tzinfo=IST))


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        is_known(datetime(2022, 12, 30, 17, 0), AS_OF)
