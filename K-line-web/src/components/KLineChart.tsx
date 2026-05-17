import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { HistoryRange, HistoryResponse, KLineBar, Signal } from "../types/api";
import { severityLabel, signalTypeLabel } from "../types/labels";

type ChartSeverity = Exclude<Signal["severity"], "normal">;

type Props = {
  history: HistoryResponse | null;
  range: HistoryRange;
  onRangeChange: (range: HistoryRange) => void;
};

type Marker = {
  date: string;
  close: number;
  title: string;
  severity: ChartSeverity;
  signalType: string;
};

type ChartBar = KLineBar & {
  candleValue: number;
  marker?: Marker;
};

const markerColor: Record<ChartSeverity, string> = {
  entry: "#dc2626",
  watch: "#0284c7",
  risk: "#d97706",
  exit: "#16a34a"
};

const visibleSeverities: ChartSeverity[] = ["entry", "exit"];
const rangeOptions: Array<{ value: HistoryRange; label: string; subtitle: string }> = [
  { value: "daily", label: "日", subtitle: "当天分钟数据" },
  { value: "monthly", label: "月", subtitle: "最近一月" },
  { value: "yearly", label: "年", subtitle: "最近一年" }
];

function markerData(bars: KLineBar[]): Marker[] {
  return bars.flatMap((bar) =>
    bar.signals
      .filter((signal) => visibleSeverities.includes(signal.severity))
      .map((signal) => ({
        date: bar.date,
        close: bar.close,
        title: signal.title,
        severity: signal.severity,
        signalType: signal.signal_type
      }))
  );
}

function chartData(bars: KLineBar[]): ChartBar[] {
  return bars.map((bar) => {
    const baseBar = { ...bar, candleValue: bar.close };
    const primarySignal = bar.signals.find((signal) => visibleSeverities.includes(signal.severity));
    if (!primarySignal) return baseBar;
    return {
      ...baseBar,
      marker: {
        date: bar.date,
        close: bar.close,
        title: primarySignal.title,
        severity: primarySignal.severity,
        signalType: primarySignal.signal_type
      }
    };
  });
}

function formatValue(value: unknown) {
  return typeof value === "number" ? value.toFixed(2) : "--";
}

function formatXAxisLabel(value: string) {
  return value.includes(" ") ? value.slice(11, 16) : value;
}

function priceDomain(bars: ChartBar[]): [number, number] | ["auto", "auto"] {
  const values = bars
    .flatMap((bar) => [bar.open, bar.high, bar.low, bar.close, bar.ma5, bar.ma10, bar.ma20])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!values.length) return ["auto", "auto"];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max((max - min) * 0.08, max * 0.01, 0.01);
  return [Math.max(0, min - padding), max + padding];
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name?: string; value?: unknown; payload?: ChartBar }>; label?: string }) {
  if (!active || !payload?.length) return null;
  const marker = payload.find((item) => item.payload?.marker)?.payload?.marker;
  const bar = payload[0]?.payload;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {bar ? (
        <>
          <div className="tooltip-row"><span>开盘</span><b>{formatValue(bar.open)}</b></div>
          <div className="tooltip-row"><span>最高</span><b>{formatValue(bar.high)}</b></div>
          <div className="tooltip-row"><span>最低</span><b>{formatValue(bar.low)}</b></div>
          <div className="tooltip-row"><span>收盘</span><b>{formatValue(bar.close)}</b></div>
        </>
      ) : null}
      {payload
        .filter((item) => item.name !== "K线")
        .map((item) => (
          <div className="tooltip-row" key={item.name}>
            <span>{item.name}</span>
            <b>{formatValue(item.value)}</b>
          </div>
        ))}
      {marker ? (
        <div className={`tooltip-signal ${marker.severity}`}>
          {severityLabel[marker.severity]} · {marker.title || signalTypeLabel[marker.signalType] || marker.signalType}
        </div>
      ) : null}
    </div>
  );
}

function CandleShape(props: { cx?: number; yAxis?: { scale: (value: number) => number }; payload?: ChartBar }) {
  const { cx = 0, yAxis, payload } = props;
  if (!payload || !yAxis) return null;
  const rising = payload.close >= payload.open;
  const color = rising ? "#dc2626" : "#16a34a";
  const openY = yAxis.scale(payload.open);
  const closeY = yAxis.scale(payload.close);
  const highY = yAxis.scale(payload.high);
  const lowY = yAxis.scale(payload.low);
  const bodyTop = Math.min(openY, closeY);
  const bodyHeight = Math.max(Math.abs(closeY - openY), 2);
  const width = 7;

  return (
    <g>
      <line x1={cx} x2={cx} y1={highY} y2={lowY} stroke={color} strokeWidth={1.4} />
      <rect x={cx - width / 2} y={bodyTop} width={width} height={bodyHeight} fill={rising ? "#fee2e2" : "#dcfce7"} stroke={color} strokeWidth={1.4} rx={1} />
    </g>
  );
}

function MarkerShape(props: { cx?: number; cy?: number; payload?: ChartBar }) {
  const { cx = 0, cy = 0, payload } = props;
  if (!payload?.marker) return null;
  const severity = payload.marker.severity;
  const color = markerColor[severity];
  if (severity === "exit" || severity === "risk") {
    return <path d={`M ${cx} ${cy - 7} L ${cx + 7} ${cy + 6} L ${cx - 7} ${cy + 6} Z`} fill={color} stroke="#ffffff" strokeWidth={2} />;
  }
  return <circle cx={cx} cy={cy} r={6} fill={color} stroke="#ffffff" strokeWidth={2} />;
}

export function KLineChart({ history, range, onRangeChange }: Props) {
  if (!history || !history.bars.length) {
    return (
      <div className="panel chart-panel empty-chart">
        <span>选择股票后显示图表</span>
      </div>
    );
  }

  const bars = history.bars;
  const markers = markerData(bars);
  const chartBars = chartData(bars);
  const yDomain = priceDomain(chartBars);
  const latest = bars[bars.length - 1];
  const recentMarkers = markers.slice(-6).reverse();
  const titleName = history.name && history.name !== history.symbol ? history.name : history.symbol;
  const showSymbol = history.name && history.name !== history.symbol;
  const selectedRange = rangeOptions.find((option) => option.value === range) || rangeOptions[0];
  const showCandles = range !== "daily";

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <div className="panel-title chart-title">
            {titleName}
            {showSymbol ? <span>{history.symbol}</span> : null}
          </div>
          <div className="chart-subtitle">{selectedRange.subtitle} · {range === "daily" ? "分时价格" : "日K线数据"}</div>
        </div>
        <div className="chart-side">
          <div className="period-switch" aria-label="切换数据范围">
            {rangeOptions.map((option) => (
              <button type="button" className={option.value === range ? "active" : ""} key={option.value} onClick={() => onRangeChange(option.value)}>
                {option.label}
              </button>
            ))}
          </div>
          <div className="chart-metrics">
            <span>收盘 <b>{formatValue(latest?.close)}</b></span>
            <span>MA5 <b>{formatValue(latest?.ma5)}</b></span>
            <span>MA10 <b>{formatValue(latest?.ma10)}</b></span>
            <span>MA20 <b>{formatValue(latest?.ma20)}</b></span>
          </div>
        </div>
      </div>
      <div className="chart-legend">
        <span><i className="line close" />收盘</span>
        {showCandles ? <span><i className="candle up" />K线箱体</span> : null}
        <span><i className="line ma5" />MA5</span>
        <span><i className="line ma10" />MA10</span>
        <span><i className="line ma20" />MA20</span>
        <span><i className="dot entry" />进场</span>
        <span><i className="triangle risk" />离场</span>
      </div>
      <div className="chart-canvas">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartBars} margin={{ top: 12, right: 30, bottom: 10, left: 8 }}>
            <defs>
              <linearGradient id="closeStroke" x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor="#0f172a" />
                <stop offset="100%" stopColor="#334155" />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#e7ebf0" vertical={false} strokeDasharray="4 4" />
            <XAxis dataKey="date" tickFormatter={formatXAxisLabel} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} minTickGap={30} />
            <YAxis domain={yDomain} tickFormatter={(value) => Number(value).toFixed(2)} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} width={48} />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#94a3b8", strokeDasharray: "4 4" }} />
            {showCandles ? <Scatter dataKey="candleValue" name="K线" shape={<CandleShape />} isAnimationActive={false} /> : null}
            <Line type="monotone" dataKey="close" name="收盘" stroke="url(#closeStroke)" dot={<MarkerShape />} strokeWidth={2.1} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="ma5" name="MA5" stroke="#2563eb" dot={false} strokeWidth={1.8} />
            <Line type="monotone" dataKey="ma10" name="MA10" stroke="#f59e0b" dot={false} strokeWidth={1.8} />
            <Line type="monotone" dataKey="ma20" name="MA20" stroke="#16a34a" dot={false} strokeWidth={1.8} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="marker-list">
        {recentMarkers.length ? (
          recentMarkers.map((marker) => (
            <div className={`marker-item ${marker.severity}`} key={`${marker.date}-${marker.signalType}`}>
              <span>{marker.date}</span>
              <b>{severityLabel[marker.severity]}</b>
              <p>{marker.title || signalTypeLabel[marker.signalType] || marker.signalType}</p>
            </div>
          ))
        ) : (
          <div className="marker-empty">当前区间暂无信号标注</div>
        )}
      </div>
    </div>
  );
}
