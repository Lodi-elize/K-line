from __future__ import annotations

from app.core.config import SignalThresholds
from app.core.models import KLine, SignalType
from app.core.signal_engine import SignalEngine


def make_rows(closes: list[float], symbol: str = "600001") -> list[KLine]:
    rows: list[KLine] = []
    for index, close in enumerate(closes):
        rows.append(
            KLine(
                symbol=symbol,
                date=f"2026-03-{index + 1:02d}",
                open=close - 0.1,
                high=close + 0.2,
                low=close - 0.2,
                close=close,
                volume=1000,
            )
        )
    return rows


def signal_types(rows: list[KLine]) -> set[SignalType]:
    annotated = SignalEngine(SignalThresholds()).annotate(rows)
    return {signal.signal_type for bar in annotated for signal in bar.signals}


def test_detects_golden_and_bullish_alignment() -> None:
    closes = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10.1, 10.2, 10.4, 10.7, 11.1, 11.6, 12.2, 12.8, 13.5, 14.3, 15.0]
    found = signal_types(make_rows(closes))
    assert SignalType.GOLDEN_CROSS in found
    assert SignalType.BULLISH_ALIGNMENT in found


def test_detects_death_and_bearish_alignment() -> None:
    closes = [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 19.8, 19.5, 19.1, 18.6, 18.0, 17.3, 16.5, 15.8, 15.0, 14.1, 13.3]
    found = signal_types(make_rows(closes))
    assert SignalType.DEATH_CROSS in found
    assert SignalType.BEARISH_ALIGNMENT in found


def test_detects_five_ma_pullback_hold() -> None:
    rows = make_rows([10, 10.2, 10.4, 10.6, 10.8, 11.0, 11.2, 11.4, 11.6, 11.8, 12.0, 12.2, 12.1])
    rows[-1] = KLine("600001", rows[-1].date, 12.0, 12.28, 11.95, 12.24, 1000)
    found = signal_types(rows)
    assert SignalType.FIVE_MA_PULLBACK_HOLD in found


def test_detects_ten_and_twenty_ma_breaks() -> None:
    closes = [20.0] * 20 + [19.0]
    found = signal_types(make_rows(closes))
    assert SignalType.TEN_MA_BREAK_NO_REBOUND in found
    assert SignalType.TWENTY_MA_BREAK in found


def test_config_items_are_documented() -> None:
    items = SignalThresholds().as_documented_items()
    assert {item["key"] for item in items} >= {"touch_tolerance_pct", "arrangement_spread_pct"}
    assert all(item["description"] and item["unit"] for item in items)
