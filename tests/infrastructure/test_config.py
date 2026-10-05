"""Task 1.3: typed configuration from one TOML file plus secrets from the environment.

Secrets are exercised through a test-only subclass, because Phase 1 defines no secret settings.
"""

import re
import traceback
from pathlib import Path
from typing import Annotated, get_args

import pytest
from pydantic import BaseModel, Field, SecretBytes, SecretStr, ValidationError

from trading.infrastructure.config import ConfigError, LogSettings, TradingSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = REPO_ROOT / "configs" / "example.toml"
VALID = '[log]\nlevel = "INFO"\n'
SECRET_VALUE = "s3cr3t-value-that-must-never-appear"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "settings.toml"
    path.write_text(text)
    return path


class _WithSecret(TradingSettings):
    api_key: Annotated[SecretStr, Field(min_length=20)]


# --- valid configuration ---------------------------------------------------------------------


def test_example_config_loads() -> None:
    settings = TradingSettings.load(EXAMPLE_CONFIG, environ={})

    assert settings.log == LogSettings(level="INFO")


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_each_log_level_loads(tmp_path: Path, level: str) -> None:
    settings = TradingSettings.load(_write(tmp_path, f'[log]\nlevel = "{level}"\n'), environ={})

    assert settings.log.level == level


def test_loading_is_deterministic_and_ignores_the_process_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, VALID)
    monkeypatch.setenv("TRADING_LOG", "this would be rejected if it were read")

    assert TradingSettings.load(path, environ={}) == TradingSettings.load(path, environ={})


def test_unrelated_environment_variables_are_ignored(tmp_path: Path) -> None:
    environ = {"PATH": "/usr/bin", "HOME": "/home/x", "TRADINGVIEW": "x"}

    assert TradingSettings.load(_write(tmp_path, VALID), environ=environ).log.level == "INFO"


def test_settings_are_immutable(tmp_path: Path) -> None:
    settings = TradingSettings.load(_write(tmp_path, VALID), environ={})

    with pytest.raises(ValidationError, match="frozen"):
        settings.log.__setattr__("level", "DEBUG")  # the runtime check, not the type checker's


# --- invalid or missing configuration fails fast ----------------------------------------------


def test_missing_file_fails(tmp_path: Path) -> None:
    missing = tmp_path / "absent.toml"

    with pytest.raises(ConfigError, match=r"config file not found: .*absent\.toml"):
        TradingSettings.load(missing, environ={})


def test_directory_instead_of_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config file not found"):
        TradingSettings.load(tmp_path, environ={})


def test_invalid_toml_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid TOML"):
        TradingSettings.load(_write(tmp_path, "[log\nlevel = "), environ={})


def test_non_utf8_file_fails(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_bytes(b'[log]\nlevel = "\xff"\n')

    with pytest.raises(ConfigError, match="invalid TOML"):
        TradingSettings.load(path, environ={})


@pytest.mark.parametrize(
    ("text", "location"),
    [
        ("", "log"),
        ("[log]\n", "log.level"),
    ],
    ids=["empty-file", "empty-section"],
)
def test_missing_required_setting_fails_with_its_location(
    tmp_path: Path, text: str, location: str
) -> None:
    with pytest.raises(ConfigError, match=rf"(?m)^  {re.escape(location)}: Field required$"):
        TradingSettings.load(_write(tmp_path, text), environ={})


@pytest.mark.parametrize(
    ("text", "location"),
    [
        ("risk_limit = 1\n" + VALID, "risk_limit"),  # before [log], so it is a top-level key
        (VALID + 'format = "text"\n', "log.format"),
    ],
    ids=["top-level", "nested"],
)
def test_unknown_setting_is_rejected(tmp_path: Path, text: str, location: str) -> None:
    pattern = rf"(?m)^  {re.escape(location)}: Extra inputs are not permitted$"

    with pytest.raises(ConfigError, match=pattern):
        TradingSettings.load(_write(tmp_path, text), environ={})


@pytest.mark.parametrize(
    "text",
    ['[log]\nlevel = "info"\n', '[log]\nlevel = "TRACE"\n', "[log]\nlevel = 20\n"],
    ids=["lowercase", "unknown-name", "number"],
)
def test_invalid_log_level_is_rejected(tmp_path: Path, text: str) -> None:
    with pytest.raises(ConfigError, match=r"log\.level"):
        TradingSettings.load(_write(tmp_path, text), environ={})


def test_error_lists_every_problem_with_the_file_path(tmp_path: Path) -> None:
    path = _write(tmp_path, "extra = 1\n")

    with pytest.raises(ConfigError) as caught:
        TradingSettings.load(path, environ={})

    message = str(caught.value)
    assert str(path) in message
    assert "log: Field required" in message
    assert "extra: Extra inputs are not permitted" in message


@pytest.mark.parametrize("text", ["", "[log\n"], ids=["validation", "toml-syntax"])
def test_underlying_error_is_not_attached(tmp_path: Path, text: str) -> None:
    """The original errors embed input values; they must not ride along on the ConfigError."""
    with pytest.raises(ConfigError) as caught:
        TradingSettings.load(_write(tmp_path, text), environ={})

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_rejected_secret_appears_nowhere_in_the_error_or_its_traceback(tmp_path: Path) -> None:
    short = "short-s3cr3t"

    with pytest.raises(ConfigError) as caught:
        _WithSecret.load(_write(tmp_path, VALID), environ={"TRADING_API_KEY": short})

    assert caught.value.__context__ is None
    assert short not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "text",
    ['[LOG]\nlevel = "INFO"\n', VALID + '[LOG]\nlevel = "DEBUG"\n'],
    ids=["other-case", "duplicate-in-other-case"],
)
def test_keys_are_case_sensitive(tmp_path: Path, text: str) -> None:
    with pytest.raises(ConfigError, match=r"(?m)^  LOG: Extra inputs are not permitted$"):
        TradingSettings.load(_write(tmp_path, text), environ={})


def test_unreadable_file_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID)
    path.chmod(0)
    try:
        with pytest.raises(ConfigError, match="cannot read config file"):
            TradingSettings.load(path, environ={})
    finally:
        path.chmod(0o600)


def test_home_relative_path_is_expanded_before_the_existence_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(tmp_path, VALID)

    assert TradingSettings.load(Path("~/settings.toml"), environ={}).log.level == "INFO"


def test_pydantic_settings_debug_output_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With this variable set, pydantic-settings logs raw source values, including secrets."""
    monkeypatch.setenv("PYDANTIC_SETTINGS_DEBUG", "1")

    with pytest.raises(ConfigError, match="PYDANTIC_SETTINGS_DEBUG"):
        TradingSettings.load(_write(tmp_path, VALID), environ={})


def test_environment_variable_for_a_non_secret_setting_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TRADING_LOG is not a secret setting"):
        TradingSettings.load(_write(tmp_path, VALID), environ={"TRADING_LOG": "x"})


def test_unknown_trading_environment_variable_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TRADING_LOG__LEVEL is not a secret setting"):
        TradingSettings.load(_write(tmp_path, VALID), environ={"TRADING_LOG__LEVEL": "DEBUG"})


def test_direct_construction_is_refused() -> None:
    with pytest.raises(ConfigError, match=r"TradingSettings\.load"):
        TradingSettings()


# --- secrets only from the environment --------------------------------------------------------


def test_secret_is_read_from_the_environment(tmp_path: Path) -> None:
    settings = _WithSecret.load(_write(tmp_path, VALID), environ={"TRADING_API_KEY": SECRET_VALUE})

    assert settings.api_key.get_secret_value() == SECRET_VALUE
    assert SECRET_VALUE not in repr(settings)
    assert SECRET_VALUE not in str(settings)


def test_secret_in_the_toml_file_is_rejected_without_echoing_it(tmp_path: Path) -> None:
    path = _write(tmp_path, f'api_key = "{SECRET_VALUE}"\n' + VALID)

    with pytest.raises(ConfigError, match="api_key may come only from the environment") as caught:
        _WithSecret.load(path, environ={"TRADING_API_KEY": SECRET_VALUE})

    assert SECRET_VALUE not in str(caught.value)


def test_secret_bytes_field_in_the_toml_file_is_rejected(tmp_path: Path) -> None:
    class WithBytes(TradingSettings):
        blob: SecretBytes

    with pytest.raises(ConfigError, match="blob may come only from the environment"):
        WithBytes.load(_write(tmp_path, 'blob = "x"\n' + VALID), environ={})


def test_missing_secret_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="api_key: Field required"):
        _WithSecret.load(_write(tmp_path, VALID), environ={})


def test_invalid_secret_is_reported_without_its_value(tmp_path: Path) -> None:
    short = "short-s3cr3t"

    with pytest.raises(ConfigError, match="api_key") as caught:
        _WithSecret.load(_write(tmp_path, VALID), environ={"TRADING_API_KEY": short})

    assert short not in str(caught.value)


def test_empty_secret_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TRADING_API_KEY is empty"):
        _WithSecret.load(_write(tmp_path, VALID), environ={"TRADING_API_KEY": ""})


def test_secret_field_with_an_alias_is_refused(tmp_path: Path) -> None:
    """The TOML source matches by alias, so an aliased secret could bypass the TOML check."""

    class Aliased(TradingSettings):
        api_key: SecretStr = Field(alias="apiKey")

    with pytest.raises(ConfigError, match="secret field api_key must not declare an alias"):
        Aliased.load(_write(tmp_path, 'apiKey = "x"\n' + VALID), environ={})


def test_secret_environment_variable_name_is_exact(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TRADING_api_key is not a secret setting"):
        _WithSecret.load(
            _write(tmp_path, VALID),
            environ={"TRADING_API_KEY": SECRET_VALUE, "TRADING_api_key": SECRET_VALUE},
        )


# --- reviewed schema --------------------------------------------------------------------------


def test_settings_schema_is_exactly_the_reviewed_fields() -> None:
    """Adding a setting is a reviewed change. Thresholds, risk limits, costs, strategy parameters
    and model ids never belong here (ADR-017, DC12, DC15)."""
    assert set(TradingSettings.model_fields) == {"log"}
    assert set(LogSettings.model_fields) == {"level"}


def _types_in(annotation: object) -> list[object]:
    """The annotation and every type nested in it (`X | None`, `list[X]`, `dict[str, X]`, ...)."""
    return [annotation, *(t for arg in get_args(annotation) for t in _types_in(arg))]


def _nested_secret_fields(model: type[BaseModel], path: str = "") -> list[str]:
    found: list[str] = []
    for name, field in model.model_fields.items():
        for t in _types_in(field.annotation):
            if path and t in (SecretStr, SecretBytes):
                found.append(path + name)
            if isinstance(t, type) and issubclass(t, BaseModel):
                found += _nested_secret_fields(t, f"{path}{name}.")
    return found


def test_nested_secret_finder_sees_optional_and_container_types() -> None:
    class Inner(BaseModel):
        token: SecretStr | None = None

    class Outer(BaseModel):
        maybe: Inner | None = None
        many: list[Inner] = []

    assert sorted(_nested_secret_fields(Outer)) == ["many.token", "maybe.token"]


def test_no_secret_fields_below_the_top_level() -> None:
    """Secrets are read only for top-level fields, so a nested secret could only come from TOML."""
    assert _nested_secret_fields(TradingSettings) == []
