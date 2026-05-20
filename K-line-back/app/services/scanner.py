from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.stock_scope import is_mainland_hs_symbol
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
    def __init__(
        self,
        provider: MarketDataProvider,
        storage: Storage,
        engine: SignalEngine,
        notifier: Notifier,
        max_symbols: int | None = None,
        status_callback: Callable[[], None] | None = None,
    ) -> None:
        self.provider = provider
        self.storage = storage
        self.engine = engine
        self.notifier = notifier
        self.max_symbols = max_symbols
        self.status_callback = status_callback

    def _emit_status(self) -> None:
        if self.status_callback:
            self.status_callback()

    def run_scan(self, run_id: int | None = None) -> ScanResult:
        run_id = run_id or self.storage.start_scan()
        self._emit_status()
        scanned_count = 0
        signal_count = 0
        warnings: list[str] = []
        try:
            stocks = self.provider.list_symbols()
            stocks = [stock for stock in stocks if is_mainland_hs_symbol(stock.get("symbol"))]
            if self.max_symbols:
                stocks = stocks[: self.max_symbols]
            self.storage.upsert_stocks(stocks)
            for stock in stocks:
                symbol = stock["symbol"]
                try:
                    rows = self.provider.daily_bars(symbol, limit=160)
                    if not rows:
                        continue
                    self.storage.upsert_klines(rows)
                    signals = self.engine.latest_signals(rows)
                    inserted = self.storage.replace_latest_signals(symbol, signals)
                    for signal in signals:
                        self.notifier.publish(signal)
                    signal_count += inserted
                except Exception as exc:
                    warnings.append(f"{symbol} 扫描失败：{exc}")
                finally:
                    scanned_count += 1
                    if scanned_count % 20 == 0:
                        self.storage.update_scan_progress(run_id, scanned_count, signal_count, "；".join(warnings[-3:]))
                        self._emit_status()
            result = ScanResult("success", scanned_count, signal_count, "；".join(warnings))
            self.storage.finish_scan(run_id, result.status, result.scanned_count, result.signal_count, result.message)
            self._emit_status()
            return result
        except Exception as exc:
            message = str(exc)
            self.storage.finish_scan(run_id, "failed", scanned_count, signal_count, message)
            self._emit_status()
            return ScanResult("failed", scanned_count, signal_count, message)
