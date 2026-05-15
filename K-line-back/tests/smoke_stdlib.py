from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import SignalThresholds
from app.core.models import KLine, SignalType
from app.core.signal_engine import SignalEngine
from app.services.storage import Storage


def make_rows() -> list[KLine]:
    closes = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10.1, 10.2, 10.4, 10.7, 11.1, 11.6, 12.2, 12.8, 13.5, 14.3, 15.0]
    return [
        KLine("600001", f"2026-04-{index + 1:02d}", close - 0.1, close + 0.2, close - 0.2, close, 1000)
        for index, close in enumerate(closes)
    ]


def main() -> None:
    engine = SignalEngine(SignalThresholds())
    rows = make_rows()
    signals = [signal for item in engine.annotate(rows) for signal in item.signals]
    assert SignalType.GOLDEN_CROSS in {signal.signal_type for signal in signals}
    assert SignalThresholds().as_documented_items()

    with TemporaryDirectory() as directory:
        storage = Storage(Path(directory) / "smoke.db")
        storage.upsert_stocks([{"symbol": "600001", "name": "Smoke"}])
        storage.upsert_klines(rows)
        inserted = storage.upsert_signals(signals)
        assert inserted > 0
        for signal in signals:
            storage.record_notification(signal)
        assert storage.latest_signals()
        assert storage.klines_for_symbol("600001")

    print("stdlib smoke passed")


if __name__ == "__main__":
    main()
