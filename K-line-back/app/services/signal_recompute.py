from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.models import Signal, SignalSeverity
from app.core.signal_engine import SignalEngine
from app.services.storage import Storage


@dataclass(frozen=True)
class SignalRecomputeResult:
    status: str
    total_symbols: int
    processed_symbols: int
    signal_count: int
    message: str = ""


class SignalRecomputeService:
    def __init__(
        self,
        storage: Storage,
        engine: SignalEngine,
        status_callback: Callable[[int, int, int, str], None] | None = None,
    ) -> None:
        self.storage = storage
        self.engine = engine
        self.status_callback = status_callback

    def _emit_status(self, total_symbols: int, processed_symbols: int, signal_count: int, message: str = "") -> None:
        if self.status_callback:
            self.status_callback(total_symbols, processed_symbols, signal_count, message)

    def recompute(self) -> SignalRecomputeResult:
        symbols = self.storage.symbols_with_klines()
        total_symbols = len(symbols)
        processed_symbols = 0
        signal_count = 0
        warnings: list[str] = []
        self._emit_status(total_symbols, processed_symbols, signal_count, "正在基于已有K线重算进/离场信号。")
        try:
            for symbol in symbols:
                try:
                    rows = self.storage.daily_klines_for_recompute(symbol)
                    if not rows:
                        continue
                    signals = [
                        signal
                        for item in self.engine.annotate(rows)
                        for signal in item.signals
                        if signal.severity in {SignalSeverity.ENTRY, SignalSeverity.EXIT}
                    ]
                    signal_count += self.storage.replace_entry_exit_signals_for_symbol(symbol, signals)
                except Exception as exc:
                    warnings.append(f"{symbol} 重算失败：{exc}")
                finally:
                    processed_symbols += 1
                    if processed_symbols % 20 == 0 or processed_symbols == total_symbols:
                        self._emit_status(total_symbols, processed_symbols, signal_count, "；".join(warnings[-3:]))
            message = "；".join(warnings)
            return SignalRecomputeResult("success", total_symbols, processed_symbols, signal_count, message)
        except Exception as exc:
            return SignalRecomputeResult("failed", total_symbols, processed_symbols, signal_count, str(exc))
