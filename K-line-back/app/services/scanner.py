from __future__ import annotations

from dataclasses import dataclass

from app.core.signal_engine import SignalEngine
from app.providers.akshare_board_provider import AkshareBoardProvider
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
        board_provider: AkshareBoardProvider | None = None,
    ) -> None:
        self.provider = provider
        self.storage = storage
        self.engine = engine
        self.notifier = notifier
        self.max_symbols = max_symbols
        self.board_provider = board_provider

    def run_scan(self) -> ScanResult:
        run_id = self.storage.start_scan()
        scanned_count = 0
        signal_count = 0
        warnings: list[str] = []
        try:
            stocks = self.provider.list_symbols()
            if self.max_symbols:
                stocks = stocks[: self.max_symbols]
            self.storage.upsert_stocks(stocks)
            if self.board_provider:
                try:
                    members = self.board_provider.concept_members()
                    self.storage.replace_concept_modules([(member.symbol, member.board_name) for member in members])
                except Exception as exc:
                    warnings.append(f"概念模块同步失败，已跳过：{exc}")
            for stock in stocks:
                symbol = stock["symbol"]
                try:
                    rows = self.provider.daily_bars(symbol, limit=160)
                    if not rows:
                        continue
                    self.storage.upsert_klines(rows)
                    signals = self.engine.latest_signals(rows)
                    inserted = self.storage.upsert_signals(signals)
                    for signal in signals:
                        self.notifier.publish(signal)
                    signal_count += inserted
                except Exception as exc:
                    warnings.append(f"{symbol} 扫描失败：{exc}")
                finally:
                    scanned_count += 1
                    if scanned_count % 20 == 0:
                        self.storage.update_scan_progress(run_id, scanned_count, signal_count, "；".join(warnings[-3:]))
            result = ScanResult("success", scanned_count, signal_count, "；".join(warnings))
            self.storage.finish_scan(run_id, result.status, result.scanned_count, result.signal_count, result.message)
            return result
        except Exception as exc:
            message = str(exc)
            self.storage.finish_scan(run_id, "failed", scanned_count, signal_count, message)
            return ScanResult("failed", scanned_count, signal_count, message)
