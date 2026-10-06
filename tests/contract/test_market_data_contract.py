"""Reusable MarketDataProvider contract (ADR-018 §1, ADR-019). Every provider must pass it.

Providers are built from a synthetic MarketDataset by a factory; add a factory to PROVIDERS to run
the same contract against a new adapter. Task 1.9 extends this suite.
"""

import dataclasses
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fakes.fake_market_data import FakeMarketData
from fakes.synthetic_market import (
    ABSENCES,
    BARS,
    BE,
    COVERAGE_END,
    COVERAGE_START,
    DELISTING_ANNOUNCED,
    EQ,
    IDENTITY,
    IDENTITY_ENDS,
    KNOWLEDGE_CUTOFF,
    MEMBERSHIP,
    REMOVAL_ANNOUNCED,
    RENAME_ANNOUNCED,
    SERIES_CHANGE_B,
    SPLIT_A,
    SPLIT_ANNOUNCED,
    UNRESOLVED_DIVIDEND_A,
    A,
    B,
    C,
    D,
    bar,
    dataset,
    day,
    published,
    source,
)

from trading.application.market_dataset import MarketDataset
from trading.application.ports import (
    KnowledgeUnavailableError,
    MarketDataProvider,
    OutsideCoverageError,
    UnknownInstrumentError,
)
from trading.domain.availability import AbsenceReason
from trading.domain.corporate_actions import CorporateActionKind
from trading.domain.identity import IdentityError, InstrumentId, Symbol
from trading.domain.market import Bar
from trading.domain.timing import IST, effective_on
from trading.domain.universe import IndexName

ProviderFactory = Callable[[MarketDataset], MarketDataProvider]
PROVIDERS: dict[str, ProviderFactory] = {"fake": FakeMarketData}
TICK = timedelta(microseconds=1)


@pytest.fixture(params=sorted(PROVIDERS))
def make_provider(request: pytest.FixtureRequest) -> ProviderFactory:
    return PROVIDERS[request.param]


@pytest.fixture
def provider(make_provider: ProviderFactory) -> MarketDataProvider:
    return make_provider(dataset())


def _bars(
    provider: MarketDataProvider, instrument: InstrumentId, as_of: datetime
) -> tuple[Bar, ...]:
    return provider.bars(instrument, COVERAGE_START, COVERAGE_END, as_of=as_of)


# --- identity ---------------------------------------------------------------------------------


def test_a_renamed_symbol_keeps_its_instrument_identity(provider: MarketDataProvider) -> None:
    identity = provider.identity_map(as_of=KNOWLEDGE_CUTOFF)

    assert identity.resolve(Symbol("AAA"), day(7)) == A
    assert identity.resolve(Symbol("AAB"), day(8)) == A
    assert identity.symbol_on(A, day(8)) == Symbol("AAB")


def test_bars_continue_under_one_instrument_across_the_rename(provider: MarketDataProvider) -> None:
    assert [b.observation_date for b in _bars(provider, A, KNOWLEDGE_CUTOFF)] == [
        day(2),
        day(3),
        day(7),
        day(8),
    ]


def test_identity_is_as_of_too(provider: MarketDataProvider) -> None:
    before = provider.identity_map(as_of=RENAME_ANNOUNCED - TICK)

    with pytest.raises(IdentityError, match="no instrument"):
        before.resolve(Symbol("AAB"), day(8))
    assert provider.identity_map(as_of=RENAME_ANNOUNCED).resolve(Symbol("AAB"), day(8)) == A


def test_queries_are_keyed_by_instrument_id_never_by_symbol(provider: MarketDataProvider) -> None:
    symbol: Any = Symbol("AAA")

    with pytest.raises(TypeError, match="instrument_id must be an InstrumentId"):
        provider.bars(symbol, day(2), day(3), as_of=KNOWLEDGE_CUTOFF)
    with pytest.raises(TypeError, match="instrument_id must be an InstrumentId"):
        provider.corporate_actions(symbol, as_of=KNOWLEDGE_CUTOFF)


def test_unknown_instrument_is_an_explicit_error(provider: MarketDataProvider) -> None:
    unknown = InstrumentId("INS-Z")

    with pytest.raises(UnknownInstrumentError, match="INS-Z"):
        provider.bars(unknown, day(2), day(3), as_of=KNOWLEDGE_CUTOFF)
    with pytest.raises(UnknownInstrumentError, match="INS-Z"):
        provider.absences(unknown, day(2), day(3), as_of=KNOWLEDGE_CUTOFF)
    with pytest.raises(UnknownInstrumentError, match="INS-Z"):
        provider.corporate_actions(unknown, as_of=KNOWLEDGE_CUTOFF)


# --- observation date vs knowledge time -------------------------------------------------------


def test_a_bar_is_invisible_until_its_knowledge_time(provider: MarketDataProvider) -> None:
    """The 7 Jan bar is published 18:00 IST on 7 Jan: its observation date alone grants nothing."""
    assert day(7) not in [b.observation_date for b in _bars(provider, A, published(7) - TICK)]
    assert day(7) in [b.observation_date for b in _bars(provider, A, published(7))]


def test_nothing_returned_is_known_after_as_of(provider: MarketDataProvider) -> None:
    for as_of in (published(3), published(7) + timedelta(hours=1), KNOWLEDGE_CUTOFF):
        for instrument in (A, B, C, D):
            assert all(b.known_at <= as_of for b in _bars(provider, instrument, as_of))
            absences = provider.absences(instrument, COVERAGE_START, COVERAGE_END, as_of=as_of)
            assert all(a.known_at <= as_of for a in absences)


def test_query_before_any_knowledge_is_empty_not_an_error(provider: MarketDataProvider) -> None:
    early = datetime(2029, 12, 15, tzinfo=IST)  # identity public, no data yet

    assert _bars(provider, A, early) == ()
    assert provider.corporate_actions(A, as_of=early) == ()


def test_as_of_after_the_knowledge_cutoff_is_refused(provider: MarketDataProvider) -> None:
    """Records known after the cut-off are not in the data, so a later as_of would look complete
    when it is not."""
    late = KNOWLEDGE_CUTOFF + TICK

    with pytest.raises(KnowledgeUnavailableError, match="after the knowledge cut-off"):
        _bars(provider, A, late)
    with pytest.raises(KnowledgeUnavailableError):
        provider.absences(A, day(2), day(3), as_of=late)
    with pytest.raises(KnowledgeUnavailableError):
        provider.corporate_actions(A, as_of=late)
    with pytest.raises(KnowledgeUnavailableError):
        provider.membership_changes(IndexName.NIFTY_100, as_of=late)
    with pytest.raises(KnowledgeUnavailableError):
        provider.identity_map(as_of=late)


@pytest.mark.parametrize(
    ("bad", "error"),
    [(datetime(2030, 1, 8, 18, 0), ValueError), (day(8), TypeError), ("2030-01-08", TypeError)],
    ids=["naive", "date", "str"],
)
def test_as_of_must_be_an_aware_datetime(
    provider: MarketDataProvider, bad: object, error: type[Exception]
) -> None:
    untyped: Any = bad
    with pytest.raises(error):
        provider.bars(A, day(2), day(3), as_of=untyped)


# --- corporate actions ------------------------------------------------------------------------


def test_known_action_is_visible_before_its_ex_date(provider: MarketDataProvider) -> None:
    assert provider.corporate_actions(A, as_of=SPLIT_ANNOUNCED) == (SPLIT_A,)
    assert provider.corporate_actions(A, as_of=SPLIT_ANNOUNCED - TICK) == ()
    assert SPLIT_A.ex_date > SPLIT_ANNOUNCED.date()


def test_unresolved_action_is_never_visible(provider: MarketDataProvider) -> None:
    """known_at=None is visible at no as_of and is never given a fallback time (ADR-018 §2)."""
    probes = [
        datetime(2029, 12, 15, tzinfo=IST),
        published(9),
        published(9) + TICK,
        KNOWLEDGE_CUTOFF,
    ]
    for as_of in probes:
        returned = provider.corporate_actions(A, as_of=as_of)
        assert UNRESOLVED_DIVIDEND_A not in returned
        assert all(action.known_at is not None for action in returned)


def test_actions_are_not_filtered_by_ex_date(provider: MarketDataProvider) -> None:
    """An action whose ex-date is still in the future at as_of is returned because it is known."""
    returned = provider.corporate_actions(A, as_of=KNOWLEDGE_CUTOFF)

    assert returned == (SPLIT_A,)
    assert all(action.ex_date > KNOWLEDGE_CUTOFF.date() for action in returned)


# --- series -----------------------------------------------------------------------------------


def test_bars_of_every_series_are_returned(provider: MarketDataProvider) -> None:
    returned = _bars(provider, B, KNOWLEDGE_CUTOFF)

    assert [(b.observation_date, b.series) for b in returned] == [
        (day(2), EQ),
        (day(3), EQ),
        (day(7), EQ),
        (day(8), BE),
    ]
    assert {b.instrument_id for b in returned} == {B}


def test_series_change_is_a_linked_legitimate_absence(provider: MarketDataProvider) -> None:
    (absence,) = provider.absences(B, day(8), day(8), as_of=KNOWLEDGE_CUTOFF)

    assert absence.reason is AbsenceReason.SERIES_CHANGED
    assert absence.series_change == SERIES_CHANGE_B
    assert absence.is_legitimate


# --- absence ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instrument", "n", "reason", "legitimate"),
    [
        (C, 9, AbsenceReason.SUSPENDED, True),
        (B, 8, AbsenceReason.SERIES_CHANGED, True),
        (C, 14, AbsenceReason.DELISTED, True),
        (D, 2, AbsenceReason.NOT_YET_LISTED, True),
        (C, 11, AbsenceReason.DATA_UNAVAILABLE, False),
        (C, 10, AbsenceReason.MISSING_OBSERVATION, False),
    ],
)
def test_each_absence_reason_is_returned_typed(
    provider: MarketDataProvider,
    instrument: InstrumentId,
    n: int,
    reason: AbsenceReason,
    legitimate: bool,
) -> None:
    (absence,) = provider.absences(instrument, day(n), day(n), as_of=KNOWLEDGE_CUTOFF)

    assert absence.reason is reason
    assert absence.is_legitimate is legitimate


def test_unsourced_legitimate_claim_is_returned_as_missing_data(
    provider: MarketDataProvider,
) -> None:
    """The fixture's 10 Jan record was an unsourced suspension claim; it must stay a failure."""
    (absence,) = provider.absences(C, day(10), day(10), as_of=KNOWLEDGE_CUTOFF)

    assert absence.reason is AbsenceReason.MISSING_OBSERVATION
    assert absence.source is None
    assert not absence.is_legitimate


def test_absence_is_invisible_until_known(provider: MarketDataProvider) -> None:
    assert provider.absences(C, day(9), day(9), as_of=published(9) - TICK) == ()
    assert len(provider.absences(C, day(9), day(9), as_of=published(9))) == 1


# --- membership -------------------------------------------------------------------------------


def test_membership_change_is_visible_from_announcement_not_effective_date(
    provider: MarketDataProvider,
) -> None:
    removal = MEMBERSHIP[1]

    assert removal not in provider.membership_changes(
        IndexName.NIFTY_100, as_of=REMOVAL_ANNOUNCED - TICK
    )
    assert removal in provider.membership_changes(IndexName.NIFTY_100, as_of=REMOVAL_ANNOUNCED)
    assert removal.effective_date > REMOVAL_ANNOUNCED.date()


# --- ranges and coverage ----------------------------------------------------------------------


def test_range_is_inclusive(provider: MarketDataProvider) -> None:
    returned = provider.bars(A, day(3), day(7), as_of=KNOWLEDGE_CUTOFF)

    assert [b.observation_date for b in returned] == [day(3), day(7)]


def test_reversed_range_is_rejected(provider: MarketDataProvider) -> None:
    with pytest.raises(ValueError, match="start 2030-01-07 is after end 2030-01-03"):
        provider.bars(A, day(7), day(3), as_of=KNOWLEDGE_CUTOFF)


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2030, 1, 1), day(3)), (day(3), date(2030, 1, 15))],
    ids=["before", "after"],
)
def test_range_outside_coverage_is_an_error_not_an_empty_answer(
    provider: MarketDataProvider, start: date, end: date
) -> None:
    with pytest.raises(OutsideCoverageError, match=r"outside coverage 2030-01-02\.\.2030-01-14"):
        provider.bars(A, start, end, as_of=KNOWLEDGE_CUTOFF)
    with pytest.raises(OutsideCoverageError):
        provider.absences(A, start, end, as_of=KNOWLEDGE_CUTOFF)


def test_range_dates_must_be_dates(provider: MarketDataProvider) -> None:
    untyped: Any = datetime(2030, 1, 3, tzinfo=IST)
    with pytest.raises(TypeError, match="start must be a date"):
        provider.bars(A, untyped, day(7), as_of=KNOWLEDGE_CUTOFF)


# --- determinism ------------------------------------------------------------------------------


def _answers(provider: MarketDataProvider) -> tuple[object, ...]:
    return (
        *(_bars(provider, i, KNOWLEDGE_CUTOFF) for i in (A, B, C, D)),
        *(
            provider.absences(i, COVERAGE_START, COVERAGE_END, as_of=KNOWLEDGE_CUTOFF)
            for i in (A, B, C, D)
        ),
        provider.corporate_actions(A, as_of=KNOWLEDGE_CUTOFF),
        provider.membership_changes(IndexName.NIFTY_100, as_of=KNOWLEDGE_CUTOFF),
        provider.identity_map(as_of=KNOWLEDGE_CUTOFF).symbol_on(A, day(8)),
    )


def test_same_query_gives_identical_results(provider: MarketDataProvider) -> None:
    assert _answers(provider) == _answers(provider)


def test_results_depend_on_content_not_on_record_order(make_provider: ProviderFactory) -> None:
    """Reversed record order (always different from the original for 2+ records)."""
    reordered = dataset(
        bars=BARS[::-1],
        absences=ABSENCES[::-1],
        membership=MEMBERSHIP[::-1],
        identity=IDENTITY[::-1],
    )

    assert _answers(make_provider(reordered)) == _answers(make_provider(dataset()))


def test_results_are_tuples_in_date_order(provider: MarketDataProvider) -> None:
    returned = _bars(provider, A, KNOWLEDGE_CUTOFF)

    assert isinstance(returned, tuple)
    assert [b.observation_date for b in returned] == sorted(b.observation_date for b in returned)


# --- review follow-ups ------------------------------------------------------------------------


def test_known_series_change_is_visible_before_it_takes_effect(
    provider: MarketDataProvider,
) -> None:
    """Visible from its own knowledge time (7 Jan 18:00), before the 8 Jan absence is published."""
    as_of = SERIES_CHANGE_B.known_at

    assert provider.series_changes(B, as_of=as_of) == (SERIES_CHANGE_B,)
    assert provider.absences(B, day(8), day(8), as_of=as_of) == ()
    assert provider.series_changes(B, as_of=as_of - TICK) == ()


def test_instrument_is_unknown_until_its_identity_is_known(provider: MarketDataProvider) -> None:
    """Before INS-D's listing is public, querying it is indistinguishable from an unknown id."""
    with pytest.raises(UnknownInstrumentError, match="INS-D"):
        provider.bars(D, day(2), day(3), as_of=published(2) - TICK)
    assert provider.bars(D, day(2), day(3), as_of=published(3))[0].observation_date == day(3)


def test_bars_of_two_series_on_one_day_are_ordered_by_series_code(
    make_provider: ProviderFactory,
) -> None:
    provider = make_provider(dataset(bars=(bar(A, EQ, 3), bar(A, BE, 3), *BARS[2:])))

    returned = provider.bars(A, day(3), day(3), as_of=KNOWLEDGE_CUTOFF)

    assert [b.series for b in returned] == [BE, EQ]


def test_effective_on_a_date_among_known_changes(provider: MarketDataProvider) -> None:
    """ADR-019 §2's second question: what takes effect on T, among what is known by as_of."""
    removal = MEMBERSHIP[1]
    known = provider.membership_changes(IndexName.NIFTY_100, as_of=REMOVAL_ANNOUNCED)

    assert effective_on(known, removal.effective_date, REMOVAL_ANNOUNCED) == [removal]
    assert effective_on(known, removal.effective_date, REMOVAL_ANNOUNCED - TICK) == []


def test_action_order_ignores_input_order_and_timezone_of_known_at(
    make_provider: ProviderFactory,
) -> None:
    first = dataclasses.replace(SPLIT_A, kind=CorporateActionKind.DIVIDEND, source=source("d1"))
    second = dataclasses.replace(
        first, source=source("d2"), known_at=SPLIT_ANNOUNCED.astimezone(UTC)
    )

    forward = make_provider(dataset(corporate_actions=(first, second)))
    backward = make_provider(dataset(corporate_actions=(second, first)))

    assert forward.corporate_actions(A, as_of=KNOWLEDGE_CUTOFF) == (first, second)
    assert backward.corporate_actions(A, as_of=KNOWLEDGE_CUTOFF) == (first, second)


# --- identity ends carry their own knowledge time ---------------------------------------------


def test_a_symbol_end_is_not_visible_before_it_is_known(provider: MarketDataProvider) -> None:
    """CCC ends on 13 Jan, but that is announced only on 10 Jan 18:00."""
    before = provider.identity_map(as_of=DELISTING_ANNOUNCED - TICK)

    assert before.resolve(Symbol("CCC"), day(14)) == C  # still open-ended as known then
    assert before.ends() == (IDENTITY_ENDS[0],)  # only the rename end, known on 3 Jan


def test_a_symbol_end_is_visible_from_its_knowledge_time(provider: MarketDataProvider) -> None:
    at = provider.identity_map(as_of=DELISTING_ANNOUNCED)

    assert at.resolve(Symbol("CCC"), day(13)) == C
    with pytest.raises(IdentityError, match="no instrument"):
        at.resolve(Symbol("CCC"), day(14))


def test_before_a_rename_is_known_the_old_symbol_is_open_ended(
    provider: MarketDataProvider,
) -> None:
    before = provider.identity_map(as_of=RENAME_ANNOUNCED - TICK)

    assert before.symbol_on(A, day(10)) == Symbol("AAA")
    assert provider.identity_map(as_of=RENAME_ANNOUNCED).symbol_on(A, day(10)) == Symbol("AAB")
