from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SignalThresholds:
    # Price distance from an MA that still counts as a touch.
    # Unit: decimal ratio of MA value. Lower values are stricter and produce fewer support/resistance signals.
    touch_tolerance_pct: float = 0.006

    # Allowed intraday pierce below an MA during a "pullback hold" check.
    # Unit: decimal ratio of MA value. Lower values reject more noisy pullbacks.
    break_tolerance_pct: float = 0.002

    # Minimum MA slope over the lookback window to call the line "turning upward".
    # Unit: decimal ratio. Higher values require stronger upward movement and reduce entry signals.
    upward_slope_pct: float = 0.003

    # Minimum MA slope over the lookback window to call the line "turning downward".
    # Unit: decimal ratio. Higher values require stronger downward movement and reduce exit signals.
    downward_slope_pct: float = 0.003

    # Number of days used to confirm a moving-average turn or alignment expansion.
    # Unit: trading days. Larger values are stricter but slower to react.
    slope_lookback_days: int = 3

    # Minimum close rebound above a broken MA that counts as a rebound.
    # Unit: decimal ratio of MA value. Higher values classify more breaks as "no rebound" risk.
    rebound_confirm_pct: float = 0.004

    # Minimum separation between adjacent MAs for bullish/bearish arrangement to be considered expanded.
    # Unit: decimal ratio. Higher values reduce weak arrangement signals.
    arrangement_spread_pct: float = 0.004

    def as_documented_items(self) -> list[dict[str, str | float | int]]:
        return [
            {
                "key": "touch_tolerance_pct",
                "label": "均线触碰容忍度",
                "value": self.touch_tolerance_pct,
                "description": "价格距离均线多近才算触碰支撑/阻力；数值越小越严格，信号越少。",
                "unit": "比例",
            },
            {
                "key": "break_tolerance_pct",
                "label": "回踩跌破容忍度",
                "value": self.break_tolerance_pct,
                "description": "回踩不破时允许盘中轻微跌破均线的幅度；数值越小越能减少误报。",
                "unit": "比例",
            },
            {
                "key": "upward_slope_pct",
                "label": "上拐斜率阈值",
                "value": self.upward_slope_pct,
                "description": "判断均线拐头向上的最小斜率；数值越大越要求趋势更强。",
                "unit": "比例",
            },
            {
                "key": "downward_slope_pct",
                "label": "下拐斜率阈值",
                "value": self.downward_slope_pct,
                "description": "判断均线拐头向下的最小斜率；数值越大越要求走弱更明显。",
                "unit": "比例",
            },
            {
                "key": "slope_lookback_days",
                "label": "斜率确认天数",
                "value": self.slope_lookback_days,
                "description": "用于确认均线拐头或排列发散的交易日数量；数值越大越严格但反应更慢。",
                "unit": "交易日",
            },
            {
                "key": "rebound_confirm_pct",
                "label": "反抽确认阈值",
                "value": self.rebound_confirm_pct,
                "description": "跌破均线后收盘需要反抽到多高才算有反抽；数值越大，越容易判定为无反抽风险。",
                "unit": "比例",
            },
            {
                "key": "arrangement_spread_pct",
                "label": "均线排列发散阈值",
                "value": self.arrangement_spread_pct,
                "description": "多头/空头排列时相邻均线至少要拉开的距离；数值越大越严格。",
                "unit": "比例",
            },
        ]


@dataclass(frozen=True)
class Settings:
    app_name: str = "K-line MA Signal Scanner"
    database_path: Path = Path("data/kline.db")
    scan_cron: str = "0 18 * * 1-5"
    max_scan_symbols: int | None = None
    thresholds: SignalThresholds = field(default_factory=SignalThresholds)


settings = Settings()
