"""Shared fixtures for the skills tests."""

from __future__ import annotations

import pytest

from cim.skills.scoped import scope_available


@pytest.fixture(scope="session")
def needs_scope() -> None:
    if not scope_available():
        pytest.skip("no systemd user session (cannot create transient scopes)")


@pytest.fixture(scope="session")
def needs_tracer(needs_scope: None) -> None:
    from cim.skills.collector import tracer_available

    if not tracer_available():
        pytest.skip("strace is not installed or may not trace a child here")
