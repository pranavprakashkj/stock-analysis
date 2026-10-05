"""Canonical logical-content identity for snapshots, and source-file provenance (ADR-020).

canonical-v1: columns sorted by name; values validated against explicit types and rendered as
canonical text; each cell tagged (0x00 null / 0x01 value) and length-prefixed; rows sorted by their
encoded bytes; SHA-256 over version, schema, row count and rows. No floating-point type exists.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum

from trading.domain.timing import require_aware

CANONICAL_VERSION = "canonical-v1"
MANIFEST_VERSION = "manifest-v1"
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1
# Bound on DECIMAL size (total digits incl. scale). Keeps hashing bounded for absurd exponents; the
# limit matches the common decimal128 maximum precision and is re-checked against storage in 1.11.
_MAX_DECIMAL_DIGITS = 38
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")

CellValue = str | int | Decimal | date | datetime | bool | None


class ColumnType(Enum):
    STRING = "STRING"
    INT64 = "INT64"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    TIMESTAMP_UTC = "TIMESTAMP_UTC"
    BOOL = "BOOL"


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: ColumnType
    scale: int | None = None
    nullable: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("column name must be non-empty")
        if not isinstance(self.type, ColumnType):
            raise ValueError(f"column type must be a ColumnType, got {self.type!r}")
        if (self.type is ColumnType.DECIMAL) != (self.scale is not None):
            raise ValueError("scale is required for DECIMAL columns and only for them")
        if self.scale is not None and (type(self.scale) is not int or self.scale < 0):
            raise ValueError("scale must be a non-negative int")
        if type(self.nullable) is not bool:
            raise ValueError("nullable must be a bool")

    @property
    def type_text(self) -> str:
        return f"DECIMAL({self.scale})" if self.type is ColumnType.DECIMAL else self.type.value


def _length_prefixed(payload: bytes) -> bytes:
    return len(payload).to_bytes(8, "big") + payload


def _decimal_text(column: Column, value: object) -> str:
    """Fixed-point text with exactly `scale` places, computed without any decimal context."""
    if not isinstance(value, Decimal):
        raise ValueError(f"{column.name}: DECIMAL needs a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{column.name}: DECIMAL must be finite")
    scale = column.scale
    assert scale is not None
    sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)
    coefficient = int("".join(map(str, digits)) or "0")
    shift = exponent + scale  # power of ten from the coefficient to units of 10**-scale
    if len(digits) + max(shift, 0) > _MAX_DECIMAL_DIGITS:
        raise ValueError(f"{column.name}: DECIMAL exceeds {_MAX_DECIMAL_DIGITS} digits")
    if shift >= 0:
        units = coefficient * 10**shift
    else:
        units, remainder = divmod(coefficient, 10**-shift)
        if remainder:
            raise ValueError(f"{column.name}: {value} has more places than scale {scale}")
    text = str(units).rjust(scale + 1, "0")
    fixed = f"{text[:-scale]}.{text[-scale:]}" if scale else text
    return f"-{fixed}" if sign and units else fixed


def _canonical_text(column: Column, value: object) -> str:
    match column.type:
        case ColumnType.STRING:
            if not isinstance(value, str):
                raise ValueError(f"{column.name}: STRING needs a str")
            return value
        case ColumnType.INT64:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{column.name}: INT64 needs an int")
            if not _INT64_MIN <= value <= _INT64_MAX:
                raise ValueError(f"{column.name}: value outside signed 64-bit range")
            return str(value)
        case ColumnType.DECIMAL:
            return _decimal_text(column, value)
        case ColumnType.DATE:
            if isinstance(value, datetime) or not isinstance(value, date):
                raise ValueError(f"{column.name}: DATE needs a date, not a datetime")
            return value.isoformat()
        case ColumnType.TIMESTAMP_UTC:
            if not isinstance(value, datetime):
                raise ValueError(f"{column.name}: TIMESTAMP_UTC needs a datetime")
            try:
                instant = require_aware(value).astimezone(UTC)
            except OverflowError as error:
                raise ValueError(f"{column.name}: timestamp out of range") from error
            return instant.isoformat(timespec="microseconds").replace("+00:00", "Z")
        case ColumnType.BOOL:
            if not isinstance(value, bool):
                raise ValueError(f"{column.name}: BOOL needs a bool")
            return "true" if value else "false"


def _encode_cell(column: Column, value: object) -> bytes:
    if value is None:
        if not column.nullable:
            raise ValueError(f"{column.name}: null in a non-nullable column")
        return b"\x00"
    try:
        payload = _canonical_text(column, value).encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{column.name}: text is not encodable as UTF-8") from error
    return b"\x01" + _length_prefixed(payload)


def _canonical_schema(schema: Sequence[Column]) -> tuple[Column, ...]:
    names = [column.name for column in schema]
    if len(set(names)) != len(names):
        raise ValueError("duplicate column names")
    return tuple(sorted(schema, key=lambda column: column.name))


def snapshot_id(schema: Sequence[Column], rows: Iterable[Mapping[str, object]]) -> str:
    """SHA-256 hex digest identifying the logical table (ADR-020 canonical-v1)."""
    return _digest(CANONICAL_VERSION, schema, rows)


def _digest(tag: str, schema: Sequence[Column], rows: Iterable[Mapping[str, object]]) -> str:
    columns = _canonical_schema(schema)
    expected = {column.name for column in columns}
    encoded_rows: list[bytes] = []
    for row in rows:
        if set(row) != expected:
            raise ValueError(f"row columns {sorted(row)} do not match schema {sorted(expected)}")
        encoded_rows.append(b"".join(_encode_cell(column, row[column.name]) for column in columns))
    encoded_rows.sort()

    digest = hashlib.sha256()
    digest.update(_length_prefixed(tag.encode()))
    digest.update(len(columns).to_bytes(8, "big"))
    for column in columns:
        digest.update(_length_prefixed(column.name.encode()))
        digest.update(_length_prefixed(column.type_text.encode()))
        digest.update(b"\x01" if column.nullable else b"\x00")
    digest.update(len(encoded_rows).to_bytes(8, "big"))
    for encoded in encoded_rows:
        digest.update(_length_prefixed(encoded))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class SourceFileRecord:
    """Provenance of one source file. Recorded beside a snapshot; never part of its id."""

    file_name: str
    sha256: str
    acquired_at: datetime | None
    provider: str
    file_format: str
    format_version: str

    def __post_init__(self) -> None:
        if not _SHA256_HEX.fullmatch(self.sha256):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        if self.acquired_at is not None:
            require_aware(self.acquired_at)
        for name in ("file_name", "provider", "file_format", "format_version"):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")


_MANIFEST_SCHEMA = (
    Column("file_name", ColumnType.STRING),
    Column("sha256", ColumnType.STRING),
    Column("acquired_at", ColumnType.TIMESTAMP_UTC, nullable=True),
    Column("provider", ColumnType.STRING),
    Column("file_format", ColumnType.STRING),
    Column("format_version", ColumnType.STRING),
)


def manifest_hash(records: Iterable[SourceFileRecord]) -> str:
    """Order-independent hash of a source-file manifest, using the same canonical encoding."""
    rows: list[dict[str, CellValue]] = [
        {
            "file_name": record.file_name,
            "sha256": record.sha256,
            "acquired_at": record.acquired_at,
            "provider": record.provider,
            "file_format": record.file_format,
            "format_version": record.format_version,
        }
        for record in records
    ]
    return _digest(MANIFEST_VERSION, _MANIFEST_SCHEMA, rows)
