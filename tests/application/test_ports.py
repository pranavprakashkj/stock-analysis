"""Task 1.6: the port contracts themselves (shapes, errors, no provider details, no bypasses)."""

import inspect
from collections.abc import Callable
from typing import Any

import pytest
from fakes.fake_market_data import FakeMarketData
from fakes.synthetic_market import dataset

from trading.application.ports import (
    KnowledgeUnavailableError,
    MarketDataError,
    MarketDataProvider,
    OutsideCoverageError,
    SnapshotId,
    SnapshotStore,
    UnknownInstrumentError,
    UnknownSnapshotError,
)

EXPECTED_PARAMETERS: dict[Callable[..., object], list[str]] = {
    MarketDataProvider.identity_map: ["self", "as_of"],
    MarketDataProvider.bars: ["self", "instrument_id", "start", "end", "as_of"],
    MarketDataProvider.absences: ["self", "instrument_id", "start", "end", "as_of"],
    MarketDataProvider.series_changes: ["self", "instrument_id", "as_of"],
    MarketDataProvider.corporate_actions: ["self", "instrument_id", "as_of"],
    MarketDataProvider.membership_changes: ["self", "index", "as_of"],
    SnapshotStore.write: ["self", "dataset"],
    SnapshotStore.read: ["self", "snapshot_id"],
}
QUERIES = (
    MarketDataProvider.identity_map,
    MarketDataProvider.bars,
    MarketDataProvider.absences,
    MarketDataProvider.series_changes,
    MarketDataProvider.corporate_actions,
    MarketDataProvider.membership_changes,
)


@pytest.mark.parametrize("method", list(EXPECTED_PARAMETERS), ids=lambda m: m.__qualname__)
def test_port_methods_take_exactly_the_specified_parameters(method: Callable[..., object]) -> None:
    """No hidden switches: no holdout bypass, no provider paths, tokens or pagination."""
    assert list(inspect.signature(method).parameters) == EXPECTED_PARAMETERS[method]


def test_ports_expose_only_the_specified_methods() -> None:
    def public(cls: type) -> set[str]:
        return {name for name in vars(cls) if not name.startswith("_")}

    assert public(MarketDataProvider) == {
        "identity_map",
        "bars",
        "absences",
        "series_changes",
        "corporate_actions",
        "membership_changes",
    }
    assert public(SnapshotStore) == {"write", "read"}


@pytest.mark.parametrize("method", QUERIES, ids=lambda m: m.__qualname__)
def test_every_query_requires_a_keyword_only_as_of(method: Callable[..., object]) -> None:
    as_of = inspect.signature(method).parameters["as_of"]

    assert as_of.kind is inspect.Parameter.KEYWORD_ONLY
    assert as_of.default is inspect.Parameter.empty


def test_fake_satisfies_the_port() -> None:
    provider: MarketDataProvider = FakeMarketData(dataset())  # checked structurally by mypy

    assert isinstance(provider, FakeMarketData)


def test_fake_accepts_only_a_market_dataset() -> None:
    untyped: Any = {"bars": ()}
    with pytest.raises(TypeError, match="dataset must be a MarketDataset"):
        FakeMarketData(untyped)


def test_market_data_errors_are_distinct() -> None:
    errors = (UnknownInstrumentError, OutsideCoverageError, KnowledgeUnavailableError)

    assert all(issubclass(error, MarketDataError) for error in errors)
    for error in errors:
        assert not any(issubclass(error, other) for other in errors if other is not error)
    assert not issubclass(UnknownSnapshotError, MarketDataError)


def test_snapshot_id_is_a_canonical_sha256_hex() -> None:
    digest = "6d74024b6fbff3bcc2fbf48c937bdc31a96cc755502325b831003245d39f190c"

    assert SnapshotId(digest).value == digest


@pytest.mark.parametrize(
    "bad",
    ["", "6D74" + "0" * 60, "0" * 63, "0" * 65, "g" * 64, " " + "0" * 63],
    ids=["empty", "uppercase", "short", "long", "non-hex", "space"],
)
def test_snapshot_id_rejects_anything_else(bad: str) -> None:
    with pytest.raises(ValueError, match="SnapshotId"):
        SnapshotId(bad)


def test_snapshot_id_rejects_non_strings() -> None:
    untyped: Any = 123
    with pytest.raises(TypeError, match="SnapshotId must be a str"):
        SnapshotId(untyped)
