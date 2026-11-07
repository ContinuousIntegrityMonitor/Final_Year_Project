"""Import smoke: every cim submodule must import cleanly."""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "cim",
    "cim.cli",
    "cim.common",
    "cim.common.config",
    "cim.common.chain",
    "cim.common.schema",
    "cim.common.store",
    "cim.mcp",
    "cim.skills",
    "cim.correlation",
    "cim.scanners",
    "cim.scanners.mcp",
    "cim.scanners.skills",
    "cim.attestation",
    "cim.attestation.hostagent",
    "cim.attestation.verifier",
    "cim.adjudicator",
    "cim.dashboard",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_import_module(module_name: str) -> None:
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_version_string() -> None:
    import cim

    assert cim.__version__
