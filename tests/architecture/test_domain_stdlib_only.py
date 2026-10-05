"""CAPABILITY-MAP hard boundary rule: the domain imports only the standard library and itself.

Import-linter's forbidden contract lists specific libraries; this allowlist check catches any other
third-party package (e.g. a broker SDK or CLI framework) without having to guess its name.
Dynamic imports (importlib.import_module) are not detected by either check.
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_PACKAGE = "trading.domain"


def _module_name(source_root: Path, path: Path) -> str:
    parts = list(path.relative_to(source_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(current_module: str, is_package: bool, level: int, name: str | None) -> str:
    package_parts = current_module.split(".") if is_package else current_module.split(".")[:-1]
    base = package_parts[: len(package_parts) - (level - 1)]
    return ".".join([*base, name] if name else base)


def _imported_modules(source_root: Path, path: Path) -> list[str]:
    current = _module_name(source_root, path)
    is_package = path.name == "__init__.py"
    modules: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                modules.append(_resolve_relative(current, is_package, node.level, node.module))
            elif node.module:
                modules.append(node.module)
    return modules


def _is_allowed(module: str) -> bool:
    if module == DOMAIN_PACKAGE or module.startswith(DOMAIN_PACKAGE + "."):
        return True
    return module.split(".")[0] in sys.stdlib_module_names


def disallowed_domain_imports(source_root: Path) -> list[tuple[str, str]]:
    """Return (file, imported module) pairs in the domain package that are not stdlib or domain."""
    domain_dir = source_root.joinpath(*DOMAIN_PACKAGE.split("."))
    return [
        (str(path.relative_to(source_root)), module)
        for path in sorted(domain_dir.rglob("*.py"))
        for module in _imported_modules(source_root, path)
        if not _is_allowed(module)
    ]


def _make_domain_module(source_root: Path, name: str, source: str) -> None:
    domain_dir = source_root / "trading" / "domain"
    domain_dir.mkdir(parents=True)
    (source_root / "trading" / "__init__.py").write_text("")
    (domain_dir / "__init__.py").write_text("")
    (domain_dir / name).write_text(source)


def test_third_party_import_in_domain_is_reported(tmp_path: Path) -> None:
    _make_domain_module(tmp_path, "bad.py", "import upstox_client\n")

    assert disallowed_domain_imports(tmp_path) == [("trading/domain/bad.py", "upstox_client")]


def test_relative_import_escaping_domain_is_reported(tmp_path: Path) -> None:
    _make_domain_module(tmp_path, "bad.py", "from ..application import ports\n")

    assert disallowed_domain_imports(tmp_path) == [("trading/domain/bad.py", "trading.application")]


def test_stdlib_and_intra_domain_imports_are_allowed(tmp_path: Path) -> None:
    _make_domain_module(
        tmp_path,
        "ok.py",
        "import dataclasses\nfrom decimal import Decimal\nfrom . import other\n"
        "import trading.domain\n",
    )

    assert disallowed_domain_imports(tmp_path) == []


def test_real_domain_imports_only_stdlib_and_domain() -> None:
    assert disallowed_domain_imports(REPO_ROOT / "src") == []
