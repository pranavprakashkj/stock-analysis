"""Structured JSON logs (task 1.3; ADR-010: stdlib `logging` with a JSON formatter; SPEC §6 fields).

Every line is one JSON object with the same top-level keys, sorted:
- `ts`: record time, UTC ISO-8601 with "Z". Operational metadata only: logs are never an input to
  results, manifests or snapshot ids (DC5, ADR-020).
- `level`: DEBUG, INFO, WARNING, ERROR or CRITICAL.
- `logger`: logger name.
- `event`: the log message, a stable event name such as "snapshot_written".
- `run_id`: the run this process belongs to, fixed when logging is configured.
- `track`, `trading_date`: SPEC §6 context, passed per record via `extra=`; null when absent.
- `fields`: every other `extra=` value.
- `exc`: exception type and traceback, or null.
- `stack`: stack trace from `stack_info=True`, or null.

Application and infrastructure code log through stdlib `logging` only, for example
`logger.info("snapshot_written", extra={"snapshot_id": sid, "trading_date": day})`; nothing outside
this module imports it. The domain does not log (import-linter contract).

Values are rendered as JSON types; nesting deeper than a fixed limit (or a cycle) is cut off.
Unsupported types show only their type name, never their repr.

Secrets: `SecretStr`/`SecretBytes` values are always REDACTED; that is the real control. Values of
credential-like field names are REDACTED too, on a best-effort name match. `event` and exception
text are not redacted, so secrets must never be put in messages or exception text.
"""

import json
import logging
import math
import re
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Literal, TextIO, get_args

from pydantic import SecretBytes, SecretStr

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

REDACTED = "**********"
_LEVELS = frozenset(get_args(LogLevel.__value__))
_MAX_DEPTH = 8
_RUN_ID = re.compile(r"\S+")
_CREDENTIAL_NAME = re.compile(
    r"secret|token|passw(or)?d|pwd|api_?key|auth|credential|private_?key|cookie|bearer|dsn",
    re.IGNORECASE,
)
# pydantic-settings logs raw settings values (secrets included) at DEBUG; keep it at WARNING.
_SILENCED_BELOW_WARNING = ("pydantic_settings",)
_CONTEXT_KEYS = ("track", "trading_date")
_STANDARD_ATTRIBUTES = frozenset(
    logging.LogRecord("", logging.INFO, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


def _render(value: object, depth: int = 0) -> JsonValue:
    if depth > _MAX_DEPTH:
        return "<too deep>"
    match value:
        case SecretStr() | SecretBytes():
            return REDACTED
        case None | bool() | int() | str():
            return value
        case float():
            return value if math.isfinite(value) else str(value)
        case Decimal() | PurePath():
            return str(value)
        case datetime() | date():
            return value.isoformat()
        case Enum():
            return _render(value.value, depth + 1)
        case list() | tuple():
            return [_render(item, depth + 1) for item in value]
        case Mapping() if all(isinstance(key, str) for key in value):
            return _render_fields(value, depth + 1)
        case _:
            return f"<unsupported {type(value).__name__}>"


def _render_fields(values: Mapping[str, object], depth: int = 0) -> dict[str, JsonValue]:
    return {
        name: REDACTED if _CREDENTIAL_NAME.search(name) else _render(value, depth)
        for name, value in values.items()
    }


class JsonFormatter(logging.Formatter):
    """Formats each record as one JSON line with the stable keys listed in the module docstring."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError(f"run_id must be non-empty without whitespace: {run_id!r}")
        self._run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        extra = {
            name: value
            for name, value in record.__dict__.items()
            if name not in _STANDARD_ATTRIBUTES
        }
        context = {key: extra.pop(key, None) for key in _CONTEXT_KEYS}
        exc: JsonValue = None
        if record.exc_info is not None and record.exc_info[0] is not None:
            exc = {
                "type": record.exc_info[0].__name__,
                "traceback": self.formatException(record.exc_info),
            }
        payload: dict[str, JsonValue] = {
            "ts": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "run_id": self._run_id,
            **_render_fields(context),
            "fields": _render_fields(extra),
            "exc": exc,
            "stack": record.stack_info,
        }
        # ASCII-only output: non-ASCII text is \u-escaped, so any stream encoding can carry it.
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class _JsonHandler(logging.StreamHandler[TextIO]):
    """Marks the handler installed by `configure_logging`, so reconfiguring closes it."""


def configure_logging(level: LogLevel, run_id: str, stream: TextIO | None = None) -> None:
    """Send all log records at `level` and above to `stream` (default: the current stderr) as
    JSON lines tagged with `run_id`.

    Owns the root logger: every existing root handler is removed, so no non-JSON line is written
    (handlers this function installed earlier are also closed). Called once by each entry point.
    """
    if level not in _LEVELS:
        raise ValueError(f"unknown log level: {level!r}")
    handler = _JsonHandler(sys.stderr if stream is None else stream)
    handler.setFormatter(JsonFormatter(run_id))
    root = logging.getLogger()
    for old in root.handlers[:]:
        root.removeHandler(old)
        if isinstance(old, _JsonHandler):
            old.close()
    root.addHandler(handler)
    root.setLevel(level)
    for name in _SILENCED_BELOW_WARNING:
        logging.getLogger(name).setLevel(logging.WARNING)
