import importlib

import pytest


@pytest.mark.parametrize("name", ["control", "eval", "gateway", "perfmodel", "workloads"])
def test_imports(name: str) -> None:
    importlib.import_module(name)
