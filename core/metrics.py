"""Pure metric helpers used by UI and automation layers."""

from __future__ import annotations


def profit_rate_per_second(profit: int, elapsed_seconds: int) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    return profit / elapsed_seconds


def project_profit(profit: int, elapsed_seconds: int, future_seconds: int) -> int:
    if elapsed_seconds < 60 or future_seconds <= 0:
        return 0
    return int(profit_rate_per_second(profit, elapsed_seconds) * future_seconds)


def parse_elapsed(elapsed: str) -> int:
    parts = [int(part) for part in elapsed.split(":")]
    if len(parts) != 3:
        raise ValueError(f"Invalid elapsed value: {elapsed!r}")
    hours, minutes, seconds = parts
    return (hours * 3600) + (minutes * 60) + seconds

