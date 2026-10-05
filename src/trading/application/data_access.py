"""Data access modes over sealed windows (ADR-018).

`check_access` decides whether a record with a given knowledge time may be read under a grant.
It is pure policy. **Grants are unverified claims in Phase 1:** nothing yet checks that the uses a
grant names exist in the holdout ledger. From task 4.0, grants are issued only by the ledger after
the write-ahead use entry (ADR-017 §6, ADR-018 §7); until then this module must not be wired to
real data.

Integrity access never reads values through this function. Integrity checks run in a dedicated
runner whose only output is an `IntegrityReport` built from closed vocabularies (ADR-018 §6).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from itertools import pairwise

from trading.domain.identity import InstrumentId
from trading.domain.timing import IST, require_aware


class AccessMode(Enum):
    RESEARCH = "research"
    INTEGRITY = "integrity"
    HOLDOUT_EVALUATION = "holdout_evaluation"
    OPERATIONAL = "operational"


class UsePurpose(Enum):
    GATE_A = "gate_a"
    ABLATION = "ablation"
    PAPER_FORWARD = "paper_forward"


class WindowKind(Enum):
    HOLDOUT = "holdout"  # sealed evaluation window (e.g. W1)
    FORWARD = "forward"  # forward window consumed by paper trading (e.g. W2)


_KIND_FOR_PURPOSE = {
    UsePurpose.GATE_A: WindowKind.HOLDOUT,
    UsePurpose.ABLATION: WindowKind.HOLDOUT,
    UsePurpose.PAPER_FORWARD: WindowKind.FORWARD,
}


class AccessDenied(Exception):
    """The requested information is not readable under the grant."""


@dataclass(frozen=True, slots=True)
class Window:
    """A registered sealed date range in IST; `end=None` means open-ended."""

    window_id: str
    start: date
    end: date | None
    kind: WindowKind

    def __post_init__(self) -> None:
        if not self.window_id.strip():
            raise ValueError("window_id must be non-empty")
        if self.end is not None and self.end < self.start:
            raise ValueError(f"window {self.window_id} ends before it starts")

    @property
    def first_instant(self) -> datetime:
        return datetime.combine(self.start, time.min, tzinfo=IST)

    def contains(self, moment: datetime) -> bool:
        require_aware(moment)
        if moment < self.first_instant:
            return False
        return self.end is None or moment <= datetime.combine(self.end, time.max, tzinfo=IST)


class _Unregistered:
    """Marker: an instant after or between registered windows (sealed until a window covers it)."""


_UNREGISTERED = _Unregistered()


class WindowRegistry:
    """Windows in date order; each starts after the previous one ends; only the last may be open."""

    def __init__(self, windows: Sequence[Window]) -> None:
        if not windows:
            raise ValueError("at least one window must be registered")
        for earlier, later in pairwise(windows):
            if earlier.end is None:
                raise ValueError(f"only the last window may be open-ended: {earlier.window_id}")
            if later.start <= earlier.end:
                raise ValueError(f"window {later.window_id} must start after {earlier.window_id}")
        if len({window.window_id for window in windows}) != len(windows):
            raise ValueError("window ids must be unique")
        self._windows = tuple(windows)

    def ids(self) -> frozenset[str]:
        return frozenset(window.window_id for window in self._windows)

    def kind_of(self, window_id: str) -> WindowKind:
        return next(window.kind for window in self._windows if window.window_id == window_id)

    def locate(self, moment: datetime) -> Window | _Unregistered | None:
        """None = before the first window (research era); a Window; or unregistered (sealed)."""
        require_aware(moment)
        if moment < self._windows[0].first_instant:
            return None
        for window in self._windows:
            if window.contains(moment):
                return window
        return _UNREGISTERED


@dataclass(frozen=True, slots=True)
class HoldoutUse:
    """A use claimed by a grant on one window, for one purpose (ADR-018 §4).

    `config_key` identifies the configuration (strategy, code, costs, risk, criteria, seeds,
    reference versions). `use_key` identifies the ledger use; for a closed window it also
    covers the sealed snapshot hash, so the two keys differ even for the same configuration.
    """

    window_id: str
    use_key: str
    config_key: str
    purpose: UsePurpose

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.window_id, self.use_key, self.config_key)):
            raise ValueError("window_id, use_key and config_key must be non-empty")


_EVALUATION_PURPOSES = frozenset({UsePurpose.GATE_A, UsePurpose.ABLATION})


@dataclass(frozen=True, slots=True)
class AccessGrant:
    mode: AccessMode
    as_of: datetime
    uses: tuple[HoldoutUse, ...] = field(default=())

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        if self.mode in (AccessMode.RESEARCH, AccessMode.INTEGRITY) and self.uses:
            raise ValueError(f"{self.mode.value} access takes no holdout uses")
        if self.mode is AccessMode.HOLDOUT_EVALUATION:
            if len(self.uses) != 1:
                raise ValueError("holdout evaluation requires exactly one use")
            if self.uses[0].purpose not in _EVALUATION_PURPOSES:
                raise ValueError("holdout evaluation requires a gate_a or ablation use")
        if self.mode is AccessMode.OPERATIONAL:
            forward = [use for use in self.uses if use.purpose is UsePurpose.PAPER_FORWARD]
            if len(forward) != 1:
                raise ValueError("operational access requires exactly one paper_forward use")
            if any(use.purpose is UsePurpose.ABLATION for use in self.uses):
                raise ValueError(
                    "operational access may cover earlier windows only via gate_a uses"
                )
            if len({use.config_key for use in self.uses}) != 1:
                raise ValueError("operational uses must belong to one configuration")
            if len({use.window_id for use in self.uses}) != len(self.uses):
                raise ValueError("at most one use per window")


def check_access(registry: WindowRegistry, grant: AccessGrant, known_at: datetime) -> None:
    """Raise AccessDenied unless information known at `known_at` is readable under `grant`."""
    require_aware(known_at)
    if grant.mode is AccessMode.INTEGRITY:
        raise AccessDenied("integrity access never reads values; integrity runners emit reports")
    if known_at > grant.as_of:
        raise AccessDenied(f"information known at {known_at} is after as_of {grant.as_of}")

    as_of_location = registry.locate(grant.as_of)
    record_location = registry.locate(known_at)
    if isinstance(as_of_location, _Unregistered) or isinstance(record_location, _Unregistered):
        raise AccessDenied("unregistered dates are unreadable until a window covers them")

    if grant.mode is AccessMode.RESEARCH:
        if as_of_location is not None:
            raise AccessDenied("research queries must be before the first registered window")
        return

    unknown = {use.window_id for use in grant.uses} - registry.ids()
    if unknown:
        raise AccessDenied(f"unknown window in use: {sorted(unknown)}")
    for use in grant.uses:
        if registry.kind_of(use.window_id) is not _KIND_FOR_PURPOSE[use.purpose]:
            raise AccessDenied(f"{use.purpose.value} use does not match window {use.window_id}")
    if grant.mode is AccessMode.OPERATIONAL:
        forward = next(use for use in grant.uses if use.purpose is UsePurpose.PAPER_FORWARD)
        if as_of_location is None or as_of_location.window_id != forward.window_id:
            raise AccessDenied("operational as_of must lie in the paper_forward use's window")
    covered = {use.window_id for use in grant.uses}
    for location in (as_of_location, record_location):
        if location is not None and location.window_id not in covered:
            raise AccessDenied(f"no covering use for window {location.window_id}")


class IntegrityDataset(Enum):
    BARS = "bars"
    CORPORATE_ACTIONS = "corporate_actions"
    MEMBERSHIP = "membership"
    IDENTITY = "identity"
    ABSENCES = "absences"
    BENCHMARK = "benchmark"
    RISK_FREE_RATE = "risk_free_rate"
    CALENDAR = "calendar"


class IntegrityRule(Enum):
    """Closed set of integrity rules (task 1.10). Adding one is a reviewed code change, so a rule
    name can never be used to encode a value (e.g. a price threshold)."""

    MISSING_OBSERVATION = "missing_observation"
    UNSOURCED_ABSENCE = "unsourced_absence"
    COVERAGE_GAP = "coverage_gap"
    MISSING_SESSION = "missing_session"
    OHLC_INCONSISTENT = "ohlc_inconsistent"
    NON_POSITIVE_PRICE = "non_positive_price"
    DUPLICATE_RECORD = "duplicate_record"
    UNMAPPED_SYMBOL = "unmapped_symbol"
    UNPARSED_CORPORATE_ACTION = "unparsed_corporate_action"
    UNEXPLAINED_MOVE = "unexplained_move"
    RATIO_MISMATCH = "ratio_mismatch"


@dataclass(frozen=True, slots=True)
class RuleCount:
    rule: IntegrityRule
    checked: int
    failed: int

    def __post_init__(self) -> None:
        if not 0 <= self.failed <= self.checked:
            raise ValueError("failed must be between 0 and checked")


@dataclass(frozen=True, slots=True)
class FailureLocation:
    rule: IntegrityRule
    observation_date: date
    instrument_id: InstrumentId | None  # None for dataset-level failures (e.g. a missing session)


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """The only output of integrity access: counts and failure locations, never market values."""

    dataset: IntegrityDataset
    rule_counts: tuple[RuleCount, ...]
    failures: tuple[FailureLocation, ...]
