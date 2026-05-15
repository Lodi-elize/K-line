from __future__ import annotations

from collections import defaultdict

from app.core.config import SignalThresholds
from app.core.models import AnnotatedBar, KLine, Signal, SignalSeverity, SignalType


def _moving_average(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    rolling_sum = 0.0
    for index, value in enumerate(values):
        rolling_sum += value
        if index >= window:
            rolling_sum -= values[index - window]
        result.append(round(rolling_sum / window, 4) if index >= window - 1 else None)
    return result


def _ratio_diff(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous


def _crossed_above(prev_short: float | None, prev_long: float | None, short: float | None, long: float | None) -> bool:
    return prev_short is not None and prev_long is not None and short is not None and long is not None and prev_short <= prev_long and short > long


def _crossed_below(prev_short: float | None, prev_long: float | None, short: float | None, long: float | None) -> bool:
    return prev_short is not None and prev_long is not None and short is not None and long is not None and prev_short >= prev_long and short < long


class SignalEngine:
    def __init__(self, thresholds: SignalThresholds) -> None:
        self.thresholds = thresholds

    def annotate(self, klines: list[KLine]) -> list[AnnotatedBar]:
        ordered = sorted(klines, key=lambda row: row.date)
        closes = [row.close for row in ordered]
        ma5 = _moving_average(closes, 5)
        ma10 = _moving_average(closes, 10)
        ma20 = _moving_average(closes, 20)
        signals_by_date: dict[str, list[Signal]] = defaultdict(list)
        for index, row in enumerate(ordered):
            signals_by_date[row.date].extend(self._signals_for_index(ordered, ma5, ma10, ma20, index))
        return [
            AnnotatedBar(kline=row, ma5=ma5[index], ma10=ma10[index], ma20=ma20[index], signals=signals_by_date[row.date])
            for index, row in enumerate(ordered)
        ]

    def latest_signals(self, klines: list[KLine]) -> list[Signal]:
        annotated = self.annotate(klines)
        return annotated[-1].signals if annotated else []

    def _signals_for_index(
        self,
        rows: list[KLine],
        ma5: list[float | None],
        ma10: list[float | None],
        ma20: list[float | None],
        index: int,
    ) -> list[Signal]:
        if index == 0:
            return []
        row = rows[index]
        previous = rows[index - 1]
        current_ma5 = ma5[index]
        current_ma10 = ma10[index]
        current_ma20 = ma20[index]
        previous_ma5 = ma5[index - 1]
        previous_ma10 = ma10[index - 1]
        previous_ma20 = ma20[index - 1]
        signals: list[Signal] = []

        if _crossed_above(previous_ma5, previous_ma10, current_ma5, current_ma10):
            signals.append(self._signal(row, SignalType.GOLDEN_CROSS, SignalSeverity.ENTRY, "5日线金叉", "5日均线上穿10日均线，属于严格短线进场信号。", current_ma5, current_ma10, current_ma20))

        if _crossed_below(previous_ma5, previous_ma10, current_ma5, current_ma10):
            signals.append(self._signal(row, SignalType.DEATH_CROSS, SignalSeverity.EXIT, "5日线死叉", "5日均线下穿10日均线，属于离场/风险信号。", current_ma5, current_ma10, current_ma20))

        # "5日线回踩不破" is treated strictly: price must approach the 5MA, avoid a meaningful break, and close back above it.
        if self._is_five_ma_pullback_hold(row, previous, current_ma5, current_ma10, previous_ma5):
            signals.append(self._signal(row, SignalType.FIVE_MA_PULLBACK_HOLD, SignalSeverity.ENTRY, "回踩5日线不破", "股价回踩接近5日均线但未有效跌破，同时5日线仍在10日线上方。", current_ma5, current_ma10, current_ma20))

        # "拐头向上/向下" uses slope over the configured lookback so a one-day wiggle is not enough.
        if self._ma_turns_up(ma5, index):
            signals.append(self._signal(row, SignalType.FIVE_MA_TURN_UP, SignalSeverity.WATCH, "5日线拐头向上", "5日均线斜率超过严格上拐阈值，可作为观察信号。", current_ma5, current_ma10, current_ma20))

        if self._ma_turns_down(ma5, index):
            signals.append(self._signal(row, SignalType.FIVE_MA_TURN_DOWN, SignalSeverity.RISK, "5日线拐头向下", "5日均线斜率超过严格下拐阈值，提示短线走弱。", current_ma5, current_ma10, current_ma20))

        # The 10MA is the stop/control line: a break with no rebound is a risk signal.
        if self._breaks_without_rebound(row.close, previous.close, current_ma10, previous_ma10):
            signals.append(self._signal(row, SignalType.TEN_MA_BREAK_NO_REBOUND, SignalSeverity.RISK, "跌破10日线且无反抽", "收盘跌破10日均线，且没有恢复到足以确认反抽的幅度。", current_ma5, current_ma10, current_ma20))

        if self._crossed_line_down(previous.close, previous_ma20, row.close, current_ma20):
            signals.append(self._signal(row, SignalType.TWENTY_MA_BREAK, SignalSeverity.EXIT, "跌破20日生命线", "收盘下穿20日均线，属于严格生命线离场信号。", current_ma5, current_ma10, current_ma20))

        # 20MA support/resistance annotations require a close on the expected side plus an intraday touch near the line.
        support_resistance = self._twenty_ma_touch(row, current_ma20)
        if support_resistance is not None:
            signals.append(self._signal(row, support_resistance[0], support_resistance[1], support_resistance[2], support_resistance[3], current_ma5, current_ma10, current_ma20))

        # Alignment signals require both ordering and minimum spread so flat, tangled averages do not trigger.
        if self._bullish_alignment(ma5, ma10, ma20, index):
            signals.append(self._signal(row, SignalType.BULLISH_ALIGNMENT, SignalSeverity.WATCH, "均线多头排列", "5日线 > 10日线 > 20日线，且发散和上行确认通过。", current_ma5, current_ma10, current_ma20))

        if self._bearish_alignment(ma5, ma10, ma20, index):
            signals.append(self._signal(row, SignalType.BEARISH_ALIGNMENT, SignalSeverity.RISK, "均线空头排列", "20日线 > 10日线 > 5日线，且发散和下行确认通过。", current_ma5, current_ma10, current_ma20))

        return signals

    def _signal(
        self,
        row: KLine,
        signal_type: SignalType,
        severity: SignalSeverity,
        title: str,
        description: str,
        ma5: float | None,
        ma10: float | None,
        ma20: float | None,
    ) -> Signal:
        return Signal(row.symbol, row.date, signal_type, severity, title, description, row.close, ma5, ma10, ma20)

    def _is_five_ma_pullback_hold(self, row: KLine, previous: KLine, ma5: float | None, ma10: float | None, previous_ma5: float | None) -> bool:
        if ma5 is None or ma10 is None or previous_ma5 is None or ma5 <= ma10:
            return False
        low_distance = abs(row.low - ma5) / ma5
        held_line = row.low >= ma5 * (1 - self.thresholds.break_tolerance_pct)
        recovered = row.close > ma5 and row.close >= previous.close
        trend_ok = _ratio_diff(ma5, previous_ma5)
        return low_distance <= self.thresholds.touch_tolerance_pct and held_line and recovered and trend_ok is not None and trend_ok >= 0

    def _ma_turns_up(self, ma_values: list[float | None], index: int) -> bool:
        lookback = self.thresholds.slope_lookback_days
        if index < lookback:
            return False
        slope = _ratio_diff(ma_values[index], ma_values[index - lookback])
        previous_slope = _ratio_diff(ma_values[index - 1], ma_values[index - lookback])
        return slope is not None and previous_slope is not None and slope >= self.thresholds.upward_slope_pct and previous_slope <= slope

    def _ma_turns_down(self, ma_values: list[float | None], index: int) -> bool:
        lookback = self.thresholds.slope_lookback_days
        if index < lookback:
            return False
        slope = _ratio_diff(ma_values[index], ma_values[index - lookback])
        previous_slope = _ratio_diff(ma_values[index - 1], ma_values[index - lookback])
        return slope is not None and previous_slope is not None and slope <= -self.thresholds.downward_slope_pct and previous_slope >= slope

    def _breaks_without_rebound(self, close: float, previous_close: float, ma: float | None, previous_ma: float | None) -> bool:
        if ma is None or previous_ma is None:
            return False
        broke_down = previous_close >= previous_ma and close < ma
        rebound_missing = close < ma * (1 + self.thresholds.rebound_confirm_pct)
        return broke_down and rebound_missing

    def _crossed_line_down(self, previous_close: float, previous_ma: float | None, close: float, ma: float | None) -> bool:
        return previous_ma is not None and ma is not None and previous_close >= previous_ma and close < ma

    def _twenty_ma_touch(self, row: KLine, ma20: float | None) -> tuple[SignalType, SignalSeverity, str, str] | None:
        if ma20 is None:
            return None
        touched = row.low <= ma20 * (1 + self.thresholds.touch_tolerance_pct) and row.high >= ma20 * (1 - self.thresholds.touch_tolerance_pct)
        if not touched:
            return None
        if row.close >= ma20:
            return (SignalType.TWENTY_MA_SUPPORT_TOUCH, SignalSeverity.WATCH, "触碰20日线支撑", "股价触碰20日均线后收在其上方，标注为支撑观察点。")
        return (SignalType.TWENTY_MA_RESISTANCE_TOUCH, SignalSeverity.RISK, "触碰20日线阻力", "股价触碰20日均线但收在其下方，标注为阻力/风险点。")

    def _bullish_alignment(self, ma5: list[float | None], ma10: list[float | None], ma20: list[float | None], index: int) -> bool:
        current = (ma5[index], ma10[index], ma20[index])
        if any(value is None for value in current):
            return False
        short, middle, long = current
        assert short is not None and middle is not None and long is not None
        spread_ok = (short - middle) / middle >= self.thresholds.arrangement_spread_pct and (middle - long) / long >= self.thresholds.arrangement_spread_pct
        return short > middle > long and spread_ok and self._ma_turns_up(ma5, index) and self._ma_turns_up(ma10, index)

    def _bearish_alignment(self, ma5: list[float | None], ma10: list[float | None], ma20: list[float | None], index: int) -> bool:
        current = (ma5[index], ma10[index], ma20[index])
        if any(value is None for value in current):
            return False
        short, middle, long = current
        assert short is not None and middle is not None and long is not None
        spread_ok = (middle - short) / short >= self.thresholds.arrangement_spread_pct and (long - middle) / middle >= self.thresholds.arrangement_spread_pct
        return long > middle > short and spread_ok and self._ma_turns_down(ma5, index) and self._ma_turns_down(ma10, index)
