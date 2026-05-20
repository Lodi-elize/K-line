from __future__ import annotations

from typing import Literal


HistoryRange = Literal["hourly", "daily", "weekly", "monthly"]

HISTORY_RANGE_LIMITS: dict[HistoryRange, int] = {
    "hourly": 8,
    "daily": 60,
    "weekly": 52,
    "monthly": 24,
}


def normalize_history_range(value: str) -> HistoryRange:
    aliases = {
        "hour": "daily",
        "hourly": "daily",
        "h": "daily",
        "day": "daily",
        "daily": "daily",
        "d": "daily",
        "week": "weekly",
        "weekly": "weekly",
        "w": "weekly",
        "month": "monthly",
        "monthly": "monthly",
        "m": "monthly",
        "year": "monthly",
        "yearly": "monthly",
        "y": "monthly",
    }
    return aliases.get(value.lower(), "daily")  # type: ignore[return-value]


def source_limit_for_range(range_value: HistoryRange) -> int:
    # Keep enough source bars to calculate MA20 before returning the visible candle window.
    if range_value == "hourly":
        return 240
    if range_value == "weekly":
        return 560
    if range_value == "monthly":
        return 960
    return max(160, HISTORY_RANGE_LIMITS[range_value] + 40)
