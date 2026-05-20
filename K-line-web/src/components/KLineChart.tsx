import { memo, useMemo } from "react";
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
  candleWidth: number;
  marker?: Marker;
  entryMarker?: number;
  exitMarker?: number;
};

const visibleSeverities: ChartSeverity[] = ["entry", "exit"];
const rangeOptions: Array<{ value: HistoryRange; label: string; subtitle: string }> = [
  { value: "daily", label: "日", subtitle: "日K线" },
  { value: "weekly", label: "周", subtitle: "周K线" },
  { value: "monthly", label: "月", subtitle: "月K线" }
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

function dedupeMarkersByDate(markers: Marker[]): Marker[] {
  const markerByDate = new Map<string, Marker>();
  for (const marker of markers) {
    if (!markerByDate.has(marker.date)) {
      markerByDate.set(marker.date, marker);
    }
  }
  return Array.from(markerByDate.values());
}

function candleWidthForRange(range: HistoryRange, count: number) {
  if (range === "hourly") return 14;
  if (range === "monthly") return 13;
  if (range === "weekly") return 11;
  if (count <= 35) return 10;
  return 7;
}

function chartData(bars: KLineBar[], range: HistoryRange): ChartBar[] {
  const candleWidth = candleWidthForRange(range, bars.length);
  return bars.map((bar) => {
    const baseBar = { ...bar, candleValue: bar.close, candleWidth };
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
      },
      entryMarker: primarySignal.severity === "entry" ? bar.close : undefined,
      exitMarker: primarySignal.severity === "exit" ? bar.close : undefined
    };
  });
}

function isPlottableCoordinate(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatValue(value: unknown) {
  return typeof value === "number" ? value.toFixed(2) : "--";
}

function formatPct(value: unknown) {
  return typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "--";
}

function formatXAxisLabel(value: string, range: HistoryRange) {
  const datePart = value.split(" ")[0] || value;
  if (range === "hourly") return value.includes(" ") ? value.slice(11, 16) : value.slice(11, 13);
  if (range === "weekly") return value.replace("-", " ");
  if (range === "monthly") return datePart.slice(0, 7);
  return datePart.slice(5, 10);
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
  const bar = payload.find((item) => item.payload?.date)?.payload;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {bar ? (
        <>
          <div className="tooltip-row"><span>开盘</span><b>{formatValue(bar.open)}</b></div>
          <div className="tooltip-row"><span>最高</span><b>{formatValue(bar.high)}</b></div>
          <div className="tooltip-row"><span>最低</span><b>{formatValue(bar.low)}</b></div>
          <div className="tooltip-row"><span>收盘</span><b>{formatValue(bar.close)}</b></div>
          <div className="tooltip-row"><span>涨跌幅</span><b>{formatPct(bar.change_pct)}</b></div>
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
  const fill = rising ? "#fff7f7" : "#16a34a";
  const openY = yAxis.scale(payload.open);
  const closeY = yAxis.scale(payload.close);
  const highY = yAxis.scale(payload.high);
  const lowY = yAxis.scale(payload.low);
  const bodyTop = Math.min(openY, closeY);
  const bodyHeight = Math.max(Math.abs(closeY - openY), 2);
  const width = payload.candleWidth;

  return (
    <g className="kline-candle">
      <line x1={cx} x2={cx} y1={highY} y2={lowY} stroke={color} strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
      <rect x={cx - width / 2} y={bodyTop} width={width} height={bodyHeight} fill={fill} stroke={color} strokeWidth={1.45} rx={0.8} vectorEffect="non-scaling-stroke" />
    </g>
  );
}

function EntryMarkerShape(props: { cx?: number; cy?: number; payload?: ChartBar }) {
  const { cx, cy, payload } = props;
  if (!isPlottableCoordinate(cx) || !isPlottableCoordinate(cy) || !isPlottableCoordinate(payload?.entryMarker)) return null;
  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill="#dc2626" stroke="#ffffff" strokeWidth={2} />
      <path d={`M ${cx - 4} ${cy + 1} L ${cx} ${cy - 4} L ${cx + 4} ${cy + 1}`} fill="none" stroke="#ffffff" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
}

function ExitMarkerShape(props: { cx?: number; cy?: number; payload?: ChartBar }) {
  const { cx, cy, payload } = props;
  if (!isPlottableCoordinate(cx) || !isPlottableCoordinate(cy) || !isPlottableCoordinate(payload?.exitMarker)) return null;
  return <path d={`M ${cx} ${cy + 7} L ${cx + 7} ${cy - 6} L ${cx - 7} ${cy - 6} Z`} fill="#16a34a" stroke="#ffffff" strokeWidth={2} />;
}

function KLineChartComponent({ history, range, onRangeChange }: Props) {
  const bars = history?.bars ?? [];
  const chartBars = useMemo(() => chartData(bars, range), [bars, range]);
  const yDomain = useMemo(() => priceDomain(chartBars), [chartBars]);
  const recentMarkers = useMemo(() => dedupeMarkersByDate(markerData(bars)).slice(-6).reverse(), [bars]);

  if (!history || !history.bars.length) {
    return (
      <div className="panel chart-panel empty-chart">
        <span>选择股票后显示图表</span>
      </div>
    );
  }

  const latest = bars[bars.length - 1];
  const titleName = history.name && history.name !== history.symbol ? history.name : history.symbol;
  const showSymbol = history.name && history.name !== history.symbol;
  const selectedRange = rangeOptions.find((option) => option.value === range) || rangeOptions[0];
  const showCandles = range !== "hourly";

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <div className="panel-title chart-title">
            {titleName}
            {showSymbol ? <span>{history.symbol}</span> : null}
          </div>
          <div className="chart-subtitle">{selectedRange.subtitle} · 每个点代表一个{selectedRange.label}周期</div>
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
            <span>涨跌幅 <b>{formatPct(latest?.change_pct)}</b></span>
            <span>MA5 <b>{formatValue(latest?.ma5)}</b></span>
            <span>MA10 <b>{formatValue(latest?.ma10)}</b></span>
            <span>MA20 <b>{formatValue(latest?.ma20)}</b></span>
          </div>
        </div>
      </div>
      <div className="chart-legend">
        {showCandles ? <span><i className="candle up" />K线箱体</span> : <span><i className="line close" />收盘线</span>}
        <span><i className="line ma5" />MA5</span>
        <span><i className="line ma10" />MA10</span>
        <span><i className="line ma20" />MA20</span>
        <span><i className="dot entry" />进场</span>
        <span><i className="triangle risk" />离场</span>
      </div>
      <div className="chart-canvas">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartBars} margin={{ top: 12, right: 30, bottom: 10, left: 8 }}>
            <CartesianGrid stroke="#e7ebf0" vertical={false} strokeDasharray="4 4" />
            <XAxis dataKey="date" tickFormatter={(value) => formatXAxisLabel(String(value), range)} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} minTickGap={30} />
            <YAxis domain={yDomain} tickFormatter={(value) => Number(value).toFixed(2)} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} width={48} />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#94a3b8", strokeDasharray: "4 4" }} />
            {showCandles ? <Scatter dataKey="candleValue" name="K线" shape={<CandleShape />} isAnimationActive={false} /> : null}
            {!showCandles ? <Line type="monotone" dataKey="close" name="收盘线" stroke="#0f172a" dot={false} strokeWidth={2.1} activeDot={{ r: 4 }} /> : null}
            <Line type="monotone" dataKey="ma5" name="MA5" stroke="#2563eb" dot={false} strokeWidth={1.8} />
            <Line type="monotone" dataKey="ma10" name="MA10" stroke="#f59e0b" dot={false} strokeWidth={1.8} />
            <Line type="monotone" dataKey="ma20" name="MA20" stroke="#16a34a" dot={false} strokeWidth={1.8} />
            <Scatter dataKey="entryMarker" name="进场" shape={<EntryMarkerShape />} isAnimationActive={false} />
            <Scatter dataKey="exitMarker" name="离场" shape={<ExitMarkerShape />} isAnimationActive={false} />
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

export const KLineChart = memo(KLineChartComponent);
