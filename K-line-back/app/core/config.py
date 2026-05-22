from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


APP_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = APP_ROOT.parent

if os.getenv("KLINE_SKIP_ENV_FILE", "").lower() not in {"1", "true", "yes", "on"}:
    _load_env_file(PROJECT_ROOT / ".env")
    _load_env_file(APP_ROOT / ".env")


@dataclass(frozen=True)
class SignalThresholds:
    # Price distance from an MA that still counts as a touch.
    # Unit: decimal ratio of MA value. Lower values are stricter and produce fewer support/resistance signals.
    touch_tolerance_pct: float = 0.006

    # Lookback window used by the entry setup to find two consecutive limit-up days.
    # Unit: trading days. Larger values keep the setup alive longer after the limit-up pair.
    double_limit_lookback_days: int = 10

    # Daily close gain that is treated as a limit-up day.
    # Unit: decimal ratio.
    limit_up_pct: float = 0.09

    # Current volume must be below this ratio of the average volume of the consecutive limit-up days.
    # Unit: decimal ratio. Lower values require a stronger volume contraction on pullback.
    pullback_volume_shrink_ratio: float = 0.8

    # Allowed intraday pierce below an MA during a "pullback hold" check.
    # Unit: decimal ratio of MA value. Lower values reject more noisy pullbacks.
    break_tolerance_pct: float = 0.03

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
                "key": "double_limit_lookback_days",
                "label": "连板回看天数",
                "value": self.double_limit_lookback_days,
                "description": "进场条件中查找连续两天涨停的时间窗口；当前规则固定要求十天内出现连板。",
                "unit": "交易日",
            },
            {
                "key": "limit_up_pct",
                "label": "涨停涨幅阈值",
                "value": self.limit_up_pct,
                "description": "单日收盘涨幅达到该比例时视为涨停。",
                "unit": "比例",
            },
            {
                "key": "pullback_volume_shrink_ratio",
                "label": "缩量回调比例",
                "value": self.pullback_volume_shrink_ratio,
                "description": "回调日成交量需要低于连续涨停两天平均成交量的该比例，数值越低越严格。",
                "unit": "比例",
            },
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
    database_url: str | None = os.getenv("KLINE_DATABASE_URL") or None
    scan_cron: str = "0 22 * * *"
    max_scan_symbols: int | None = None
    sync_concept_modules: bool = (os.getenv("KLINE_SYNC_CONCEPTS") or "").lower() in {"1", "true", "yes", "on"}
    thresholds: SignalThresholds = field(default_factory=SignalThresholds)


settings = Settings()
