"""Task 1.3: JSON logs with `run_id`, `level`, `event`, plus SPEC §6 `track` and `trading_date`."""

import io
import json
import logging
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import cast

import pytest
from pydantic import SecretStr

from trading.infrastructure.config import ConfigError, TradingSettings
from trading.infrastructure.logging import REDACTED, JsonFormatter, LogLevel, configure_logging

type ExcInfo = (
    tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
)
RUN_ID = "run-0001"
FIXED_CREATED = datetime(2026, 10, 5, 12, 30, 45, 123456, tzinfo=UTC).timestamp()
TOP_LEVEL_KEYS = {
    "ts",
    "level",
    "logger",
    "event",
    "run_id",
    "track",
    "trading_date",
    "fields",
    "exc",
    "stack",
}


class Track(Enum):
    ALGORITHM = "algorithm"


class _Opaque:
    def __repr__(self) -> str:
        return "Opaque(password=hunter2)"


def _record(
    event: str = "snapshot_written",
    level: int = logging.INFO,
    extra: dict[str, object] | None = None,
    exc_info: ExcInfo | None = None,
) -> logging.LogRecord:
    record = logging.getLogger("trading.test").makeRecord(
        "trading.test", level, "test.py", 1, event, (), exc_info, extra=extra
    )
    record.created = FIXED_CREATED
    return record


def _format(record: logging.LogRecord) -> dict[str, object]:
    line = JsonFormatter(RUN_ID).format(record)
    assert "\n" not in line
    parsed = json.loads(line)
    assert isinstance(parsed, dict)
    return parsed


def _fields(record: logging.LogRecord) -> object:
    return _format(record)["fields"]


# --- structure --------------------------------------------------------------------------------


def test_minimal_record_has_exactly_the_stable_keys() -> None:
    line = JsonFormatter(RUN_ID).format(_record())

    assert line == (
        '{"event":"snapshot_written","exc":null,"fields":{},"level":"INFO",'
        '"logger":"trading.test","run_id":"run-0001","stack":null,"track":null,"trading_date":null,'
        '"ts":"2026-10-05T12:30:45.123Z"}'
    )


@pytest.mark.parametrize(
    ("level", "name"),
    [
        (logging.DEBUG, "DEBUG"),
        (logging.INFO, "INFO"),
        (logging.WARNING, "WARNING"),
        (logging.ERROR, "ERROR"),
        (logging.CRITICAL, "CRITICAL"),
    ],
)
def test_level_is_the_level_name(level: int, name: str) -> None:
    assert _format(_record(level=level))["level"] == name


def test_every_record_has_the_same_top_level_keys() -> None:
    rich = _record(
        extra={"track": "algorithm", "trading_date": date(2026, 10, 5), "count": 3},
        exc_info=_exc_info(ValueError("boom")),
    )

    assert set(_format(_record())) == TOP_LEVEL_KEYS
    assert set(_format(rich)) == TOP_LEVEL_KEYS


def test_track_and_trading_date_are_top_level() -> None:
    parsed = _format(_record(extra={"track": Track.ALGORITHM, "trading_date": date(2026, 10, 5)}))

    assert parsed["track"] == "algorithm"
    assert parsed["trading_date"] == "2026-10-05"
    assert parsed["fields"] == {}


def test_extra_cannot_override_the_run_id_or_event() -> None:
    parsed = _format(_record(extra={"run_id": "forged", "event": "forged"}))

    assert parsed["run_id"] == RUN_ID
    assert parsed["event"] == "snapshot_written"
    assert parsed["fields"] == {"run_id": "forged", "event": "forged"}


def test_formatting_is_deterministic() -> None:
    record = _record(extra={"b": 1, "a": {"y": 2, "x": 1}})

    line = JsonFormatter(RUN_ID).format(record)

    assert line == JsonFormatter(RUN_ID).format(record)
    assert '"fields":{"a":{"x":1,"y":2},"b":1}' in line


@pytest.mark.parametrize("run_id", ["", " ", "run 1", "run\n1"])
def test_run_id_must_be_non_empty_without_whitespace(run_id: str) -> None:
    with pytest.raises(ValueError, match="run_id"):
        JsonFormatter(run_id)


# --- serialisation ----------------------------------------------------------------------------


def test_values_are_serialised_to_json_types() -> None:
    fields = _fields(
        _record(
            extra={
                "text": "ünï",
                "count": 7,
                "flag": True,
                "nothing": None,
                "ratio": 0.5,
                "price": Decimal("101.50"),
                "day": date(2026, 10, 5),
                "at": datetime(2026, 10, 5, 9, 15, tzinfo=UTC),
                "kind": Track.ALGORITHM,
                "path": Path("data/snapshots"),
                "ids": ("INS-1", "INS-2"),
                "nested": {"n": [1, 2]},
            }
        )
    )

    assert fields == {
        "text": "ünï",
        "count": 7,
        "flag": True,
        "nothing": None,
        "ratio": 0.5,
        "price": "101.50",
        "day": "2026-10-05",
        "at": "2026-10-05T09:15:00+00:00",
        "kind": "algorithm",
        "path": "data/snapshots",
        "ids": ["INS-1", "INS-2"],
        "nested": {"n": [1, 2]},
    }


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_strings(value: float) -> None:
    assert _fields(_record(extra={"x": value})) == {"x": str(value)}


def test_unsupported_values_show_only_their_type() -> None:
    fields = _fields(_record(extra={"thing": _Opaque()}))

    assert fields == {"thing": "<unsupported _Opaque>"}


def test_cyclic_value_is_cut_off_instead_of_raising() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)

    fields = _fields(_record(extra={"c": cyclic}))

    assert "<too deep>" in json.dumps(fields)


def test_stack_info_is_recorded() -> None:
    record = _record()
    record.stack_info = "Stack (most recent call last):\n  frame"

    assert _format(record)["stack"] == "Stack (most recent call last):\n  frame"
    assert _format(_record())["stack"] is None


def test_non_string_mapping_keys_are_unsupported() -> None:
    assert _fields(_record(extra={"m": {1: "a"}})) == {"m": "<unsupported dict>"}


def test_exception_is_recorded_with_type_and_traceback() -> None:
    exc = _format(_record(level=logging.ERROR, exc_info=_exc_info(ValueError("boom"))))["exc"]

    assert isinstance(exc, dict)
    assert exc["type"] == "ValueError"
    assert "ValueError: boom" in exc["traceback"]


def test_prose_message_with_arguments_is_still_one_json_line() -> None:
    record = logging.getLogger("other.lib").makeRecord(
        "other.lib", logging.WARNING, "lib.py", 1, "retry %d of %s\nnext", (2, "x"), None
    )

    parsed = json.loads(JsonFormatter(RUN_ID).format(record))

    assert parsed["event"] == "retry 2 of x\nnext"


# --- secrets ----------------------------------------------------------------------------------


def test_secret_values_are_redacted() -> None:
    fields = _fields(_record(extra={"key": SecretStr("hunter2"), "nested": [SecretStr("x")]}))

    assert fields == {"key": REDACTED, "nested": [REDACTED]}


@pytest.mark.parametrize(
    "name",
    [
        "api_key",
        "API_KEY",
        "apikey",
        "token",
        "access_token",
        "password",
        "client_secret",
        "authorization",
        "credentials",
        "private_key",
        "auth",
        "cookie",
        "bearer",
        "pwd",
        "database_dsn",
    ],
)
def test_credential_like_field_names_are_redacted(name: str) -> None:
    assert _fields(_record(extra={name: "hunter2"})) == {name: REDACTED}


def test_credential_like_nested_keys_are_redacted() -> None:
    fields = _fields(_record(extra={"request": {"url": "/x", "headers": {"Authorization": "b"}}}))

    assert fields == {"request": {"url": "/x", "headers": {"Authorization": REDACTED}}}


def test_ordinary_field_names_are_not_redacted() -> None:
    assert _fields(_record(extra={"session": "2026-10-05", "symbol": "ABC"})) == {
        "session": "2026-10-05",
        "symbol": "ABC",
    }


def test_logged_config_error_never_contains_the_secret(tmp_path: Path) -> None:
    secret = "s3cr3t-value-that-must-never-appear"
    path = tmp_path / "settings.toml"
    path.write_text(f'api_key = "{secret}"\n[log]\nlevel = "INFO"\n')

    class WithSecret(TradingSettings):
        api_key: SecretStr

    try:
        WithSecret.load(path, environ={})
    except ConfigError:
        line = JsonFormatter(RUN_ID).format(_record(level=logging.ERROR, exc_info=sys.exc_info()))
    else:
        pytest.fail("a secret in the TOML file must be rejected")

    assert secret not in line
    assert "api_key may come only from the environment" in line


# --- configure_logging ------------------------------------------------------------------------


@pytest.fixture
def root_logger() -> Iterator[logging.Logger]:
    root, settings_logger = logging.getLogger(), logging.getLogger("pydantic_settings")
    saved_handlers, saved_level = root.handlers[:], root.level
    saved_settings_level = settings_logger.level
    yield root
    for handler in root.handlers:
        if handler not in saved_handlers:
            handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    settings_logger.setLevel(saved_settings_level)


@pytest.mark.usefixtures("root_logger")
def test_configure_logging_writes_json_to_the_stream() -> None:
    stream = io.StringIO()
    configure_logging("INFO", RUN_ID, stream=stream)

    logging.getLogger("trading.anything").info("config_loaded", extra={"count": 1})

    parsed = json.loads(stream.getvalue())
    assert parsed["event"] == "config_loaded"
    assert parsed["run_id"] == RUN_ID
    assert parsed["fields"] == {"count": 1}


@pytest.mark.usefixtures("root_logger")
def test_configure_logging_applies_the_level() -> None:
    stream = io.StringIO()
    configure_logging("WARNING", RUN_ID, stream=stream)

    logging.getLogger("trading.anything").info("ignored")
    logging.getLogger("trading.anything").warning("kept")

    assert [json.loads(line)["event"] for line in stream.getvalue().splitlines()] == ["kept"]


def test_configure_logging_owns_the_root_logger(root_logger: logging.Logger) -> None:
    """Every line is JSON: earlier handlers, including a previous configuration, are removed."""
    foreign, first, second = io.StringIO(), io.StringIO(), io.StringIO()
    root_logger.addHandler(logging.StreamHandler(foreign))
    configure_logging("INFO", "run-a", stream=first)
    configure_logging("INFO", "run-b", stream=second)

    logging.getLogger("trading.anything").info("once")

    assert foreign.getvalue() == ""
    assert first.getvalue() == ""
    assert json.loads(second.getvalue())["run_id"] == "run-b"
    assert len(root_logger.handlers) == 1


@pytest.mark.usefixtures("root_logger")
def test_pydantic_settings_debug_output_is_suppressed() -> None:
    """Its DEBUG output dumps raw settings values, including secrets."""
    stream = io.StringIO()
    configure_logging("DEBUG", RUN_ID, stream=stream)

    logging.getLogger("pydantic_settings").debug("raw values: hunter2")
    logging.getLogger("pydantic_settings.main").debug("raw values: hunter2")

    assert stream.getvalue() == ""


@pytest.mark.usefixtures("root_logger")
def test_configure_logging_rejects_unknown_levels() -> None:
    with pytest.raises(ValueError, match="level"):
        configure_logging(cast("LogLevel", "TRACE"), RUN_ID, stream=io.StringIO())


def _exc_info(error: BaseException) -> ExcInfo:
    try:
        raise error
    except BaseException:
        return sys.exc_info()
