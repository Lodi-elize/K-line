from __future__ import annotations

from app.core.models import KLine
from app.providers.base import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self) -> None:
        self._symbols = [
            {"symbol": "600001", "name": "Sample Uptrend"},
            {"symbol": "000001", "name": "Sample Risk"},
        ]

    def list_symbols(self) -> list[dict[str, str]]:
        return self._symbols

    def daily_bars(self, symbol: str, limit: int = 120) -> list[KLine]:
        base = 10.0 if symbol.startswith("6") else 25.0
        direction = 0.16 if symbol.startswith("6") else -0.12
        rows: list[KLine] = []
        for index in range(limit):
            close = round(base + direction * index + (0.15 if index % 7 == 0 else 0), 2)
            rows.append(
                KLine(
                    symbol=symbol,
                    date=f"2026-01-{(index % 28) + 1:02d}" if index < 28 else f"2026-02-{((index - 28) % 28) + 1:02d}",
                    open=round(close - 0.05, 2),
                    high=round(close + 0.2, 2),
                    low=round(close - 0.2, 2),
                    close=close,
                    volume=100000 + index,
                )
            )
        return rows
