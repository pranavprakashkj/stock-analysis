"""ADR-020 §1 is normative: an independent implementation written from its text must agree.

The reference below deliberately uses different code paths from the production module
(high-precision quantize instead of tuple arithmetic, isoformat instead of strftime).
"""

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Context, Decimal, Inexact, Rounded, localcontext
from typing import cast

import pytest

from trading.domain.timing import IST
from trading.infrastructure.storage.canonical import (
    Column,
    ColumnType,
    SourceFileRecord,
    manifest_hash,
    snapshot_id,
)


def _prefixed(payload: bytes) -> bytes:
    return len(payload).to_bytes(8, "big") + payload


def _reference_text(column: Column, value: object) -> str:
    if column.type is ColumnType.DECIMAL:
        assert isinstance(value, Decimal) and column.scale is not None
        with localcontext(Context(prec=200)):
            quantised = value.quantize(Decimal(10) ** -column.scale)
        return f"{abs(quantised) if quantised == 0 else quantised:f}"
    if column.type is ColumnType.TIMESTAMP_UTC:
        assert isinstance(value, datetime)
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if column.type is ColumnType.BOOL:
        return "true" if value else "false"
    if column.type is ColumnType.DATE:
        assert isinstance(value, date)
        return value.isoformat()
    return str(value)


def reference_id(tag: str, schema: Sequence[Column], rows: Sequence[Mapping[str, object]]) -> str:
    columns = sorted(schema, key=lambda column: column.name)
    encoded = sorted(
        b"".join(
            b"\x00"
            if row[column.name] is None
            else b"\x01" + _prefixed(_reference_text(column, row[column.name]).encode())
            for column in columns
        )
        for row in rows
    )
    payload = _prefixed(tag.encode()) + len(columns).to_bytes(8, "big")
    for column in columns:
        type_text = f"DECIMAL({column.scale})" if column.scale is not None else column.type.value
        payload += _prefixed(column.name.encode()) + _prefixed(type_text.encode())
        payload += b"\x01" if column.nullable else b"\x00"
    payload += len(encoded).to_bytes(8, "big") + b"".join(_prefixed(row) for row in encoded)
    return hashlib.sha256(payload).hexdigest()


# Same table and pinned id as test_canonical_snapshot.py (repeated: tests are not importable).
SCHEMA = (
    Column("instrument_id", ColumnType.STRING),
    Column("session", ColumnType.DATE),
    Column("close", ColumnType.DECIMAL, scale=2),
    Column("volume", ColumnType.INT64),
    Column("known_at", ColumnType.TIMESTAMP_UTC),
    Column("is_eq", ColumnType.BOOL),
)
_PUBLISHED = datetime(2022, 12, 30, 18, 0, tzinfo=IST)
ROWS: tuple[dict[str, object], ...] = (
    {
        "instrument_id": "INS-0001",
        "session": date(2022, 12, 30),
        "close": Decimal("101.50"),
        "volume": 1200,
        "known_at": _PUBLISHED,
        "is_eq": True,
    },
    {
        "instrument_id": "INS-0002",
        "session": date(2022, 12, 30),
        "close": Decimal("55.05"),
        "volume": 900,
        "known_at": _PUBLISHED,
        "is_eq": False,
    },
)
KNOWN_ANSWER = "6d74024b6fbff3bcc2fbf48c937bdc31a96cc755502325b831003245d39f190c"

EDGE_SCHEMA = (
    Column("amount", ColumnType.DECIMAL, scale=2),
    Column("note", ColumnType.STRING, nullable=True),
    Column("count", ColumnType.INT64),
)
EDGE_ROWS: tuple[dict[str, object], ...] = (
    {"amount": Decimal("-0.00"), "note": None, "count": -5},
    {"amount": Decimal("-12.30"), "note": "", "count": 0},
    {"amount": Decimal("1E+27"), "note": "ünïcode", "count": 2**63 - 1},
    {"amount": Decimal("7.500"), "note": "x", "count": -(2**63)},
)


def test_reference_reproduces_the_pinned_known_answer() -> None:
    assert reference_id("canonical-v1", SCHEMA, ROWS) == KNOWN_ANSWER


def test_reference_agrees_on_edge_values() -> None:
    assert reference_id("canonical-v1", EDGE_SCHEMA, EDGE_ROWS) == snapshot_id(
        EDGE_SCHEMA, EDGE_ROWS
    )


def test_hash_does_not_depend_on_the_callers_decimal_context() -> None:
    expected = snapshot_id(EDGE_SCHEMA, EDGE_ROWS)
    hostile = Context(prec=3, traps=[Inexact, Rounded])

    with localcontext(hostile):
        assert snapshot_id(EDGE_SCHEMA, EDGE_ROWS) == expected


def test_negative_zero_and_zero_are_the_same_value() -> None:
    schema = (Column("v", ColumnType.DECIMAL, scale=2),)

    assert snapshot_id(schema, ({"v": Decimal("-0.00")},)) == snapshot_id(
        schema, ({"v": Decimal("0")},)
    )


def test_unencodable_text_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="UTF-8"):
        snapshot_id((Column("s", ColumnType.STRING),), ({"s": "\ud800"},))


@pytest.mark.parametrize("scale", [True, -1, 2.0])
def test_scale_must_be_a_non_negative_int(scale: object) -> None:
    with pytest.raises(ValueError, match="scale"):
        Column("v", ColumnType.DECIMAL, scale=cast("int", scale))  # deliberately wrong type


def test_manifest_and_snapshot_hashes_use_different_tags() -> None:
    record = SourceFileRecord(
        "a.csv", "a" * 64, datetime(2026, 10, 5, 9, 0, tzinfo=IST), "nse-files", "fmt", "1"
    )
    manifest_schema = (
        Column("file_name", ColumnType.STRING),
        Column("sha256", ColumnType.STRING),
        Column("acquired_at", ColumnType.TIMESTAMP_UTC, nullable=True),
        Column("provider", ColumnType.STRING),
        Column("file_format", ColumnType.STRING),
        Column("format_version", ColumnType.STRING),
    )
    row = {
        "file_name": "a.csv",
        "sha256": "a" * 64,
        "acquired_at": record.acquired_at,
        "provider": "nse-files",
        "file_format": "fmt",
        "format_version": "1",
    }

    assert manifest_hash((record,)) == reference_id("manifest-v1", manifest_schema, (row,))
    assert manifest_hash((record,)) != snapshot_id(manifest_schema, (row,))


def test_column_type_must_be_a_column_type() -> None:
    with pytest.raises(ValueError, match="ColumnType"):
        Column("v", cast("ColumnType", "STRING"))  # deliberately wrong type


def test_absurd_decimal_exponent_is_rejected_quickly() -> None:
    with pytest.raises(ValueError, match="digits"):
        snapshot_id((Column("v", ColumnType.DECIMAL, scale=2),), ({"v": Decimal("1E+999999999")},))


def test_timestamps_before_year_1000_are_zero_padded() -> None:
    schema = (Column("t", ColumnType.TIMESTAMP_UTC),)
    early = datetime(999, 1, 2, 3, 4, 5, tzinfo=UTC)

    assert snapshot_id(schema, ({"t": early},)) == reference_id(
        "canonical-v1", schema, ({"t": early},)
    )
    assert _reference_text(schema[0], early) == "0999-01-02T03:04:05.000000Z"
