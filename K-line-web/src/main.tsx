import { Activity, Filter, Play, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api/client";
import { KLineChart } from "./components/KLineChart";
import { SignalTable } from "./components/SignalTable";
import type { ConfigItem, HistoryResponse, ScanStatus, Signal } from "./types/api";
import { signalTypeLabel, statusLabel } from "./types/labels";
import "./styles.css";

function App() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [config, setConfig] = useState<ConfigItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState("600001");
  const [severity, setSeverity] = useState("");
  const [signalType, setSignalType] = useState("");
  const [loading, setLoading] = useState(false);

  const signalTypes = useMemo(() => Array.from(new Set(signals.map((signal) => signal.signal_type))).sort(), [signals]);

  async function loadSignals() {
    const params = new URLSearchParams({ limit: "200" });
    if (severity) params.set("severity", severity);
    if (signalType) params.set("signal_type", signalType);
    setSignals(await api.signals(params));
  }

  async function loadStatus() {
    setStatus(await api.scanStatus());
  }

  async function loadHistory(symbol: string) {
    setSelectedSymbol(symbol);
    setHistory(await api.history(symbol));
  }

  async function runScan() {
    setLoading(true);
    try {
      await api.runScan();
      await Promise.all([loadSignals(), loadStatus(), loadHistory(selectedSymbol)]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    api.config().then((data) => setConfig(data.thresholds));
    loadStatus();
    loadSignals();
    loadHistory(selectedSymbol);
  }, []);

  useEffect(() => {
    loadSignals();
  }, [severity, signalType]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>K-line Web</h1>
          <p>全市场 A 股均线信号扫描与历史标注</p>
        </div>
        <div className="actions">
          <button type="button" onClick={runScan} disabled={loading}>
            {loading ? <RefreshCw className="spin" size={16} /> : <Play size={16} />}
            扫描
          </button>
          <button type="button" onClick={() => Promise.all([loadSignals(), loadStatus(), loadHistory(selectedSymbol)])}>
            <RefreshCw size={16} />
            刷新
          </button>
        </div>
      </header>

      <section className="status-strip">
        <div className="status-item">
          <Activity size={18} />
          <span>任务状态</span>
          <strong>{status ? statusLabel[status.status] || status.status : "未运行"}</strong>
        </div>
        <div className="status-item">
          <span>扫描数</span>
          <strong>{status?.scanned_count ?? 0}</strong>
        </div>
        <div className="status-item">
          <span>新增信号</span>
          <strong>{status?.signal_count ?? 0}</strong>
        </div>
        <label className="search-box">
          <Search size={16} />
          <input value={selectedSymbol} onChange={(event) => setSelectedSymbol(event.target.value)} onKeyDown={(event) => event.key === "Enter" && loadHistory(selectedSymbol)} />
        </label>
      </section>

      <section className="filters">
        <label>
          <Filter size={15} />
          级别
          <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
            <option value="">全部</option>
            <option value="entry">进场</option>
            <option value="watch">观察</option>
            <option value="risk">风险</option>
            <option value="exit">离场</option>
          </select>
        </label>
        <label>
          信号
          <select value={signalType} onChange={(event) => setSignalType(event.target.value)}>
            <option value="">全部</option>
            {signalTypes.map((type) => (
              <option value={type} key={type}>
                {signalTypeLabel[type] || type}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="workspace">
        <SignalTable signals={signals} selectedSymbol={selectedSymbol} onSelectSymbol={loadHistory} />
        <KLineChart history={history} />
      </section>

      <section className="panel config-panel">
        <div className="panel-title">可调算法项</div>
        <div className="config-grid">
          {config.map((item) => (
            <div className="config-item" key={item.key}>
              <strong>{item.label || item.key}</strong>
              <span>{String(item.value)} / {item.unit}</span>
              <p>{item.description}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
