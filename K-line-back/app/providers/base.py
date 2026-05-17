from __future__ import annotations

from typing import Protocol

from app.core.models import KLine


class MarketDataProvider(Protocol):
    def list_symbols(self) -> list[dict[str, str]]:
        ...

    def daily_bars(self, symbol: str, limit: int = 120) -> list[KLine]:
        ...

    def intraday_bars(self, symbol: str, limit: int = 240, trade_date: str | None = None) -> list[KLine]:
        ...
