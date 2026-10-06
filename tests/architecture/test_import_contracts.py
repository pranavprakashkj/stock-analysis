"""Import-linter contracts (DC1, DC2): each rule is proven to fail on a violating package.

Violating packages are generated in a temporary directory, never inside the repository, so they
cannot enter the production import graph. They are checked against a copy of the repository's real
pyproject.toml, so weakening the real contracts makes these tests fail.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"
LAYERS_CONTRACT = "Layers: infrastructure > application > domain"
DOMAIN_PURITY_CONTRACT = (
    "Domain purity: no dataframe, settings, model, network or database libraries"
)
DOMAIN_NO_IO_CONTRACT = "Domain imports no logging, os or tomllib"
DOMAIN_NO_FILES_CONTRACT = "Domain imports no filesystem or process modules"
APPLICATION_NO_NETWORK_CONTRACT = "Application imports no network libraries"
NO_PROVIDER_SDK_CONTRACT = "No broker or market-data provider SDKs"
ALL_CONTRACTS = (
    LAYERS_CONTRACT,
    DOMAIN_PURITY_CONTRACT,
    DOMAIN_NO_IO_CONTRACT,
    DOMAIN_NO_FILES_CONTRACT,
    APPLICATION_NO_NETWORK_CONTRACT,
    NO_PROVIDER_SDK_CONTRACT,
)
LAYER_PACKAGES = ("domain", "application", "infrastructure")


def _make_project(root: Path, modules: dict[str, str]) -> None:
    """Create a minimal `trading` package under root/src plus extra modules (path -> source)."""
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    package = root / "src" / "trading"
    for layer in LAYER_PACKAGES:
        (package / layer).mkdir(parents=True)
        (package / layer / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    for relative_path, source in modules.items():
        (package / relative_path).write_text(source)


def _lint_imports(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LINT_IMPORTS), "--config", str(root / "pyproject.toml"), "--no-cache"],
        cwd=root,
        env={"PYTHONPATH": str(root / "src"), "PATH": str(LINT_IMPORTS.parent)},
        capture_output=True,
        text=True,
        check=False,
    )


def _broken_contracts(result: subprocess.CompletedProcess[str]) -> set[str]:
    return {
        name
        for name in ALL_CONTRACTS
        if any(name in line and "BROKEN" in line for line in result.stdout.splitlines())
    }


def test_allowed_dependency_directions_pass(tmp_path: Path) -> None:
    _make_project(
        tmp_path,
        {
            "application/uses_domain.py": "import trading.domain\n",
            "infrastructure/uses_application.py": "import trading.application\n",
            "infrastructure/uses_domain.py": "import trading.domain\n",
            "domain/uses_stdlib.py": "import dataclasses\nimport decimal\n",
        },
    )

    result = _lint_imports(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("module_path", "source"),
    [
        ("domain/bad.py", "import trading.application\n"),
        ("domain/bad.py", "import trading.infrastructure\n"),
        ("application/bad.py", "import trading.infrastructure\n"),
    ],
    ids=["domain->application", "domain->infrastructure", "application->infrastructure"],
)
def test_upward_layer_import_breaks_layers_contract(
    tmp_path: Path, module_path: str, source: str
) -> None:
    _make_project(tmp_path, {module_path: source})

    result = _lint_imports(tmp_path)

    assert result.returncode != 0
    assert LAYERS_CONTRACT in _broken_contracts(result), result.stdout + result.stderr


@pytest.mark.parametrize(
    "forbidden_module",
    [
        "polars",
        "pyarrow",
        "pydantic",
        "pydantic_settings",
        "anthropic",
        "laya",
        "torch",
        "transformers",
        "httpx",
        "requests",
        "http",
        "urllib",
        "socket",
        "sqlite3",
    ],
)
def test_domain_importing_forbidden_library_breaks_purity_contract(
    tmp_path: Path, forbidden_module: str
) -> None:
    _make_project(tmp_path, {"domain/bad.py": f"import {forbidden_module}\n"})

    result = _lint_imports(tmp_path)

    assert result.returncode != 0
    assert DOMAIN_PURITY_CONTRACT in _broken_contracts(result), result.stdout + result.stderr


@pytest.mark.parametrize(
    "source",
    ["import logging\n", "import os\n", "from os import environ\n", "import tomllib\n"],
)
def test_domain_logging_environment_or_config_access_breaks_no_io_contract(
    tmp_path: Path, source: str
) -> None:
    _make_project(tmp_path, {"domain/bad.py": source})

    result = _lint_imports(tmp_path)

    assert result.returncode != 0
    assert DOMAIN_NO_IO_CONTRACT in _broken_contracts(result), result.stdout + result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "import pathlib\n",
        "from pathlib import Path\n",
        "import shutil\n",
        "import io\n",
        "import glob\n",
        "import tempfile\n",
        "import subprocess\n",
    ],
)
def test_domain_filesystem_or_process_access_breaks_its_contract(
    tmp_path: Path, source: str
) -> None:
    _make_project(tmp_path, {"domain/bad.py": source})

    result = _lint_imports(tmp_path)

    assert result.returncode != 0
    assert DOMAIN_NO_FILES_CONTRACT in _broken_contracts(result), result.stdout + result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "import http.client\n",
        "import urllib.request\n",
        "import socket\n",
        "import httpx\n",
        "import requests\n",
        "import aiohttp\n",
        "import ssl\n",
        "import urllib3\n",
        "import websockets\n",
        "import smtplib\n",
    ],
)
def test_application_network_access_breaks_its_contract(tmp_path: Path, source: str) -> None:
    _make_project(tmp_path, {"application/bad.py": source})

    result = _lint_imports(tmp_path)

    assert result.returncode != 0
    assert APPLICATION_NO_NETWORK_CONTRACT in _broken_contracts(result), (
        result.stdout + result.stderr
    )


@pytest.mark.parametrize("layer", LAYER_PACKAGES)
@pytest.mark.parametrize(
    "sdk",
    [
        "upstox_client",
        "kiteconnect",
        "SmartApi",
        "nsepython",
        "nsepy",
        "nsetools",
        "jugaad_data",
        "yfinance",
    ],
)
def test_provider_sdk_in_any_layer_breaks_its_contract(
    tmp_path: Path, layer: str, sdk: str
) -> None:
    _make_project(tmp_path, {f"{layer}/bad.py": f"import {sdk}\n"})

    result = _lint_imports(tmp_path)

    assert result.returncode != 0
    assert NO_PROVIDER_SDK_CONTRACT in _broken_contracts(result), result.stdout + result.stderr


def test_application_may_use_libraries_forbidden_in_domain(tmp_path: Path) -> None:
    _make_project(
        tmp_path,
        {
            "application/frames.py": "import polars\n",
            "application/log.py": "import logging\n",
            "application/paths.py": "import pathlib\n",
            "infrastructure/http_client.py": "import httpx\n",
            "infrastructure/settings.py": "import os\nimport tomllib\nimport pydantic_settings\n",
        },
    )

    result = _lint_imports(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_real_repository_keeps_all_contracts() -> None:
    result = subprocess.run(
        [str(LINT_IMPORTS), "--no-cache"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    kept = [line for line in result.stdout.splitlines() if line.endswith(" KEPT")]
    for contract in ALL_CONTRACTS:
        assert any(contract in line for line in kept), (contract, result.stdout)
