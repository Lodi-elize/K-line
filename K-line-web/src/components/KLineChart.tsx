import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { HistoryResponse, KLineBar, Signal } from "../types/api";
import { severityLabel, signalTypeLabel } from "../types/labels";

type Props = {
  history: HistoryResponse | null;
};

type Marker = {
  date: string;
  close: number;
  title: string;
  severity: Signal["severity"];
  signalType: string;
};

type ChartBar = KLineBar & {
  markerClose?: number;
  marker?: Marker;
};

const markerColor: Record<Signal["severity"], string> = {
  entry: "#16a34a",
  watch: "#0284c7",
  risk: "#d97706",
  exit: "#dc2626"
};

function markerData(bars: KLineBar[]): Marker[] {
  return bars.flatMap((bar) =>
    bar.signals.map((signal) => ({
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
    const primarySignal = bar.signals[0];
    if (!primarySignal) return bar;
    return {
      ...bar,
      markerClose: bar.close,
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

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name?: string; value?: unknown; payload?: ChartBar }>; label?: string }) {
  if (!active || !payload?.length) return null;
  const marker = payload.find((item) => item.payload?.marker)?.payload?.marker;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload
        .filter((item) => item.name !== "信号" && item.name !== "markerClose")
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

function MarkerShape(props: { cx?: number; cy?: number; payload?: ChartBar }) {
  const { cx = 0, cy = 0, payload } = props;
  const severity = payload?.marker?.severity ?? "watch";
  const color = markerColor[severity];
  if (severity === "exit" || severity === "risk") {
    return <path d={`M ${cx} ${cy - 7} L ${cx + 7} ${cy + 6} L ${cx - 7} ${cy + 6} Z`} fill={color} stroke="#ffffff" strokeWidth={2} />;
  }
  return <circle cx={cx} cy={cy} r={6} fill={color} stroke="#ffffff" strokeWidth={2} />;
}

export function KLineChart({ history }: Props) {
  if (!history) {
    return <div className="panel chart-panel empty-chart">选择一只股票查看历史标注</div>;
  }

  const bars = history.bars.slice(-90);
  const markers = markerData(bars);
  const chartBars = chartData(bars);
  const latest = bars[bars.length - 1];
  const recentMarkers = markers.slice(-6).reverse();

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <div className="panel-title chart-title">{history.symbol} 历史标注</div>
          <div className="chart-subtitle">最近90个交易日 · 严格均线信号</div>
        </div>
        <div className="chart-metrics">
          <span>收盘 <b>{formatValue(latest?.close)}</b></span>
          <span>MA5 <b>{formatValue(latest?.ma5)}</b></span>
          <span>MA10 <b>{formatValue(latest?.ma10)}</b></span>
          <span>MA20 <b>{formatValue(latest?.ma20)}</b></span>
        </div>
      </div>
      <div className="chart-legend">
        <span><i className="line close" />收盘</span>
        <span><i className="line ma5" />MA5</span>
        <span><i className="line ma10" />MA10</span>
        <span><i className="line ma20" />MA20</span>
        <span><i className="dot entry" />进场/观察</span>
        <span><i className="triangle risk" />风险/离场</span>
      </div>
      <ResponsiveContainer width="100%" height={390}>
        <ComposedChart data={chartBars} margin={{ top: 8, right: 18, bottom: 8, left: 2 }}>
          <defs>
            <linearGradient id="closeStroke" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#0f172a" />
              <stop offset="100%" stopColor="#334155" />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e7ebf0" vertical={false} strokeDasharray="4 4" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} minTickGap={30} />
          <YAxis domain={["dataMin - 1", "dataMax + 1"]} tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} width={48} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#94a3b8", strokeDasharray: "4 4" }} />
          <Line type="monotone" dataKey="close" name="收盘" stroke="url(#closeStroke)" dot={false} strokeWidth={2.4} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="ma5" name="MA5" stroke="#2563eb" dot={false} strokeWidth={1.8} />
          <Line type="monotone" dataKey="ma10" name="MA10" stroke="#f59e0b" dot={false} strokeWidth={1.8} />
          <Line type="monotone" dataKey="ma20" name="MA20" stroke="#16a34a" dot={false} strokeWidth={1.8} />
          <Scatter dataKey="markerClose" name="信号" shape={<MarkerShape />} />
        </ComposedChart>
      </ResponsiveContainer>
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
