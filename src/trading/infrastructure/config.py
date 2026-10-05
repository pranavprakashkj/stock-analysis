"""Process configuration (task 1.3; ADR-010: Pydantic v2 + pydantic-settings, TOML validated).

- Non-secret settings come only from one TOML file, so a run's configuration is fixed by that file.
- Secrets come only from environment variables `TRADING_<FIELD>` for top-level `SecretStr` fields
  without aliases. A secret in the TOML file, an empty secret, or a `TRADING_` variable that names
  no secret field is rejected. Phase 1 defines no secret settings.
- Every field is required; unknown keys, including keys that differ only in case, are rejected;
  nothing falls back to a default.
- Error messages name the file and the location of each problem, never the offending value, and
  carry no underlying exception (those embed input values).

Thresholds, risk limits, costs, strategy parameters and model ids never belong here: thresholds
come only from the locked-config loader (ADR-017 §4, DC15), model ids from model config (DC12).
"""

import os
import tomllib
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self, get_args

from pydantic import BaseModel, ConfigDict, SecretBytes, SecretStr, ValidationError
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from trading.infrastructure.logging import LogLevel

ENV_PREFIX = "TRADING_"
# When set, pydantic-settings logs every raw source value at DEBUG, secrets included.
_PYDANTIC_SETTINGS_DEBUG = "PYDANTIC_SETTINGS_DEBUG"


class ConfigError(Exception):
    """Configuration is missing or invalid. The message never contains configured values."""


class LogSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    level: LogLevel


@dataclass(frozen=True, slots=True)
class _LoadRequest:
    toml_file: Path
    environ: Mapping[str, str]


# Carries the arguments of `load` into `settings_customise_sources`, which pydantic-settings calls
# as a classmethod without access to them.
_LOAD_REQUEST: ContextVar[_LoadRequest | None] = ContextVar("load_request", default=None)


def _env_name(field_name: str) -> str:
    return ENV_PREFIX + field_name.upper()


def _secret_fields(settings_cls: type[BaseSettings]) -> frozenset[str]:
    """Top-level secret fields. `SecretBytes` counts as secret so it can never come from TOML."""
    secret_types = (SecretStr, SecretBytes)
    names = frozenset(
        name
        for name, field in settings_cls.model_fields.items()
        if any(t in secret_types for t in (field.annotation, *get_args(field.annotation)))
    )
    for name in sorted(names):
        field = settings_cls.model_fields[name]
        if field.alias is not None or field.validation_alias is not None:
            # The TOML source matches keys by alias, which the name-based checks would miss.
            raise ConfigError(f"secret field {name} must not declare an alias")
    return names


class _SecretsFromEnvironment(PydanticBaseSettingsSource):
    """Reads secret fields from `TRADING_<FIELD>`; refuses any other `TRADING_` variable."""

    def __init__(self, settings_cls: type[BaseSettings], environ: Mapping[str, str]) -> None:
        super().__init__(settings_cls)
        self._environ = environ

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return self._environ.get(_env_name(field_name)), field_name, False

    def __call__(self) -> dict[str, Any]:
        secrets = _secret_fields(self.settings_cls)
        allowed = {_env_name(name) for name in secrets}
        for key in sorted(self._environ):
            if key.startswith(ENV_PREFIX) and key not in allowed:
                raise ConfigError(
                    f"environment variable {key} is not a secret setting; "
                    "non-secret settings come only from the config file"
                )
        values: dict[str, Any] = {}
        for name in sorted(secrets):
            value, _, _ = self.get_field_value(self.settings_cls.model_fields[name], name)
            if value == "":
                raise ConfigError(f"environment variable {_env_name(name)} is empty")
            if value is not None:
                values[name] = value
        return values


class _TomlWithoutSecrets(TomlConfigSettingsSource):
    """The TOML file source, refusing any secret field."""

    def __call__(self) -> dict[str, Any]:
        values = super().__call__()
        leaked = sorted(_secret_fields(self.settings_cls) & values.keys())
        if leaked:
            names = ", ".join(f"{name} may come only from the environment" for name in leaked)
            raise ConfigError(f"{self.toml_file_path}: {names} ({ENV_PREFIX}<NAME>)")
        return values


def _describe(path: Path, error: ValidationError) -> str:
    problems = [
        f"  {'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors(include_url=False, include_context=False, include_input=False)
    ]
    return "\n".join([f"invalid configuration in {path}:", *problems])


class TradingSettings(BaseSettings):
    """Typed process settings. Construct only with `TradingSettings.load`."""

    model_config = SettingsConfigDict(extra="forbid", frozen=True, strict=True, case_sensitive=True)

    log: LogSettings

    @classmethod
    def load(cls, path: Path, *, environ: Mapping[str, str]) -> Self:
        """Load from the TOML file at `path` plus secrets from `environ`; raise ConfigError.

        The process environment is read only to refuse `PYDANTIC_SETTINGS_DEBUG`, which
        pydantic-settings reads from `os.environ` itself."""
        if os.environ.get(_PYDANTIC_SETTINGS_DEBUG, ""):
            raise ConfigError(
                f"unset {_PYDANTIC_SETTINGS_DEBUG}: it makes pydantic-settings log raw "
                "configuration values, including secrets"
            )
        path = path.expanduser()  # the TOML source expands "~" too; check the same file it reads
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
        token = _LOAD_REQUEST.set(_LoadRequest(path, environ))
        try:
            return cls()
        except OSError as error:
            message = f"cannot read config file {path}: {error.strerror}"
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            message = f"{path}: invalid TOML: {error}"
        except ValidationError as error:
            message = _describe(path, error)
        finally:
            _LOAD_REQUEST.reset(token)
        # Raised outside the handlers, so the original error (which embeds input values, possibly
        # secrets) is neither the cause nor the context of the ConfigError.
        raise ConfigError(message)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Only two sources: secrets from the environment and everything else from the TOML file.
        Constructor arguments, `.env` files and secret directories are not read. Refusing
        construction outside `load` guards against accidental use; it is not a security boundary
        (pydantic-settings' private `_build_sources` argument bypasses it)."""
        request = _LOAD_REQUEST.get()
        if request is None:
            raise ConfigError(f"construct settings with {cls.__name__}.load(path, environ=...)")
        return (
            _SecretsFromEnvironment(settings_cls, request.environ),
            _TomlWithoutSecrets(settings_cls, toml_file=request.toml_file),
        )
