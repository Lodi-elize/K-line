from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import SignalThresholds
from app.core.models import KLine, SignalType
from app.core.signal_engine import SignalEngine
from app.services.storage import Storage


def make_rows() -> list[KLine]:
    closes = [10.0] * 10 + [11.0, 12.1, 10.55]
    rows = [
        KLine("600001", f"2026-04-{index + 1:02d}", close - 0.1, close + 0.2, close - 0.2, close, 1000)
        for index, close in enumerate(closes)
    ]
    rows[10] = KLine("600001", "2026-04-11", 10.2, 11.0, 10.2, 11.0, 5000)
    rows[11] = KLine("600001", "2026-04-12", 11.2, 12.1, 11.2, 12.1, 5200)
    rows[12] = KLine("600001", "2026-04-13", 12.0, 12.2, 10.40, 10.55, 2500)
    return rows


def main() -> None:
    engine = SignalEngine(SignalThresholds())
    rows = make_rows()
    signals = [signal for item in engine.annotate(rows) for signal in item.signals]
    assert SignalType.DOUBLE_LIMIT_UP_TEN_MA_PULLBACK in {signal.signal_type for signal in signals}
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
