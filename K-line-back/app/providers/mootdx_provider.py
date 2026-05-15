from __future__ import annotations

from typing import Any

from app.core.models import KLine
from app.providers.base import MarketDataProvider


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
                symbols.append({"symbol": code, "name": str(row.get("name") or code)})
        return symbols

    def daily_bars(self, symbol: str, limit: int = 120) -> list[KLine]:
        frame = self.client.bars(symbol=symbol, frequency=9, offset=limit)
        records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame)
        rows: list[KLine] = []
        for row in records:
            date_value = row.get("date") or row.get("datetime") or row.get("time")
            rows.append(
                KLine(
                    symbol=symbol,
                    date=str(date_value)[:10],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("vol") or row.get("volume") or 0),
                )
            )
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
