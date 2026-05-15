from __future__ import annotations

from dataclasses import dataclass

from app.core.signal_engine import SignalEngine
from app.providers.base import MarketDataProvider
from app.services.notifier import Notifier
from app.services.storage import Storage


@dataclass(frozen=True)
class ScanResult:
    status: str
    scanned_count: int
    signal_count: int
    message: str = ""


class ScannerService:
    def __init__(self, provider: MarketDataProvider, storage: Storage, engine: SignalEngine, notifier: Notifier, max_symbols: int | None = None) -> None:
        self.provider = provider
        self.storage = storage
        self.engine = engine
        self.notifier = notifier
        self.max_symbols = max_symbols

    def run_scan(self) -> ScanResult:
        run_id = self.storage.start_scan()
        scanned_count = 0
        signal_count = 0
        try:
            stocks = self.provider.list_symbols()
            if self.max_symbols:
                stocks = stocks[: self.max_symbols]
            self.storage.upsert_stocks(stocks)
            for stock in stocks:
                symbol = stock["symbol"]
                rows = self.provider.daily_bars(symbol, limit=160)
                if not rows:
                    continue
                self.storage.upsert_klines(rows)
                signals = self.engine.latest_signals(rows)
                inserted = self.storage.upsert_signals(signals)
                for signal in signals:
                    self.notifier.publish(signal)
                scanned_count += 1
                signal_count += inserted
            result = ScanResult("success", scanned_count, signal_count)
            self.storage.finish_scan(run_id, result.status, result.scanned_count, result.signal_count, result.message)
            return result
        except Exception as exc:
            message = str(exc)
            self.storage.finish_scan(run_id, "failed", scanned_count, signal_count, message)
            return ScanResult("failed", scanned_count, signal_count, message)
