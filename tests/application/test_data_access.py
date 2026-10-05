"""ADR-018 access modes: research, integrity, holdout evaluation, operational, future windows."""

import types
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from typing import Any, get_args, get_origin, get_type_hints

import pytest

from trading.application.data_access import (
    AccessDenied,
    AccessGrant,
    AccessMode,
    FailureLocation,
    HoldoutUse,
    IntegrityDataset,
    IntegrityReport,
    IntegrityRule,
    RuleCount,
    UsePurpose,
    Window,
    WindowKind,
    WindowRegistry,
    check_access,
)
from trading.domain.identity import InstrumentId
from trading.domain.timing import IST

W1 = Window("W1", date(2023, 1, 1), date(2026, 6, 30), WindowKind.HOLDOUT)
W2 = Window("W2", date(2026, 7, 1), None, WindowKind.FORWARD)
ONLY_W1 = WindowRegistry((W1,))
W1_AND_W2 = WindowRegistry((W1, W2))

RESEARCH_ERA = datetime(2022, 12, 30, 18, 0, tzinfo=IST)
IN_W1 = datetime(2024, 3, 15, 18, 0, tzinfo=IST)
AFTER_W1 = datetime(2026, 8, 3, 18, 0, tzinfo=IST)
W1_FIRST_INSTANT = datetime(2023, 1, 1, 0, 0, tzinfo=IST)
W1_LAST_INSTANT = datetime.combine(date(2026, 6, 30), time.max, tzinfo=IST)

GATE_A_USE = HoldoutUse("W1", "use-W1-C", "config-C", UsePurpose.GATE_A)
FORWARD_USE = HoldoutUse("W2", "use-W2-C", "config-C", UsePurpose.PAPER_FORWARD)


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 20, 0, tzinfo=IST)


def _research(as_of: datetime) -> AccessGrant:
    return AccessGrant(AccessMode.RESEARCH, as_of=as_of)


# --- A. Research -----------------------------------------------------------------------------


def test_research_reads_pre_window_information() -> None:
    check_access(ONLY_W1, _research(_at(2022, 12, 30)), RESEARCH_ERA)


def test_research_reads_an_announcement_made_before_the_window_taking_effect_inside() -> None:
    announced = datetime(2022, 12, 20, 17, 0, tzinfo=IST)  # e.g. ex-date in Jan 2023

    check_access(ONLY_W1, _research(_at(2022, 12, 30)), announced)


def test_research_cannot_query_as_of_inside_a_window() -> None:
    with pytest.raises(AccessDenied, match="research"):
        check_access(ONLY_W1, _research(_at(2023, 1, 2)), RESEARCH_ERA)


def test_research_cannot_read_information_known_after_as_of() -> None:
    with pytest.raises(AccessDenied, match="after as_of"):
        check_access(ONLY_W1, _research(datetime(2022, 12, 30, 12, 0, tzinfo=IST)), RESEARCH_ERA)


# --- Boundary instants -----------------------------------------------------------------------


def test_last_instant_before_the_window_is_research_era() -> None:
    just_before = datetime(2022, 12, 31, 23, 59, 59, 999999, tzinfo=IST)

    check_access(ONLY_W1, _research(just_before), just_before)


def test_first_instant_of_the_window_is_sealed_for_research() -> None:
    with pytest.raises(AccessDenied, match="research"):
        check_access(ONLY_W1, _research(W1_FIRST_INSTANT), RESEARCH_ERA)


def test_utc_instant_that_is_already_the_next_ist_day_is_sealed() -> None:
    # 2022-12-31T18:30Z is 2023-01-01T00:00 IST, the first instant of W1.
    with pytest.raises(AccessDenied, match="research"):
        check_access(ONLY_W1, _research(datetime(2022, 12, 31, 18, 30, tzinfo=UTC)), RESEARCH_ERA)


def test_last_instant_of_w1_belongs_to_w1_and_the_next_to_w2() -> None:
    gate_a = AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=W1_LAST_INSTANT, uses=(GATE_A_USE,))
    check_access(W1_AND_W2, gate_a, W1_LAST_INSTANT)

    first_of_w2 = datetime(2026, 7, 1, 0, 0, tzinfo=IST)
    late = AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=first_of_w2, uses=(GATE_A_USE,))
    with pytest.raises(AccessDenied, match="no covering use for window W2"):
        check_access(W1_AND_W2, late, first_of_w2)


def test_a_gap_between_windows_is_unregistered() -> None:
    registry = WindowRegistry((W1, Window("W3", date(2026, 9, 1), None, WindowKind.HOLDOUT)))
    grant = AccessGrant(
        AccessMode.HOLDOUT_EVALUATION,
        as_of=_at(2026, 7, 15),
        uses=(HoldoutUse("W3", "k", "c", UsePurpose.GATE_A),),
    )

    with pytest.raises(AccessDenied, match="unregistered"):
        check_access(registry, grant, RESEARCH_ERA)


# --- C. Holdout evaluation -------------------------------------------------------------------


def test_holdout_use_reads_its_window_up_to_as_of() -> None:
    grant = AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=_at(2025, 1, 1), uses=(GATE_A_USE,))

    check_access(ONLY_W1, grant, IN_W1)
    check_access(ONLY_W1, grant, RESEARCH_ERA)


def test_holdout_use_cannot_read_beyond_as_of() -> None:
    grant = AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=_at(2024, 1, 1), uses=(GATE_A_USE,))

    with pytest.raises(AccessDenied, match="after as_of"):
        check_access(ONLY_W1, grant, IN_W1)


def test_holdout_grant_requires_exactly_one_evaluation_use() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=_at(2025, 1, 1))
    with pytest.raises(ValueError, match="gate_a or ablation"):
        AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=_at(2026, 8, 3), uses=(FORWARD_USE,))


# --- C'. Operational (paper) -----------------------------------------------------------------


def test_paper_warm_up_reads_w1_under_the_existing_gate_a_use() -> None:
    grant = AccessGrant(
        AccessMode.OPERATIONAL, as_of=_at(2026, 8, 3), uses=(GATE_A_USE, FORWARD_USE)
    )

    check_access(W1_AND_W2, grant, IN_W1)
    check_access(W1_AND_W2, grant, AFTER_W1)


def test_paper_cannot_read_a_window_without_a_covering_use() -> None:
    grant = AccessGrant(AccessMode.OPERATIONAL, as_of=_at(2026, 8, 3), uses=(FORWARD_USE,))

    with pytest.raises(AccessDenied, match="no covering use for window W1"):
        check_access(W1_AND_W2, grant, IN_W1)


def test_operational_access_requires_a_paper_forward_use() -> None:
    with pytest.raises(ValueError, match="paper_forward"):
        AccessGrant(AccessMode.OPERATIONAL, as_of=_at(2024, 6, 1), uses=(GATE_A_USE,))


def test_operational_as_of_must_lie_in_the_forward_window() -> None:
    grant = AccessGrant(
        AccessMode.OPERATIONAL, as_of=_at(2024, 6, 1), uses=(GATE_A_USE, FORWARD_USE)
    )

    with pytest.raises(AccessDenied, match="paper_forward"):
        check_access(W1_AND_W2, grant, RESEARCH_ERA)


def test_paper_never_sees_information_known_after_its_simulated_time() -> None:
    grant = AccessGrant(
        AccessMode.OPERATIONAL, as_of=_at(2026, 8, 2), uses=(GATE_A_USE, FORWARD_USE)
    )

    with pytest.raises(AccessDenied, match="after as_of"):
        check_access(W1_AND_W2, grant, AFTER_W1)


def test_operational_uses_must_belong_to_one_configuration() -> None:
    with pytest.raises(ValueError, match="one configuration"):
        AccessGrant(
            AccessMode.OPERATIONAL,
            as_of=_at(2026, 8, 3),
            uses=(
                GATE_A_USE,
                HoldoutUse("W2", "use-W2-X", "config-OTHER", UsePurpose.PAPER_FORWARD),
            ),
        )


def test_operational_cannot_cover_a_window_with_an_ablation_use() -> None:
    with pytest.raises(ValueError, match="gate_a"):
        AccessGrant(
            AccessMode.OPERATIONAL,
            as_of=_at(2026, 8, 3),
            uses=(HoldoutUse("W1", "use-W1-C2", "config-C", UsePurpose.ABLATION), FORWARD_USE),
        )


# --- D. Unregistered future dates ------------------------------------------------------------


def test_dates_after_the_last_registered_window_are_unreadable() -> None:
    grant = AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=_at(2026, 8, 4), uses=(GATE_A_USE,))

    with pytest.raises(AccessDenied, match="unregistered"):
        check_access(ONLY_W1, grant, AFTER_W1)


def test_research_cannot_read_unregistered_future_dates() -> None:
    with pytest.raises(AccessDenied, match="unregistered"):
        check_access(ONLY_W1, _research(_at(2026, 8, 4)), AFTER_W1)


# --- B. Integrity ----------------------------------------------------------------------------


@pytest.mark.parametrize("known_at", [RESEARCH_ERA, IN_W1, AFTER_W1])
def test_integrity_grants_never_read_values_through_check_access(known_at: datetime) -> None:
    grant = AccessGrant(AccessMode.INTEGRITY, as_of=_at(2026, 10, 5))

    with pytest.raises(AccessDenied, match="integrity"):
        check_access(ONLY_W1, grant, known_at)


_REPORT_LEAF_TYPES: set[Any] = {int, date, InstrumentId, types.NoneType}


def _assert_value_free(hint: Any, path: str) -> None:
    origin = get_origin(hint)
    if origin in (tuple, types.UnionType):
        for argument in get_args(hint):
            if argument is not Ellipsis:
                _assert_value_free(argument, path)
    elif isinstance(hint, type) and issubclass(hint, Enum):
        return
    elif is_dataclass(hint) and hint is not InstrumentId:
        assert isinstance(hint, type)
        hints = get_type_hints(hint)
        for item in fields(hint):
            _assert_value_free(hints[item.name], f"{path}.{item.name}")
    else:
        assert hint in _REPORT_LEAF_TYPES, f"{path}: {hint} could carry a value"


def test_integrity_report_uses_only_closed_vocabularies_and_counts() -> None:
    _assert_value_free(IntegrityReport, "IntegrityReport")


def test_integrity_report_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValueError, match="failed"):
        RuleCount(IntegrityRule.OHLC_INCONSISTENT, checked=3, failed=4)


def test_integrity_report_can_be_built_from_the_closed_vocabularies() -> None:
    report = IntegrityReport(
        IntegrityDataset.BARS,
        (RuleCount(IntegrityRule.MISSING_OBSERVATION, checked=10, failed=1),),
        (FailureLocation(IntegrityRule.MISSING_OBSERVATION, date(2024, 3, 15), InstrumentId("I")),),
    )

    assert report.rule_counts[0].failed == 1


# --- Window registry -------------------------------------------------------------------------


def test_windows_must_not_overlap_or_go_backwards() -> None:
    with pytest.raises(ValueError, match="must start after"):
        WindowRegistry((W1, Window("W0", date(2026, 1, 1), date(2026, 12, 31), WindowKind.HOLDOUT)))


def test_only_the_last_window_may_be_open_ended() -> None:
    with pytest.raises(ValueError, match="open-ended"):
        WindowRegistry((Window("W1", date(2023, 1, 1), None, WindowKind.HOLDOUT), W2))


def test_unknown_window_in_a_use_is_denied() -> None:
    grant = AccessGrant(
        AccessMode.HOLDOUT_EVALUATION,
        as_of=_at(2025, 1, 1),
        uses=(HoldoutUse("W9", "k", "c", UsePurpose.GATE_A),),
    )

    with pytest.raises(AccessDenied, match="unknown window"):
        check_access(ONLY_W1, grant, IN_W1)


def test_naive_instants_are_rejected_by_the_registry() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ONLY_W1.locate(datetime(2024, 1, 1))


def test_blank_use_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        HoldoutUse("", "", "", UsePurpose.GATE_A)


# --- Window kinds (C3) -----------------------------------------------------------------------


def test_a_holdout_window_cannot_be_relabelled_as_paper_forward() -> None:
    relabelled = HoldoutUse("W1", "use-W1-C", "config-C", UsePurpose.PAPER_FORWARD)
    grant = AccessGrant(AccessMode.OPERATIONAL, as_of=_at(2024, 6, 1), uses=(relabelled,))

    with pytest.raises(AccessDenied, match="does not match window W1"):
        check_access(ONLY_W1, grant, IN_W1)


def test_a_gate_a_use_cannot_name_a_forward_window() -> None:
    misfiled = HoldoutUse("W2", "use-W2-C", "config-C", UsePurpose.GATE_A)
    grant = AccessGrant(AccessMode.HOLDOUT_EVALUATION, as_of=_at(2026, 8, 3), uses=(misfiled,))

    with pytest.raises(AccessDenied, match="does not match window W2"):
        check_access(W1_AND_W2, grant, AFTER_W1)


def test_operational_uses_share_a_configuration_but_not_a_ledger_use_key() -> None:
    assert GATE_A_USE.use_key != FORWARD_USE.use_key
    assert GATE_A_USE.config_key == FORWARD_USE.config_key
