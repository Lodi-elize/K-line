from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SignalSeverity(str, Enum):
    ENTRY = "entry"
    WATCH = "watch"
    RISK = "risk"
    EXIT = "exit"


class SignalType(str, Enum):
    DOUBLE_LIMIT_UP_TEN_MA_PULLBACK = "double_limit_up_ten_ma_pullback"
    GOLDEN_CROSS = "golden_cross"
    DEATH_CROSS = "death_cross"
    FIVE_MA_PULLBACK_HOLD = "five_ma_pullback_hold"
    FIVE_MA_TURN_UP = "five_ma_turn_up"
    FIVE_MA_TURN_DOWN = "five_ma_turn_down"
    TEN_MA_BREAK_NO_REBOUND = "ten_ma_break_no_rebound"
    TWENTY_MA_BREAK = "twenty_ma_break"
    TWENTY_MA_SUPPORT_TOUCH = "twenty_ma_support_touch"
    TWENTY_MA_RESISTANCE_TOUCH = "twenty_ma_resistance_touch"
    BULLISH_ALIGNMENT = "bullish_alignment"
    BEARISH_ALIGNMENT = "bearish_alignment"


@dataclass(frozen=True)
class KLine:
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    change_pct: float | None = None


@dataclass(frozen=True)
class Signal:
    symbol: str
    trade_date: str
    signal_type: SignalType
    severity: SignalSeverity
    title: str
    description: str
    close: float
    ma5: float | None
    ma10: float | None
    ma20: float | None


@dataclass(frozen=True)
class AnnotatedBar:
    kline: KLine
    ma5: float | None
    ma10: float | None
    ma20: float | None
    signals: list[Signal]
