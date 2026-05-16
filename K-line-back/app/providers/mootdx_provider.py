from __future__ import annotations

from typing import Any

from app.core.models import KLine
from app.providers.base import MarketDataProvider


def _clean_stock_name(value: object, fallback: str) -> str:
    cleaned = "".join(char for char in str(value or "").replace("\ufffd", "") if char.isprintable()).strip()
    return cleaned or fallback


def _normalized_kline(symbol: str, date: str, open_price: float, high: float, low: float, close: float, volume: float) -> KLine | None:
    prices = [open_price, high, low, close]
    if any(price <= 0 for price in prices):
        return None
    normalized_high = max(prices)
    normalized_low = min(prices)
    return KLine(symbol=symbol, date=date, open=open_price, high=normalized_high, low=normalized_low, close=close, volume=volume)


class MootdxProvider(MarketDataProvider):
    def __init__(self) -> None:
        try:
            from mootdx.quotes import Quotes
        except ImportError as exc:
            raise RuntimeError("mootdx is not installed. Install K-line-back requirements first.") from exc
        self.client = Quotes.factory(market="std")

    def list_symbols(self) -> list[dict[str, str]]:
        data = self._call_first_available(["stocks", "stock_all"])
        if data is None:
            return []
        records = data.to_dict("records") if hasattr(data, "to_dict") else list(data)
        symbols: list[dict[str, str]] = []
        for row in records:
            code = str(row.get("code") or row.get("symbol") or "").zfill(6)
            if code and (code.startswith(("0", "3", "6"))):
                symbols.append({"symbol": code, "name": _clean_stock_name(row.get("name"), code)})
        return symbols

    def daily_bars(self, symbol: str, limit: int = 120) -> list[KLine]:
        frame = self.client.bars(symbol=symbol, frequency=9, offset=limit)
        records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame)
        rows: list[KLine] = []
        for row in records:
            date_value = row.get("date") or row.get("datetime") or row.get("time")
            kline = _normalized_kline(
                symbol=symbol,
                date=str(date_value)[:10],
                open_price=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("vol") or row.get("volume") or 0),
            )
            if kline is not None:
                rows.append(kline)
        return rows

    def _call_first_available(self, names: list[str]) -> Any | None:
        for name in names:
            method = getattr(self.client, name, None)
            if callable(method):
                try:
                    return method()
                except TypeError:
                    continue
        return None
