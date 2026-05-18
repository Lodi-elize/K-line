from __future__ import annotations

from datetime import datetime, timedelta

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
            if symbol.startswith("6") and index >= limit - 3:
                setup_closes = [11.0, 12.1, 10.55]
                close = setup_closes[index - (limit - 3)]
                volume = [5000, 5200, 2500][index - (limit - 3)]
                low = 10.4 if index == limit - 1 else close - 0.2
            else:
                close = round(base + (0 if symbol.startswith("6") else direction * index) + (0.15 if index % 7 == 0 and not symbol.startswith("6") else 0), 2)
                volume = 100000 + index
                low = close - 0.2
            rows.append(
                KLine(
                    symbol=symbol,
                    date=(datetime(2026, 1, 1) + timedelta(days=index)).strftime("%Y-%m-%d"),
                    open=round(close - 0.05, 2),
                    high=round(close + 0.2, 2),
                    low=round(low, 2),
                    close=close,
                    volume=volume,
                )
            )
        return rows

    def intraday_bars(self, symbol: str, limit: int = 240, trade_date: str | None = None) -> list[KLine]:
        base = 10.0 if symbol.startswith("6") else 25.0
        day = trade_date or "2026-02-28"
        start = datetime.fromisoformat(f"{day[:10]} 09:30")
        rows: list[KLine] = []
        for index in range(min(limit, 240)):
            timestamp = start + timedelta(minutes=index)
            close = round(base + 0.01 * index + (0.03 if index % 17 == 0 else 0), 2)
            rows.append(
                KLine(
                    symbol=symbol,
                    date=timestamp.strftime("%Y-%m-%d %H:%M"),
                    open=round(close - 0.02, 2),
                    high=round(close + 0.05, 2),
                    low=round(close - 0.05, 2),
                    close=close,
                    volume=1000 + index,
                )
            )
        return rows
