"""Shared configuration helpers (border file — both review)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CimConfig:
    """Minimal config loaded from environment / defaults."""

    log_level: str = "INFO"
    store_path: Path = Path("logs/cim-store.sqlite")


def load_config() -> CimConfig:
    """Return default config (env wiring lands with later tasks)."""
    return CimConfig()
