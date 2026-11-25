"""Fixtures for every test."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_operator_config(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point CIM_CONFIG at an empty file, so a cim.toml on the developer's machine never
    changes what a test sees. A test that wants a config passes --config or its own env."""
    empty = tmp_path_factory.mktemp("cim-config") / "cim.toml"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("CIM_CONFIG", str(empty))
