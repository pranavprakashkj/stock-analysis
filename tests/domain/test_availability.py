"""ADR-019 §3: series changes and legitimate absence are typed; unexplained absence is a failure."""

from datetime import date, datetime

import pytest

from trading.domain.availability import Absence, AbsenceReason, Series, SeriesChange, SourceRef
from trading.domain.identity import InstrumentId
from trading.domain.timing import IST

INSTRUMENT = InstrumentId("INS-0001")
SOURCE = SourceRef("nse-circular:2019-07-15:surveillance")
PUBLISHED = datetime(2019, 8, 1, 18, 0, tzinfo=IST)
MOVE_TO_BE = SeriesChange(
    instrument_id=INSTRUMENT,
    effective_date=date(2019, 7, 22),
    from_series=Series("EQ"),
    to_series=Series("BE"),
    known_at=datetime(2019, 7, 15, 18, 0, tzinfo=IST),
    source=SOURCE,
)
SOURCED_REASONS = [AbsenceReason.SUSPENDED, AbsenceReason.DELISTED, AbsenceReason.NOT_YET_LISTED]


@pytest.mark.parametrize("reason", SOURCED_REASONS)
def test_sourced_legitimate_absence_is_legitimate(reason: AbsenceReason) -> None:
    absence = Absence(INSTRUMENT, date(2019, 8, 1), reason, PUBLISHED, source=SOURCE)

    assert absence.is_legitimate


def test_series_changed_absence_requires_the_linked_series_change() -> None:
    absence = Absence(
        INSTRUMENT,
        date(2019, 7, 22),
        AbsenceReason.SERIES_CHANGED,
        PUBLISHED,
        series_change=MOVE_TO_BE,
    )

    assert absence.is_legitimate
    with pytest.raises(ValueError, match="series change"):
        Absence(
            INSTRUMENT, date(2019, 7, 22), AbsenceReason.SERIES_CHANGED, PUBLISHED, source=SOURCE
        )


def test_series_changed_absence_cannot_predate_the_change() -> None:
    with pytest.raises(ValueError, match="before the series change"):
        Absence(
            INSTRUMENT,
            date(2019, 1, 1),
            AbsenceReason.SERIES_CHANGED,
            PUBLISHED,
            series_change=MOVE_TO_BE,
        )


def test_series_change_for_another_instrument_is_rejected() -> None:
    with pytest.raises(ValueError, match="instrument"):
        Absence(
            InstrumentId("INS-0002"),
            date(2019, 7, 22),
            AbsenceReason.SERIES_CHANGED,
            PUBLISHED,
            series_change=MOVE_TO_BE,
        )


def test_series_change_on_another_reason_is_rejected() -> None:
    with pytest.raises(ValueError, match="only accompany"):
        Absence(
            INSTRUMENT,
            date(2019, 7, 22),
            AbsenceReason.SUSPENDED,
            PUBLISHED,
            source=SOURCE,
            series_change=MOVE_TO_BE,
        )


@pytest.mark.parametrize("reason", SOURCED_REASONS)
def test_legitimate_reason_without_source_cannot_be_constructed(reason: AbsenceReason) -> None:
    with pytest.raises(ValueError, match="source"):
        Absence(INSTRUMENT, date(2019, 8, 1), reason, PUBLISHED)


@pytest.mark.parametrize("reason", SOURCED_REASONS)
def test_classify_downgrades_unsourced_legitimate_claims_to_missing(reason: AbsenceReason) -> None:
    absence = Absence.classify(INSTRUMENT, date(2019, 8, 1), reason, PUBLISHED)

    assert absence.reason is AbsenceReason.MISSING_OBSERVATION
    assert not absence.is_legitimate


def test_classify_keeps_a_series_change_with_its_evidence() -> None:
    absence = Absence.classify(
        INSTRUMENT,
        date(2019, 7, 22),
        AbsenceReason.SERIES_CHANGED,
        PUBLISHED,
        series_change=MOVE_TO_BE,
    )

    assert absence.reason is AbsenceReason.SERIES_CHANGED


def test_classify_downgrades_a_series_change_claim_without_the_event() -> None:
    absence = Absence.classify(
        INSTRUMENT, date(2019, 7, 22), AbsenceReason.SERIES_CHANGED, PUBLISHED, source=SOURCE
    )

    assert absence.reason is AbsenceReason.MISSING_OBSERVATION


def test_classify_keeps_sourced_legitimate_claims() -> None:
    absence = Absence.classify(
        INSTRUMENT, date(2019, 8, 1), AbsenceReason.SUSPENDED, PUBLISHED, source=SOURCE
    )

    assert absence.reason is AbsenceReason.SUSPENDED


@pytest.mark.parametrize(
    "reason", [AbsenceReason.DATA_UNAVAILABLE, AbsenceReason.MISSING_OBSERVATION]
)
def test_unavailable_and_missing_are_never_legitimate(reason: AbsenceReason) -> None:
    assert not Absence(INSTRUMENT, date(2019, 8, 1), reason, PUBLISHED).is_legitimate


def test_absence_requires_an_aware_knowledge_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Absence(
            INSTRUMENT, date(2019, 8, 1), AbsenceReason.MISSING_OBSERVATION, datetime(2019, 8, 1)
        )


def test_series_change_must_change_series() -> None:
    with pytest.raises(ValueError, match="differ"):
        SeriesChange(
            INSTRUMENT,
            date(2019, 7, 22),
            Series("EQ"),
            Series("EQ"),
            datetime(2019, 7, 15, 18, 0, tzinfo=IST),
            SOURCE,
        )


@pytest.mark.parametrize("bad", ["", "eq", "EQUITY", "E Q"])
def test_series_code_shape(bad: str) -> None:
    with pytest.raises(ValueError, match="series code"):
        Series(bad)


def test_series_change_announced_after_the_absence_is_rejected() -> None:
    later_announcement = SeriesChange(
        INSTRUMENT,
        date(2019, 7, 22),
        Series("EQ"),
        Series("BE"),
        datetime(2019, 9, 1, 18, 0, tzinfo=IST),
        SOURCE,
    )

    with pytest.raises(ValueError, match="not yet known"):
        Absence(
            INSTRUMENT,
            date(2019, 8, 1),
            AbsenceReason.SERIES_CHANGED,
            PUBLISHED,
            series_change=later_announcement,
        )
    downgraded = Absence.classify(
        INSTRUMENT,
        date(2019, 8, 1),
        AbsenceReason.SERIES_CHANGED,
        PUBLISHED,
        series_change=later_announcement,
    )
    assert downgraded.reason is AbsenceReason.MISSING_OBSERVATION
