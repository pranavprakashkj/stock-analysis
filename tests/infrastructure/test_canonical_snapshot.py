"""ADR-020: snapshot identity is a SHA-256 over canonical logical content, not serialised bytes.

A real Parquet round-trip test (write -> read -> same id) belongs to Task 1.11, with Polars.
Here, representation independence is proven on the logical inputs the hash is computed from.
"""

import inspect
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from trading.domain.timing import IST
from trading.infrastructure.storage.canonical import (
    CANONICAL_VERSION,
    Column,
    ColumnType,
    SourceFileRecord,
    manifest_hash,
    snapshot_id,
)

SCHEMA = (
    Column("instrument_id", ColumnType.STRING),
    Column("session", ColumnType.DATE),
    Column("close", ColumnType.DECIMAL, scale=2),
    Column("volume", ColumnType.INT64),
    Column("known_at", ColumnType.TIMESTAMP_UTC),
    Column("is_eq", ColumnType.BOOL),
)
PUBLISHED = datetime(2022, 12, 30, 18, 0, tzinfo=IST)
ROWS: tuple[dict[str, object], ...] = (
    {
        "instrument_id": "INS-0001",
        "session": date(2022, 12, 30),
        "close": Decimal("101.50"),
        "volume": 1200,
        "known_at": PUBLISHED,
        "is_eq": True,
    },
    {
        "instrument_id": "INS-0002",
        "session": date(2022, 12, 30),
        "close": Decimal("55.05"),
        "volume": 900,
        "known_at": PUBLISHED,
        "is_eq": False,
    },
)


def _with(row_index: int, **changes: object) -> tuple[dict[str, object], ...]:
    rows = [dict(row) for row in ROWS]
    rows[row_index].update(changes)
    return tuple(rows)


def test_same_logical_content_gives_the_same_id() -> None:
    assert snapshot_id(SCHEMA, ROWS) == snapshot_id(SCHEMA, tuple(dict(row) for row in ROWS))


def test_row_order_does_not_change_the_id() -> None:
    assert snapshot_id(SCHEMA, ROWS) == snapshot_id(SCHEMA, tuple(reversed(ROWS)))


def test_column_order_does_not_change_the_id() -> None:
    reordered_rows = tuple(dict(reversed(list(row.items()))) for row in ROWS)

    assert snapshot_id(tuple(reversed(SCHEMA)), reordered_rows) == snapshot_id(SCHEMA, ROWS)


def test_equivalent_representations_of_the_same_values_give_the_same_id() -> None:
    # Stand-in for "serialisation changes": different in-memory representations of identical values.
    same_values = _with(0, close=Decimal("101.5"), known_at=PUBLISHED.astimezone(UTC))

    assert snapshot_id(SCHEMA, same_values) == snapshot_id(SCHEMA, ROWS)


@pytest.mark.parametrize(
    "changed",
    [
        _with(0, close=Decimal("101.55")),
        _with(1, volume=901),
        _with(0, instrument_id="INS-0003"),
        _with(0, session=date(2022, 12, 29)),
        _with(1, is_eq=True),
    ],
    ids=["decimal", "int", "string", "date", "bool"],
)
def test_any_content_change_gives_a_different_id(changed: tuple[dict[str, object], ...]) -> None:
    assert snapshot_id(SCHEMA, changed) != snapshot_id(SCHEMA, ROWS)


def test_type_change_gives_a_different_id() -> None:
    wider = tuple(Column(c.name, c.type, scale=3) if c.name == "close" else c for c in SCHEMA)

    assert snapshot_id(wider, ROWS) != snapshot_id(SCHEMA, ROWS)


def test_duplicate_rows_keep_their_multiplicity() -> None:
    assert snapshot_id(SCHEMA, (*ROWS, ROWS[0])) != snapshot_id(SCHEMA, ROWS)


def test_null_is_distinct_from_empty_string() -> None:
    schema = (Column("note", ColumnType.STRING, nullable=True),)

    assert snapshot_id(schema, ({"note": None},)) != snapshot_id(schema, ({"note": ""},))


def test_cell_boundaries_are_unambiguous() -> None:
    schema = (Column("a", ColumnType.STRING), Column("b", ColumnType.STRING))

    assert snapshot_id(schema, ({"a": "x", "b": "yz"},)) != snapshot_id(
        schema, ({"a": "xy", "b": "z"},)
    )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        (Column("v", ColumnType.DECIMAL, scale=2), 1.5, "Decimal"),
        (Column("v", ColumnType.DECIMAL, scale=2), Decimal("1.505"), "scale"),
        (Column("v", ColumnType.DECIMAL, scale=2), Decimal("NaN"), "finite"),
        (Column("v", ColumnType.INT64), True, "int"),
        (Column("v", ColumnType.INT64), 2**63, "64-bit"),
        (Column("v", ColumnType.DATE), datetime(2022, 1, 1, tzinfo=UTC), "date"),
        (Column("v", ColumnType.TIMESTAMP_UTC), datetime(2022, 1, 1), "timezone-aware"),
        (Column("v", ColumnType.STRING), None, "null"),
    ],
    ids=[
        "float",
        "too-many-places",
        "nan",
        "bool-as-int",
        "overflow",
        "datetime-as-date",
        "naive",
        "null",
    ],
)
def test_values_are_validated_against_their_type(
    column: Column, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        snapshot_id((column,), ({"v": value},))


def test_rows_must_match_the_schema_exactly() -> None:
    with pytest.raises(ValueError, match="columns"):
        snapshot_id(SCHEMA, ({**ROWS[0], "extra": 1},))


def test_duplicate_column_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        snapshot_id((Column("a", ColumnType.INT64), Column("a", ColumnType.STRING)), ())


def test_canonical_v1_known_answer() -> None:
    # Regression lock: canonical-v1 must keep this id; an algorithm change needs a new version.
    assert CANONICAL_VERSION == "canonical-v1"
    assert snapshot_id(SCHEMA, ROWS) == KNOWN_ANSWER


# Computed by canonical-v1 on 2026-10-05 and pinned; it detects accidental algorithm changes only.
KNOWN_ANSWER = "6d74024b6fbff3bcc2fbf48c937bdc31a96cc755502325b831003245d39f190c"


# --- Provenance ------------------------------------------------------------------------------


def _record(name: str, digest: str) -> SourceFileRecord:
    return SourceFileRecord(
        file_name=name,
        sha256=digest,
        acquired_at=datetime(2026, 10, 5, 9, 0, tzinfo=IST),
        provider="nse-files",
        file_format="nse-cm-bhavcopy-legacy",
        format_version="1",
    )


def test_provenance_changes_the_manifest_hash_but_not_the_snapshot_id() -> None:
    first = (_record("cm30DEC2022bhav.csv", "a" * 64),)
    second = (_record("cm30DEC2022bhav-reacquired.csv", "b" * 64),)

    assert manifest_hash(first) != manifest_hash(second)
    # The snapshot id cannot depend on provenance: its only inputs are schema and rows.
    assert list(inspect.signature(snapshot_id).parameters) == ["schema", "rows"]


def test_manifest_hash_ignores_record_order() -> None:
    records = (_record("a.csv", "a" * 64), _record("b.csv", "b" * 64))

    assert manifest_hash(records) == manifest_hash(tuple(reversed(records)))


def test_unknown_acquisition_time_is_allowed_and_distinct() -> None:
    known = _record("a.csv", "a" * 64)
    unknown = SourceFileRecord("a.csv", "a" * 64, None, "nse-files", "nse-cm-bhavcopy-legacy", "1")

    assert manifest_hash((known,)) != manifest_hash((unknown,))


@pytest.mark.parametrize("digest", ["abc", "G" * 64, "A" * 64])
def test_source_file_hash_must_be_lowercase_sha256_hex(digest: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        _record("a.csv", digest)
