from __future__ import annotations

from typing import Literal


HistoryRange = Literal["daily", "monthly", "yearly"]

HISTORY_RANGE_LIMITS: dict[HistoryRange, int] = {
    "daily": 1,
    "monthly": 22,
    "yearly": 250,
}


def normalize_history_range(value: str) -> HistoryRange:
    aliases = {
        "day": "daily",
        "daily": "daily",
        "d": "daily",
        "month": "monthly",
        "monthly": "monthly",
        "m": "monthly",
        "year": "yearly",
        "yearly": "yearly",
        "y": "yearly",
    }
    return aliases.get(value.lower(), "daily")  # type: ignore[return-value]


def source_limit_for_range(range_value: HistoryRange) -> int:
    # Keep enough daily history to calculate MA20 before returning the short display window.
    return max(160, HISTORY_RANGE_LIMITS[range_value] + 30)
