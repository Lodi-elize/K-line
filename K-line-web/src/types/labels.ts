import type { Signal } from "./api";

export const severityLabel: Record<Signal["severity"], string> = {
  entry: "进场",
  watch: "观察",
  risk: "风险",
  exit: "离场",
  normal: "通常"
};

export const signalTypeLabel: Record<string, string> = {
  golden_cross: "5日线金叉",
  death_cross: "5日线死叉",
  five_ma_pullback_hold: "回踩5日线不破",
  five_ma_turn_up: "5日线拐头向上",
  five_ma_turn_down: "5日线拐头向下",
  ten_ma_break_no_rebound: "跌破10日线且无反抽",
  twenty_ma_break: "跌破20日生命线",
  twenty_ma_support_touch: "触碰20日线支撑",
  twenty_ma_resistance_touch: "触碰20日线阻力",
  bullish_alignment: "均线多头排列",
  bearish_alignment: "均线空头排列"
};

export const statusLabel: Record<string, string> = {
  running: "扫描中",
  success: "完成",
  failed: "失败",
  idle: "未运行"
};
