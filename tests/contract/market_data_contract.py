"""Reusable MarketDataProvider contract suite (task 1.9; ADR-018 §1, ADR-019 §2-3).

Every `MarketDataProvider` must pass it: subclass `MarketDataProviderContract` in a `test_*.py`
module and supply a `make_provider` fixture (see test_fake_provider.py).

Fixture contract: `make_provider(dataset)` must build a provider that answers from exactly the
records of any valid `MarketDataset`, without loss or repair, including combinations a real source
would rarely produce (e.g. a symbol ended while later bars still exist). A file-backed provider
(task 1.15) therefore needs a dataset-to-files writer for its factory.

The port has no "effective on T" query: effective-on tests filter the provider's known records by
effective date, so they check that the second ADR-019 §2 question can be answered from the first.
Error assertions match exception types, instrument ids and dates, never an adapter's wording
(`IdentityError` text comes from the domain `IdentityMap` every provider returns).
"""

import dataclasses
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest
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
from trading.domain.availability import Absence, AbsenceReason, Series, SeriesChange
from trading.domain.corporate_actions import CorporateActionKind
from trading.domain.identity import (
    IdentityError,
    IdentityMap,
    IdentityMapEnd,
    IdentityMapEntry,
    InstrumentId,
    Symbol,
)
from trading.domain.market import Bar
from trading.domain.timing import IST, effective_on
from trading.domain.universe import IndexMembershipChange, IndexName, MembershipChange

ProviderFactory = Callable[[MarketDataset], MarketDataProvider]
TICK = timedelta(microseconds=1)


def _bars(
    provider: MarketDataProvider, instrument: InstrumentId, as_of: datetime
) -> tuple[Bar, ...]:
    return provider.bars(instrument, COVERAGE_START, COVERAGE_END, as_of=as_of)


# Probes are given in several zones: a provider must compare instants, not wall-clock readings.
ZONES = (IST, UTC, timezone(timedelta(hours=14)))
COVERAGE_DAYS = tuple(
    COVERAGE_START + timedelta(days=n) for n in range((COVERAGE_END - COVERAGE_START).days + 1)
)


def _known_at(record: Any) -> datetime:
    known_at: datetime = record.known_at
    return known_at


def _instruments(data: MarketDataset) -> list[InstrumentId]:
    return sorted({e.instrument_id for e in data.identity})


def _probe_instants(data: MarketDataset) -> list[datetime]:
    """Every knowledge time in the data and one tick before each, up to the cut-off, each
    expressed in every zone of `ZONES`."""
    times = {
        *(r.known_at for r in data.identity),
        *(r.known_at for r in data.identity_ends),
        *(r.known_at for r in data.bars),
        *(r.known_at for r in data.absences),
        *(r.known_at for r in data.series_changes),
        *(r.known_at for r in data.corporate_actions if r.known_at is not None),
        *(r.known_at for r in data.membership),
    }
    probes = sorted({t for known in times for t in (known - TICK, known)})
    return [t.astimezone(zone) for t in probes if t <= data.knowledge_cutoff for zone in ZONES]


def _resolution(identity: IdentityMap, data: MarketDataset) -> tuple[object, ...]:
    """How every symbol and every instrument of `data` resolves on every coverage day."""
    resolved: list[object] = []
    for symbol in sorted({e.symbol for e in data.identity}):
        for current in COVERAGE_DAYS:
            try:
                resolved.append((symbol, current, identity.resolve(symbol, current)))
            except IdentityError:
                resolved.append((symbol, current, None))
    for instrument in _instruments(data):
        for current in COVERAGE_DAYS:
            try:
                resolved.append((instrument, current, identity.symbol_on(instrument, current)))
            except IdentityError:
                resolved.append((instrument, current, None))
    return tuple(resolved)


def _answers(
    provider: MarketDataProvider,
    as_of: datetime = KNOWLEDGE_CUTOFF,
    data: MarketDataset | None = None,
) -> tuple[object, ...]:
    """Every query's answer at `as_of`, over the instruments and symbols of `data` (default: the
    synthetic dataset); an instrument not yet known answers "unknown"."""
    universe = dataset() if data is None else data
    identity = provider.identity_map(as_of=as_of)
    answers: list[object] = [
        provider.membership_changes(IndexName.NIFTY_100, as_of=as_of),
        identity.ends(),
        _resolution(identity, universe),
    ]
    for instrument in _instruments(universe):
        try:
            answers += [
                _bars(provider, instrument, as_of),
                provider.absences(instrument, COVERAGE_START, COVERAGE_END, as_of=as_of),
                provider.series_changes(instrument, as_of=as_of),
                provider.corporate_actions(instrument, as_of=as_of),
            ]
        except UnknownInstrumentError:
            answers.append(("unknown", instrument))
    return tuple(answers)


class MarketDataProviderContract:
    """Subclass as `Test<Provider>` and define a `make_provider` fixture returning a factory that
    builds the provider from a `MarketDataset`. Every test below then runs against it."""

    @pytest.fixture
    def provider(self, make_provider: ProviderFactory) -> MarketDataProvider:
        return make_provider(dataset())

    # --- identity ---------------------------------------------------------------------------------

    def test_a_renamed_symbol_keeps_its_instrument_identity(
        self, provider: MarketDataProvider
    ) -> None:
        identity = provider.identity_map(as_of=KNOWLEDGE_CUTOFF)

        assert identity.resolve(Symbol("AAA"), day(7)) == A
        assert identity.resolve(Symbol("AAB"), day(8)) == A
        assert identity.symbol_on(A, day(8)) == Symbol("AAB")

    def test_bars_continue_under_one_instrument_across_the_rename(
        self, provider: MarketDataProvider
    ) -> None:
        assert [b.observation_date for b in _bars(provider, A, KNOWLEDGE_CUTOFF)] == [
            day(2),
            day(3),
            day(7),
            day(8),
        ]

    def test_identity_is_as_of_too(self, provider: MarketDataProvider) -> None:
        before = provider.identity_map(as_of=RENAME_ANNOUNCED - TICK)

        with pytest.raises(IdentityError, match="no instrument"):
            before.resolve(Symbol("AAB"), day(8))
        assert provider.identity_map(as_of=RENAME_ANNOUNCED).resolve(Symbol("AAB"), day(8)) == A

    def test_queries_are_keyed_by_instrument_id_never_by_symbol(
        self, provider: MarketDataProvider
    ) -> None:
        symbol: Any = Symbol("AAA")

        with pytest.raises(TypeError):
            provider.bars(symbol, day(2), day(3), as_of=KNOWLEDGE_CUTOFF)
        with pytest.raises(TypeError):
            provider.corporate_actions(symbol, as_of=KNOWLEDGE_CUTOFF)

    def test_unknown_instrument_is_an_explicit_error(self, provider: MarketDataProvider) -> None:
        unknown = InstrumentId("INS-Z")

        with pytest.raises(UnknownInstrumentError, match="INS-Z"):
            provider.bars(unknown, day(2), day(3), as_of=KNOWLEDGE_CUTOFF)
        with pytest.raises(UnknownInstrumentError, match="INS-Z"):
            provider.absences(unknown, day(2), day(3), as_of=KNOWLEDGE_CUTOFF)
        with pytest.raises(UnknownInstrumentError, match="INS-Z"):
            provider.corporate_actions(unknown, as_of=KNOWLEDGE_CUTOFF)

    # --- observation date vs knowledge time -------------------------------------------------------

    def test_a_bar_is_invisible_until_its_knowledge_time(
        self, provider: MarketDataProvider
    ) -> None:
        """The 7 Jan bar is published 18:00 IST on 7 Jan; its observation date grants nothing."""
        assert day(7) not in [b.observation_date for b in _bars(provider, A, published(7) - TICK)]
        assert day(7) in [b.observation_date for b in _bars(provider, A, published(7))]

    def test_nothing_returned_is_known_after_as_of(self, provider: MarketDataProvider) -> None:
        for as_of in (published(3), published(7) + timedelta(hours=1), KNOWLEDGE_CUTOFF):
            for instrument in (A, B, C, D):
                assert all(b.known_at <= as_of for b in _bars(provider, instrument, as_of))
                absences = provider.absences(instrument, COVERAGE_START, COVERAGE_END, as_of=as_of)
                assert all(a.known_at <= as_of for a in absences)

    def test_query_before_any_knowledge_is_empty_not_an_error(
        self, provider: MarketDataProvider
    ) -> None:
        early = datetime(2029, 12, 15, tzinfo=IST)  # identity public, no data yet

        assert _bars(provider, A, early) == ()
        assert provider.corporate_actions(A, as_of=early) == ()

    def test_as_of_after_the_knowledge_cutoff_is_refused(
        self, provider: MarketDataProvider
    ) -> None:
        """Records known after the cut-off are not in the data, so a later as_of would look complete
        when it is not."""
        late = KNOWLEDGE_CUTOFF + TICK

        with pytest.raises(KnowledgeUnavailableError):
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
        self, provider: MarketDataProvider, bad: object, error: type[Exception]
    ) -> None:
        untyped: Any = bad
        with pytest.raises(error):
            provider.bars(A, day(2), day(3), as_of=untyped)

    # --- corporate actions ------------------------------------------------------------------------

    def test_known_action_is_visible_before_its_ex_date(self, provider: MarketDataProvider) -> None:
        assert provider.corporate_actions(A, as_of=SPLIT_ANNOUNCED) == (SPLIT_A,)
        assert provider.corporate_actions(A, as_of=SPLIT_ANNOUNCED - TICK) == ()
        assert SPLIT_A.ex_date > SPLIT_ANNOUNCED.date()

    def test_unresolved_action_is_never_visible(self, provider: MarketDataProvider) -> None:
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
            # Also not returned under a stamped (fallback) knowledge time.
            assert all(action.source != UNRESOLVED_DIVIDEND_A.source for action in returned)

    def test_actions_are_not_filtered_by_ex_date(self, provider: MarketDataProvider) -> None:
        """An action whose ex-date is still ahead at as_of is returned because it is known."""
        returned = provider.corporate_actions(A, as_of=KNOWLEDGE_CUTOFF)

        assert returned == (SPLIT_A,)
        assert all(action.ex_date > KNOWLEDGE_CUTOFF.date() for action in returned)

    # --- series -----------------------------------------------------------------------------------

    def test_bars_of_every_series_are_returned(self, provider: MarketDataProvider) -> None:
        returned = _bars(provider, B, KNOWLEDGE_CUTOFF)

        assert [(b.observation_date, b.series) for b in returned] == [
            (day(2), EQ),
            (day(3), EQ),
            (day(7), EQ),
            (day(8), BE),
        ]
        assert {b.instrument_id for b in returned} == {B}

    def test_series_change_is_a_linked_legitimate_absence(
        self, provider: MarketDataProvider
    ) -> None:
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
        self,
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
        self,
        provider: MarketDataProvider,
    ) -> None:
        """The fixture's 10 Jan record was an unsourced suspension claim; it must stay a failure."""
        (absence,) = provider.absences(C, day(10), day(10), as_of=KNOWLEDGE_CUTOFF)

        assert absence.reason is AbsenceReason.MISSING_OBSERVATION
        assert absence.source is None
        assert not absence.is_legitimate

    def test_absence_is_invisible_until_known(self, provider: MarketDataProvider) -> None:
        assert provider.absences(C, day(9), day(9), as_of=published(9) - TICK) == ()
        assert len(provider.absences(C, day(9), day(9), as_of=published(9))) == 1

    # --- membership -------------------------------------------------------------------------------

    def test_membership_change_is_visible_from_announcement_not_effective_date(
        self,
        provider: MarketDataProvider,
    ) -> None:
        removal = MEMBERSHIP[1]

        assert removal not in provider.membership_changes(
            IndexName.NIFTY_100, as_of=REMOVAL_ANNOUNCED - TICK
        )
        assert removal in provider.membership_changes(IndexName.NIFTY_100, as_of=REMOVAL_ANNOUNCED)
        assert removal.effective_date > REMOVAL_ANNOUNCED.date()

    # --- ranges and coverage ----------------------------------------------------------------------

    def test_range_is_inclusive(self, provider: MarketDataProvider) -> None:
        returned = provider.bars(A, day(3), day(7), as_of=KNOWLEDGE_CUTOFF)

        assert [b.observation_date for b in returned] == [day(3), day(7)]

    def test_reversed_range_is_rejected(self, provider: MarketDataProvider) -> None:
        with pytest.raises(ValueError, match=r"2030-01-07.*2030-01-03"):
            provider.bars(A, day(7), day(3), as_of=KNOWLEDGE_CUTOFF)

    @pytest.mark.parametrize(
        ("start", "end"),
        [(date(2030, 1, 1), day(3)), (day(3), date(2030, 1, 15))],
        ids=["before", "after"],
    )
    def test_range_outside_coverage_is_an_error_not_an_empty_answer(
        self, provider: MarketDataProvider, start: date, end: date
    ) -> None:
        with pytest.raises(OutsideCoverageError):
            provider.bars(A, start, end, as_of=KNOWLEDGE_CUTOFF)
        with pytest.raises(OutsideCoverageError):
            provider.absences(A, start, end, as_of=KNOWLEDGE_CUTOFF)

    def test_range_dates_must_be_dates(self, provider: MarketDataProvider) -> None:
        untyped: Any = datetime(2030, 1, 3, tzinfo=IST)
        with pytest.raises(TypeError):
            provider.bars(A, untyped, day(7), as_of=KNOWLEDGE_CUTOFF)

    # --- determinism ------------------------------------------------------------------------------

    def test_same_query_gives_identical_results(self, provider: MarketDataProvider) -> None:
        assert _answers(provider) == _answers(provider)

    def test_results_depend_on_content_not_on_record_order(
        self, make_provider: ProviderFactory
    ) -> None:
        """Reversed record order (always different from the original for 2+ records). The data
        includes a bar published days late (so knowledge order differs from date order) and a
        second series change for B (so series-change order is exercised)."""
        late_bar = dataclasses.replace(bar(A, EQ, 4), known_at=published(12))
        second_change = SeriesChange(B, day(12), BE, Series("BZ"), published(10), source("bz"))
        bars, changes = (*BARS, late_bar), (SERIES_CHANGE_B, second_change)
        forward = dataset(bars=bars, series_changes=changes)
        reordered = dataset(
            bars=bars[::-1],
            absences=ABSENCES[::-1],
            series_changes=changes[::-1],
            membership=MEMBERSHIP[::-1],
            identity=IDENTITY[::-1],
            identity_ends=IDENTITY_ENDS[::-1],
            corporate_actions=(UNRESOLVED_DIVIDEND_A, SPLIT_A),
        )

        assert _answers(make_provider(reordered)) == _answers(make_provider(forward))
        returned = make_provider(forward).bars(A, day(2), day(8), as_of=KNOWLEDGE_CUTOFF)
        assert [b.observation_date for b in returned] == [day(n) for n in (2, 3, 4, 7, 8)]
        assert make_provider(forward).series_changes(B, as_of=KNOWLEDGE_CUTOFF) == changes

    def test_results_are_tuples_in_date_order(self, provider: MarketDataProvider) -> None:
        returned = _bars(provider, A, KNOWLEDGE_CUTOFF)

        assert isinstance(returned, tuple)
        assert [b.observation_date for b in returned] == sorted(
            b.observation_date for b in returned
        )

    # --- review follow-ups ------------------------------------------------------------------------

    def test_known_series_change_is_visible_before_it_takes_effect(
        self,
        provider: MarketDataProvider,
    ) -> None:
        """Visible from its own knowledge time (7 Jan 18:00), before the 8 Jan absence."""
        as_of = SERIES_CHANGE_B.known_at

        assert provider.series_changes(B, as_of=as_of) == (SERIES_CHANGE_B,)
        assert provider.absences(B, day(8), day(8), as_of=as_of) == ()
        assert provider.series_changes(B, as_of=as_of - TICK) == ()

    def test_instrument_is_unknown_until_its_identity_is_known(
        self, provider: MarketDataProvider
    ) -> None:
        """Before INS-D's listing is public, querying it is indistinguishable from an unknown id."""
        with pytest.raises(UnknownInstrumentError, match="INS-D"):
            provider.bars(D, day(2), day(3), as_of=published(2) - TICK)
        assert provider.bars(D, day(2), day(3), as_of=published(3))[0].observation_date == day(3)

    def test_bars_of_two_series_on_one_day_are_ordered_by_series_code(
        self,
        make_provider: ProviderFactory,
    ) -> None:
        provider = make_provider(dataset(bars=(bar(A, EQ, 3), bar(A, BE, 3), *BARS[2:])))

        returned = provider.bars(A, day(3), day(3), as_of=KNOWLEDGE_CUTOFF)

        assert [b.series for b in returned] == [BE, EQ]

    def test_effective_on_a_date_among_known_changes(self, provider: MarketDataProvider) -> None:
        """ADR-019 §2's second question: what takes effect on T, among what is known by as_of."""
        removal = MEMBERSHIP[1]
        known = provider.membership_changes(IndexName.NIFTY_100, as_of=REMOVAL_ANNOUNCED)

        assert effective_on(known, removal.effective_date, REMOVAL_ANNOUNCED) == [removal]
        assert effective_on(known, removal.effective_date, REMOVAL_ANNOUNCED - TICK) == []

    def test_action_order_ignores_input_order_and_timezone_of_known_at(
        self,
        make_provider: ProviderFactory,
    ) -> None:
        first = dataclasses.replace(SPLIT_A, kind=CorporateActionKind.DIVIDEND, source=source("d1"))
        second = dataclasses.replace(
            first, source=source("d2"), known_at=SPLIT_ANNOUNCED.astimezone(UTC)
        )

        forward = make_provider(dataset(corporate_actions=(first, second)))
        backward = make_provider(dataset(corporate_actions=(second, first)))

        # The port fixes "ex-date, then content", not a particular content tie-break, so the
        # contract requires one order independent of input, not the fake's order.
        forward_result = forward.corporate_actions(A, as_of=KNOWLEDGE_CUTOFF)
        assert forward_result == backward.corporate_actions(A, as_of=KNOWLEDGE_CUTOFF)
        assert Counter(forward_result) == Counter((first, second))

    # --- identity ends carry their own knowledge time ---------------------------------------------

    def test_a_symbol_end_is_not_visible_before_it_is_known(
        self, provider: MarketDataProvider
    ) -> None:
        """CCC ends on 13 Jan, but that is announced only on 10 Jan 18:00."""
        before = provider.identity_map(as_of=DELISTING_ANNOUNCED - TICK)

        assert before.resolve(Symbol("CCC"), day(14)) == C  # still open-ended as known then
        assert before.ends() == (IDENTITY_ENDS[0],)  # only the rename end, known on 3 Jan

    def test_a_symbol_end_is_visible_from_its_knowledge_time(
        self, provider: MarketDataProvider
    ) -> None:
        at = provider.identity_map(as_of=DELISTING_ANNOUNCED)

        assert at.resolve(Symbol("CCC"), day(13)) == C
        with pytest.raises(IdentityError, match="no instrument"):
            at.resolve(Symbol("CCC"), day(14))

    def test_before_a_rename_is_known_the_old_symbol_is_open_ended(
        self,
        provider: MarketDataProvider,
    ) -> None:
        before = provider.identity_map(as_of=RENAME_ANNOUNCED - TICK)

        assert before.symbol_on(A, day(10)) == Symbol("AAA")
        assert provider.identity_map(as_of=RENAME_ANNOUNCED).symbol_on(A, day(10)) == Symbol("AAB")

    # --- task 1.9: exhaustive knowledge-time and look-ahead guarantees ------------------------

    def test_every_answer_is_exactly_what_was_known(self, provider: MarketDataProvider) -> None:
        """At every knowledge instant in the data (and one tick before it), each query returns
        precisely the records known by then: nothing later, nothing omitted, nothing twice."""
        data = dataset()
        for as_of in _probe_instants(data):
            identity_known = {e.instrument_id for e in data.identity if e.known_at <= as_of}
            for instrument in _instruments(data):
                if instrument not in identity_known:  # no query may reveal a future listing
                    with pytest.raises(UnknownInstrumentError):
                        _bars(provider, instrument, as_of)
                    with pytest.raises(UnknownInstrumentError):
                        provider.absences(instrument, COVERAGE_START, COVERAGE_END, as_of=as_of)
                    with pytest.raises(UnknownInstrumentError):
                        provider.series_changes(instrument, as_of=as_of)
                    with pytest.raises(UnknownInstrumentError):
                        provider.corporate_actions(instrument, as_of=as_of)
                    continue
                expected: dict[str, list[object]] = {
                    "bars": [r for r in data.bars if r.instrument_id == instrument],
                    "absences": [r for r in data.absences if r.instrument_id == instrument],
                    "series": [r for r in data.series_changes if r.instrument_id == instrument],
                    "actions": [
                        r
                        for r in data.corporate_actions
                        if r.instrument_id == instrument and r.known_at is not None
                    ],
                }
                actual: dict[str, tuple[Any, ...]] = {
                    "bars": _bars(provider, instrument, as_of),
                    "absences": provider.absences(
                        instrument, COVERAGE_START, COVERAGE_END, as_of=as_of
                    ),
                    "series": provider.series_changes(instrument, as_of=as_of),
                    "actions": provider.corporate_actions(instrument, as_of=as_of),
                }
                for kind, records in expected.items():
                    known = [r for r in records if _known_at(r) <= as_of]
                    # Multisets compared by ==, so equal values in another form (e.g. a UTC
                    # known_at) are accepted and duplicates are not.
                    assert Counter(actual[kind]) == Counter(known), (kind, instrument, as_of)
            membership = provider.membership_changes(IndexName.NIFTY_100, as_of=as_of)
            assert Counter(membership) == Counter(m for m in data.membership if m.known_at <= as_of)
            identity = provider.identity_map(as_of=as_of)
            known_entries = [e for e in data.identity if e.known_at <= as_of]
            known_ends = [e for e in data.identity_ends if e.known_at <= as_of]
            assert Counter(identity.ends()) == Counter(known_ends)
            # The oracle filters by knowledge time here, independently of `as_known_at`, which a
            # provider may use: a fault there must not make expected and actual agree.
            oracle = IdentityMap(known_entries, known_ends)
            assert _resolution(identity, data) == _resolution(oracle, data), as_of

    def test_records_known_later_cannot_change_an_earlier_answer(
        self, make_provider: ProviderFactory
    ) -> None:
        """Look-ahead guarantee: adding records of every kind that become known after as_of —
        including ones whose observation or effective date is before as_of — changes no answer
        at as_of."""
        as_of = published(7)
        later = published(12)
        newcomer = InstrumentId("INS-E")
        perturbed = dataset(
            identity=(*IDENTITY, IdentityMapEntry(newcomer, Symbol("EEE"), day(2), later)),
            identity_ends=(
                *IDENTITY_ENDS,
                IdentityMapEnd(B, Symbol("BBB"), date(2029, 12, 1), day(6), later),
            ),
            bars=(*BARS, dataclasses.replace(bar(A, BE, 3), known_at=later)),
            absences=(*ABSENCES, Absence(A, day(4), AbsenceReason.DATA_UNAVAILABLE, later)),
            series_changes=(
                SERIES_CHANGE_B,
                SeriesChange(A, day(5), EQ, BE, later, source("late-series")),
            ),
            corporate_actions=(
                SPLIT_A,
                UNRESOLVED_DIVIDEND_A,
                dataclasses.replace(
                    SPLIT_A,
                    kind=CorporateActionKind.BONUS,
                    ex_date=day(4),
                    announcement_date=day(12),
                    known_at=later,
                    source=source("late-bonus"),
                ),
            ),
            membership=(
                *MEMBERSHIP,
                IndexMembershipChange(
                    IndexName.NIFTY_100, B, MembershipChange.ADDED, day(5), later, source("late")
                ),
            ),
        )
        base, changed = make_provider(dataset()), make_provider(perturbed)

        assert _answers(changed, as_of, perturbed) == _answers(base, as_of, perturbed)
        with pytest.raises(UnknownInstrumentError):
            changed.bars(newcomer, day(2), day(3), as_of=as_of)

        # The added records are real: each is visible once known.
        identity_later = changed.identity_map(as_of=later)
        assert identity_later.resolve(Symbol("EEE"), day(2)) == newcomer
        with pytest.raises(IdentityError):
            identity_later.resolve(Symbol("BBB"), day(7))
        assert perturbed.bars[-1] in changed.bars(A, day(3), day(3), as_of=later)
        assert perturbed.absences[-1] in changed.absences(A, day(4), day(4), as_of=later)
        assert perturbed.series_changes[-1] in changed.series_changes(A, as_of=later)
        assert perturbed.corporate_actions[-1] in changed.corporate_actions(A, as_of=later)
        assert perturbed.membership[-1] in changed.membership_changes(
            IndexName.NIFTY_100, as_of=later
        )

    def test_action_effective_on_a_date_among_known_actions(
        self, make_provider: ProviderFactory
    ) -> None:
        """ADR-019 §2, second question, for corporate actions: of two actions with ex-date 9 Jan,
        only the one known by as_of takes effect on 9 Jan as seen at as_of."""
        known = dataclasses.replace(
            SPLIT_A, ex_date=day(9), announcement_date=day(8), known_at=published(8)
        )
        late = dataclasses.replace(
            known,
            kind=CorporateActionKind.DIVIDEND,
            announcement_date=day(12),
            known_at=published(12),
            source=source("late-dividend"),
        )
        provider = make_provider(dataset(corporate_actions=(known, late)))

        def effective_on_9th(as_of: datetime) -> tuple[object, ...]:
            visible = provider.corporate_actions(A, as_of=as_of)
            return tuple(action for action in visible if action.effective_date == day(9))

        assert effective_on_9th(published(8) - TICK) == ()
        assert effective_on_9th(published(10)) == (known,)
        assert set(effective_on_9th(published(12))) == {known, late}

    def test_membership_announced_after_it_took_effect_is_invisible_until_announced(
        self, make_provider: ProviderFactory
    ) -> None:
        late_addition = IndexMembershipChange(
            IndexName.NIFTY_100, B, MembershipChange.ADDED, day(5), published(9), source("late")
        )
        provider = make_provider(dataset(membership=(*MEMBERSHIP, late_addition)))

        after_effect = provider.membership_changes(IndexName.NIFTY_100, as_of=published(8))
        assert late_addition not in after_effect
        assert effective_on(after_effect, day(5), published(8)) == []
        announced = provider.membership_changes(IndexName.NIFTY_100, as_of=published(9))
        assert effective_on(announced, day(5), published(9)) == [late_addition]

    def test_series_changes_follow_the_instrument_and_cutoff_rules(
        self, provider: MarketDataProvider
    ) -> None:
        with pytest.raises(UnknownInstrumentError, match="INS-Z"):
            provider.series_changes(InstrumentId("INS-Z"), as_of=KNOWLEDGE_CUTOFF)
        with pytest.raises(KnowledgeUnavailableError):
            provider.series_changes(B, as_of=KNOWLEDGE_CUTOFF + TICK)
        symbol: Any = Symbol("BBB")
        with pytest.raises(TypeError):
            provider.series_changes(symbol, as_of=KNOWLEDGE_CUTOFF)
