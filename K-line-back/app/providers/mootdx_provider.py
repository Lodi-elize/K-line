from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.models import KLine
from app.core.stock_scope import is_mainland_hs_symbol
from app.providers.base import MarketDataProvider


SZ_MARKET = 0
SH_MARKET = 1


def _clean_stock_name(value: object, fallback: str) -> str:
    cleaned = "".join(char for char in str(value or "").replace("\ufffd", "") if char.isprintable()).strip()
    return cleaned or fallback


def _symbol_belongs_to_market(symbol: str, market: int) -> bool:
    if market == SZ_MARKET:
        return symbol.startswith(("00", "30"))
    if market == SH_MARKET:
        return symbol.startswith(("60", "68", "90"))
    return False


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
        symbols: dict[str, str] = {}
        loaded_market = False
        stocks = getattr(self.client, "stocks", None)
        if callable(stocks):
            for market in (SZ_MARKET, SH_MARKET):
                try:
                    data = stocks(market=market)
                except TypeError:
                    data = stocks(market)
                except Exception:
                    continue
                loaded_market = True
                for row in self._records(data):
                    code = str(row.get("code") or row.get("symbol") or "").zfill(6)
                    if is_mainland_hs_symbol(code) and _symbol_belongs_to_market(code, market):
                        symbols[code] = _clean_stock_name(row.get("name"), code)
        if not loaded_market:
            data = self._call_first_available(["stock_all", "stocks"])
            if data is None:
                return []
            for row in self._records(data):
                code = str(row.get("code") or row.get("symbol") or "").zfill(6)
                if is_mainland_hs_symbol(code):
                    symbols.setdefault(code, _clean_stock_name(row.get("name"), code))
        return [{"symbol": symbol, "name": name} for symbol, name in sorted(symbols.items())]

    def daily_bars(self, symbol: str, limit: int = 120) -> list[KLine]:
        frame = self.client.bars(symbol=symbol, frequency=9, offset=limit)
        return self._frame_to_klines(symbol, frame)

    def intraday_bars(self, symbol: str, limit: int = 240, trade_date: str | None = None) -> list[KLine]:
        if trade_date:
            frame = self.client.minutes(symbol=symbol, date=trade_date.replace("-", "")[:8])
        else:
            frame = self.client.minute(symbol=symbol)
        return self._frame_to_klines(symbol, frame, trade_date=trade_date, synthesize_minutes=True)[-limit:]

    def _frame_to_klines(self, symbol: str, frame: Any, trade_date: str | None = None, synthesize_minutes: bool = False) -> list[KLine]:
        records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame)
        minute_times = _trading_minute_labels(trade_date, len(records)) if synthesize_minutes else []
        rows: list[KLine] = []
        for index, row in enumerate(records):
            date_value = row.get("datetime") or row.get("date") or row.get("time") or (minute_times[index] if index < len(minute_times) else "")
            open_price = float(row.get("open") or row.get("price") or row.get("close"))
            high = float(row.get("high") or row.get("price") or row.get("close") or open_price)
            low = float(row.get("low") or row.get("price") or row.get("close") or open_price)
            close = float(row.get("close") or row.get("price") or open_price)
            kline = _normalized_kline(
                symbol=symbol,
                date=_format_datetime_value(date_value),
                open_price=open_price,
                high=high,
                low=low,
                close=close,
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

    def _records(self, data: Any) -> list[dict[str, Any]]:
        return data.to_dict("records") if hasattr(data, "to_dict") else list(data)


def _format_datetime_value(value: object) -> str:
    text = str(value or "")[:16]
    if "T" in text:
        text = text.replace("T", " ")
    return text


def _trading_minute_labels(trade_date: str | None, count: int) -> list[str]:
    day = (trade_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    morning = _minute_range(f"{day} 09:30", 120)
    afternoon = _minute_range(f"{day} 13:00", 120)
    labels = morning + afternoon
    if count <= len(labels):
        return labels[:count]
    return labels + _minute_range(f"{day} 15:00", count - len(labels))


def _minute_range(start: str, count: int) -> list[str]:
    current = datetime.fromisoformat(start)
    return [(current + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M") for index in range(count)]
