import type { Signal } from "../types/api";
import { severityLabel, signalTypeLabel } from "../types/labels";

type Props = {
  signals: Signal[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
};

export function SignalTable({ signals, selectedSymbol, onSelectSymbol }: Props) {
  return (
    <div className="panel table-panel">
      <div className="table-header">
        <div>
          <div className="panel-title table-title">最新信号</div>
          <div className="table-subtitle">按日期倒序显示，点击行查看历史标注</div>
        </div>
        <span className="table-count">{signals.length} 条</span>
      </div>
      <div className="signal-table">
        <div className="signal-row signal-head">
          <span>代码</span>
          <span>日期</span>
          <span>级别</span>
          <span>信号</span>
          <span>收盘</span>
        </div>
        {signals.map((signal) => (
          <button
            type="button"
            className={`signal-row ${signal.severity} ${selectedSymbol === signal.symbol ? "selected" : ""}`}
            key={`${signal.symbol}-${signal.trade_date}-${signal.signal_type}`}
            onClick={() => onSelectSymbol(signal.symbol)}
          >
            <span className="symbol-cell">{signal.symbol}</span>
            <span className="date-cell">{signal.trade_date}</span>
            <span className={`badge ${signal.severity}`}>{severityLabel[signal.severity]}</span>
            <span className="signal-cell" title={signal.description}>
              <b>{signal.title || signalTypeLabel[signal.signal_type] || signal.signal_type}</b>
              <small>{signal.description}</small>
            </span>
            <span className="price-cell">{signal.close.toFixed(2)}</span>
          </button>
        ))}
        {signals.length === 0 ? <div className="empty">暂无信号</div> : null}
      </div>
    </div>
  );
}
