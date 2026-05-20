import { memo } from "react";
import type { Signal } from "../types/api";
import { severityLabel, signalTypeLabel } from "../types/labels";

type Props = {
  signals: Signal[];
  selectedSymbol: string;
  updatedAt?: string;
  onSelectSymbol: (symbol: string) => void;
};

function formatUpdatedAt(value?: string) {
  if (!value) return "暂无更新时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function moduleTypeLabel(type: string) {
  const labels: Record<string, string> = {
    market: "市场",
    chain: "产业链",
    industry: "行业",
    concept: "概念",
    custom: "自定义",
  };
  return labels[type] || type;
}

function SignalTableComponent({ signals, selectedSymbol, updatedAt, onSelectSymbol }: Props) {
  return (
    <div className="panel table-panel">
      <div className="table-header">
        <div>
          <div className="panel-title table-title">
            最新信号
            <span>最近更新：{formatUpdatedAt(updatedAt)}</span>
          </div>
          <div className="table-subtitle">按日期倒序显示，点击行查看历史标注</div>
        </div>
        <span className="table-count">{signals.length} 条</span>
      </div>
      <div className="signal-table">
        <div className="signal-row signal-head">
          <span>股票</span>
          <span>日期</span>
          <span>级别</span>
          <span>模块</span>
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
            <span className="stock-cell" title={`${signal.name || signal.symbol} ${signal.symbol}`}>
              <b>{signal.name || signal.symbol}</b>
              <small>{signal.symbol}</small>
            </span>
            <span className="date-cell">{signal.trade_date || "--"}</span>
            <span className={`badge ${signal.severity}`}>{severityLabel[signal.severity]}</span>
            <span className="module-cell">
              {(signal.modules?.length ? signal.modules : [{ name: "未分组", type: "custom", source: "system" }]).map((module) => (
                <i className={`module-${module.type}`} title={`${moduleTypeLabel(module.type)}：${module.name}`} key={`${module.type}-${module.name}`}>
                  {module.name}
                </i>
              ))}
            </span>
            <span className="signal-cell" title={signal.description}>
              <b>{signal.title || signalTypeLabel[signal.signal_type] || signal.signal_type}</b>
              <small>{signal.description}</small>
            </span>
            <span className="price-cell">{typeof signal.close === "number" ? signal.close.toFixed(2) : "--"}</span>
          </button>
        ))}
        {signals.length === 0 ? (
          <div className="empty signal-empty">
            <strong>暂无匹配股票</strong>
            <span>当前筛选条件下没有可展示的股票状态，清空筛选后可查看全量列表。</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export const SignalTable = memo(SignalTableComponent);
