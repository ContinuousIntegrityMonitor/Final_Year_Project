"""Shared fixtures for the skills tests."""

from __future__ import annotations

import pytest

from cim.skills.scoped import scope_available


@pytest.fixture(scope="session")
def needs_scope() -> None:
    if not scope_available():
        pytest.skip("no systemd user session (cannot create transient scopes)")
