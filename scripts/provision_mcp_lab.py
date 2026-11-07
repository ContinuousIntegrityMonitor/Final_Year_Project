#!/usr/bin/env python3
"""Validate the recorded MCP lab and print the clean-rebuild plan (T-04)."""

from __future__ import annotations

import argparse

from cim.mcp.lab import check_recorded_lab


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the pinned HexStrike lab topology and print rebuild steps (T-04)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate corpora/mcp pin + topology (also the default action).",
    )
    args = parser.parse_args(argv)
    _ = args.check
    print(check_recorded_lab())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
