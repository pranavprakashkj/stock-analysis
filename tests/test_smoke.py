import importlib

import pytest

LAYERS = ("trading.domain", "trading.application", "trading.infrastructure")


def test_root_package_imports() -> None:
    assert importlib.import_module("trading").__name__ == "trading"


@pytest.mark.parametrize("module_name", LAYERS)
def test_layer_package_imports(module_name: str) -> None:
    assert importlib.import_module(module_name).__name__ == module_name
