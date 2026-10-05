"""DC3: no wall-clock reads or module-level randomness in `trading.domain` (Ruff TID251).

The bans live in the root pyproject.toml, scoped to the domain by a negated per-file-ignore, so that
both default config discovery and an explicit `--config pyproject.toml` apply them. Each banned
call is written into a temporary copy of the project that uses the repository's real pyproject.toml.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUFF = Path(sys.executable).parent / "ruff"
RUFF_CONFIG_NAMES = ("ruff.toml", ".ruff.toml", "pyproject.toml")
INVOCATIONS: dict[str, list[str]] = {
    "default-discovery": [],
    "explicit-config": ["--config", "pyproject.toml"],
}


def _make_project(root: Path, relative_path: str, source: str) -> None:
    shutil.copy(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)


def _ruff_check(root: Path, extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUFF), "check", ".", "--no-cache", "--output-format", "concise", *extra_args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("invocation", INVOCATIONS)
@pytest.mark.parametrize(
    "source",
    [
        "import datetime\n\nx = datetime.datetime.now()\n",
        "from datetime import datetime\n\nx = datetime.now()\n",
        "import datetime\n\nx = datetime.datetime.utcnow()\n",
        "import datetime\n\nx = datetime.datetime.today()\n",
        "import datetime\n\nx = datetime.date.today()\n",
        "import time\n\nx = time.time()\n",
        "import time\n\nx = time.time_ns()\n",
        "import random\n",
        "from random import choice\n",
    ],
    ids=[
        "datetime.now",
        "from-import datetime.now",
        "datetime.utcnow",
        "datetime.today",
        "date.today",
        "time.time",
        "time.time_ns",
        "import random",
        "from random import",
    ],
)
def test_banned_clock_or_randomness_in_domain_is_reported(
    tmp_path: Path, source: str, invocation: str
) -> None:
    _make_project(tmp_path, "src/trading/domain/sub/bad.py", source)

    result = _ruff_check(tmp_path, INVOCATIONS[invocation])

    assert result.returncode != 0
    assert "TID251" in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("invocation", INVOCATIONS)
def test_same_calls_outside_domain_are_not_banned(tmp_path: Path, invocation: str) -> None:
    _make_project(
        tmp_path,
        "src/trading/application/clock_user.py",
        "import datetime\nimport random\n\nx = datetime.datetime.now()\ny = random.random()\n",
    )

    result = _ruff_check(tmp_path, INVOCATIONS[invocation])

    assert "TID251" not in result.stdout, result.stdout + result.stderr


def test_clean_domain_module_passes(tmp_path: Path) -> None:
    _make_project(
        tmp_path,
        "src/trading/domain/clean.py",
        "import datetime\n\nEPOCH = datetime.date(2010, 1, 1)\n",
    )

    result = _ruff_check(tmp_path, [])

    assert result.returncode == 0, result.stdout + result.stderr


def test_no_nested_ruff_configuration_can_shadow_the_root_config() -> None:
    # Ruff uses the closest config file without merging, so a nested config would silently replace
    # the root bans for its subtree. All Ruff configuration must live in the root pyproject.toml.
    nested = [
        str(path.relative_to(REPO_ROOT))
        for name in RUFF_CONFIG_NAMES
        for directory in ("src", "tests")
        for path in (REPO_ROOT / directory).rglob(name)
    ]

    assert nested == []
