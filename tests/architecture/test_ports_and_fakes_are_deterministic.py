"""Task 1.6: the market-data ports, the dataset and the test fakes stay deterministic and offline.

Ruff's DC3 ban covers the domain only, so these files are scanned here: no clock, randomness, UUIDs,
environment, processes or file access. Each forbidden pattern is proven to be detected.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED = (
    REPO_ROOT / "src/trading/application/ports.py",
    REPO_ROOT / "src/trading/application/market_dataset.py",
    *sorted((REPO_ROOT / "tests/fakes").glob("*.py")),
)
FORBIDDEN_MODULES = frozenset(
    {
        "random",
        "uuid",
        "secrets",
        "os",
        "sys",
        "time",
        "importlib",
        "pathlib",
        "io",
        "shutil",
        "tempfile",
        "glob",
        "subprocess",
        "socket",
        "urllib",
        "http",
    }
)
FORBIDDEN_ATTRIBUTES = frozenset({"now", "today", "utcnow", "environ", "getenv"})
FORBIDDEN_CALLS = frozenset({"open", "input", "hash", "id", "__import__"})


def violations(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_MODULES:
                found.append(node.module)
            found += [a.name for a in node.names if a.name in FORBIDDEN_ATTRIBUTES]
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            found.append(node.attr)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FORBIDDEN_CALLS
        ):
            found.append(node.func.id)
    return found


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from datetime import datetime\nx = datetime.now()\n", "now"),
        ("import datetime\nx = datetime.date.today()\n", "today"),
        ("import random\n", "random"),
        ("from uuid import uuid4\n", "uuid"),
        ("import os\nx = os.environ['X']\n", "os"),
        ("from os import getenv\n", "getenv"),
        ("import time\n", "time"),
        ("x = open('prices.csv')\n", "open"),
        ("from pathlib import Path\n", "pathlib"),
        ("x = hash('a')\n", "hash"),
        ("x = id(object())\n", "id"),
        ("m = __import__('random')\n", "__import__"),
        ("import importlib\n", "importlib"),
        ("import sys\n", "sys"),
        ("import http.client\n", "http.client"),
    ],
)
def test_each_forbidden_pattern_is_detected(source: str, expected: str) -> None:
    assert expected in violations(source)


def test_scan_covers_the_ports_dataset_and_fakes() -> None:
    names = {path.name for path in SCANNED}

    assert {"ports.py", "market_dataset.py", "fake_market_data.py", "synthetic_market.py"} <= names


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_file_is_deterministic_and_offline(path: Path) -> None:
    assert violations(path.read_text()) == []
