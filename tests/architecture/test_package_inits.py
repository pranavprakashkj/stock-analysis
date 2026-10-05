"""The root and layer `__init__.py` files contain no imports.

Import-linter's layer contract does not govern the root package itself, so `trading/__init__.py`
importing `trading.infrastructure` would keep every contract green while loading infrastructure in
every process that imports the domain. Layer `__init__` files stay import-free for the same reason.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDED_INITS = (
    "src/trading/__init__.py",
    "src/trading/domain/__init__.py",
    "src/trading/application/__init__.py",
    "src/trading/infrastructure/__init__.py",
)


def import_statements(path: Path) -> list[int]:
    """Return line numbers of every import statement anywhere in the file (incl. nested blocks)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    return sorted(
        node.lineno for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)
    )


@pytest.mark.parametrize("relative_path", GUARDED_INITS)
def test_guarded_init_has_no_imports(relative_path: str) -> None:
    assert import_statements(REPO_ROOT / relative_path) == []


def test_checker_finds_top_level_and_nested_imports(tmp_path: Path) -> None:
    init = tmp_path / "__init__.py"
    init.write_text(
        '"""Doc."""\nimport trading.infrastructure\n'
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from . import broker\n"
    )

    assert import_statements(init) == [2, 3, 6]
