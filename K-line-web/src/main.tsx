import { Activity, Check, ChevronDown, Filter, Layers, Play, RefreshCw, RotateCcw, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api/client";
import { KLineChart } from "./components/KLineChart";
import { SignalTable } from "./components/SignalTable";
import type { ConfigItem, HistoryResponse, ModuleSyncStatus, ScanStatus, Signal, StockModule } from "./types/api";
import { statusLabel } from "./types/labels";
import "./styles.css";

type SelectOption = {
  value: string;
  label: string;
};

type FilterSelectProps = {
  label: string;
  value: string;
  options: SelectOption[];
  wide?: boolean;
  onChange: (value: string) => void;
};

type ToastState = {
  message: string;
  tone: "info" | "success" | "error";
};

function moduleTypeLabel(type: string) {
  const labels: Record<string, string> = {
    market: "市场",
    industry: "行业",
    concept: "概念",
    custom: "自定义",
  };
  return labels[type] || type;
}

function formatConfigValue(item: ConfigItem) {
  if (item.unit === "比例" && typeof item.value === "number") {
    return `${item.value}（${(item.value * 100).toFixed(2)}%）`;
  }
  return String(item.value);
}

function moduleSyncLabel(status?: string) {
  const labels: Record<string, string> = {
    idle: "未运行",
    running: "更新中",
    success: "完成",
    failed: "失败",
  };
  return status ? labels[status] || status : "未运行";
}

function moduleSyncSocketUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/modules/sync`;
}

function FilterSelect({ label, value, options, wide = false, onChange }: FilterSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value) || options[0];

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, []);

  return (
    <div className={`select-field custom-select ${wide ? "signal-select" : ""} ${open ? "open" : ""}`} ref={rootRef}>
      <span>{label}</span>
      <button type="button" className="select-trigger" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        <b>{selected?.label || "请选择"}</b>
        <ChevronDown size={14} />
      </button>
      {open ? (
        <div className="select-menu" role="listbox">
          {options.map((option) => (
            <button
              type="button"
              className={`select-option ${option.value === value ? "selected" : ""}`}
              role="option"
              aria-selected={option.value === value}
              key={option.value || "all"}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              <span>{option.label}</span>
              {option.value === value ? <Check size={14} /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function App() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [moduleSync, setModuleSync] = useState<ModuleSyncStatus | null>(null);
  const [config, setConfig] = useState<ConfigItem[]>([]);
  const [modules, setModules] = useState<StockModule[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [severity, setSeverity] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [syncingModules, setSyncingModules] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);
  const isModuleSyncRunning = syncingModules || moduleSync?.status === "running";
  const isScanning = loading || status?.status === "running";

  const severityOptions = useMemo(
    () => [
      { value: "", label: "全部级别" },
      { value: "entry", label: "进场" },
      { value: "exit", label: "离场" },
      { value: "normal", label: "通常" },
    ],
    [],
  );
  const moduleOptions = useMemo(
    () => [
      { value: "", label: "全部模块" },
      ...modules.map((module) => ({
        value: String(module.id),
        label: `${moduleTypeLabel(module.type)} / ${module.name}${typeof module.stock_count === "number" ? `（${module.stock_count}）` : ""}`,
      })),
    ],
    [modules],
  );

  async function loadSignals() {
    const params = new URLSearchParams({ limit: "10000" });
    if (severity) params.set("severity", severity);
    if (moduleId) params.set("module_id", moduleId);
    const nextSignals = (await api.stockStatuses(params))
      .sort((left, right) => {
        const normalOrder = Number(left.severity === "normal") - Number(right.severity === "normal");
        if (normalOrder !== 0) return normalOrder;
        const dateOrder = (right.trade_date || "").localeCompare(left.trade_date || "");
        if (dateOrder !== 0) return dateOrder;
        return (right.id ?? 0) - (left.id ?? 0);
      });
    setSignals(nextSignals);
  }

  async function loadStatus() {
    setStatus(await api.scanStatus());
  }

  async function loadModuleSyncStatus() {
    const nextStatus = await api.moduleSyncStatus();
    setModuleSync(nextStatus);
    setSyncingModules(nextStatus.status === "running");
    return nextStatus;
  }

  async function loadConfig() {
    const data = await api.config();
    setConfig(data.thresholds);
  }

  async function loadModules() {
    setModules(await api.modules());
  }

  async function loadHistory(symbol: string) {
    setSelectedSymbol(symbol);
    setHistory(await api.history(symbol));
  }

  function showToast(message: string, tone: ToastState["tone"] = "info") {
    setToast({ message, tone });
    window.setTimeout(() => setToast((current) => (current?.message === message ? null : current)), 2600);
  }

  async function refreshData() {
    setRefreshing(true);
    showToast("正在刷新数据...", "info");
    try {
      const tasks: Array<Promise<unknown>> = [loadSignals(), loadStatus(), loadConfig(), loadModules(), loadModuleSyncStatus()];
      if (selectedSymbol) tasks.push(loadHistory(selectedSymbol));
      await Promise.all(tasks);
      showToast("刷新完成", "success");
    } catch (error) {
      showToast(error instanceof Error ? `刷新失败：${error.message}` : "刷新失败", "error");
    } finally {
      setRefreshing(false);
    }
  }

  async function runModuleSync() {
    if (isModuleSyncRunning) return;
    setSyncingModules(true);
    showToast("正在后台更新概念模块...", "info");
    try {
      const result = await api.runModuleSync();
      setModuleSync(result);
      if (result.status === "running") {
        showToast(result.message || "模块更新已在后台启动，请稍后刷新", "info");
      } else if (result.status === "success") {
        await Promise.all([loadModules(), loadSignals()]);
        showToast(result.message || `模块更新完成：${result.updated_count} 条`, "success");
      } else {
        showToast(result.message || "模块更新失败", "error");
      }
    } catch (error) {
      showToast(error instanceof Error ? `模块更新失败：${error.message}` : "模块更新失败", "error");
    } finally {
      await loadModuleSyncStatus();
    }
  }

  async function runScan() {
    if (isScanning) return;
    setLoading(true);
    showToast("正在扫描全市场...", "info");
    try {
      const result = await api.runScan();
      const tasks: Array<Promise<unknown>> = [loadSignals(), loadStatus(), loadConfig(), loadModules()];
      if (selectedSymbol) tasks.push(loadHistory(selectedSymbol));
      await Promise.all(tasks);
      if (result.status === "running") {
        showToast(result.message || "扫描已在后台启动，请稍后刷新", "info");
      } else if (result.status === "success") {
        showToast(`扫描完成：${result.scanned_count} 只，新增 ${result.signal_count} 条`, "success");
      } else {
        showToast(result.message || "扫描失败", "error");
      }
    } catch (error) {
      showToast(error instanceof Error ? `扫描失败：${error.message}` : "扫描失败", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadConfig();
    loadStatus();
    loadModuleSyncStatus();
    loadModules();
    loadSignals();
  }, []);

  useEffect(() => {
    let lastTerminalStatus = "";
    let lastModuleRefreshAt = 0;
    const socket = new WebSocket(moduleSyncSocketUrl());
    socket.onmessage = async (event) => {
      const nextStatus = JSON.parse(event.data) as ModuleSyncStatus;
      setModuleSync(nextStatus);
      setSyncingModules(nextStatus.status === "running");
      if (nextStatus.status === "running" && Date.now() - lastModuleRefreshAt > 15000) {
        lastModuleRefreshAt = Date.now();
        loadModules();
      }
      if (nextStatus.status === "success" && lastTerminalStatus !== "success") {
        lastTerminalStatus = "success";
        await Promise.all([loadModules(), loadSignals()]);
        showToast(nextStatus.message || "模块更新完成", "success");
      }
      if (nextStatus.status === "failed" && lastTerminalStatus !== "failed") {
        lastTerminalStatus = "failed";
        showToast(nextStatus.message || "模块更新失败", "error");
      }
      if (nextStatus.status === "running") {
        lastTerminalStatus = "";
      }
    };
    socket.onerror = () => {
      socket.close();
    };
    return () => socket.close();
  }, []);

  useEffect(() => {
    loadSignals();
  }, [severity, moduleId]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>K-line Web</h1>
          <p>全市场 A 股均线信号扫描与历史标注</p>
        </div>
        <div className="actions">
          <button type="button" onClick={runScan} disabled={isScanning} title={isScanning ? "扫描正在运行中" : "开始扫描"}>
            {isScanning ? <RefreshCw className="spin" size={16} /> : <Play size={16} />}
            {status?.status === "running" ? "扫描中" : "扫描"}
          </button>
          <button type="button" onClick={runModuleSync} disabled={isModuleSyncRunning} title="更新概念模块">
            {isModuleSyncRunning ? <RefreshCw className="spin" size={16} /> : <Layers size={16} />}
            {isModuleSyncRunning ? "更新中" : "更新模块"}
          </button>
          <button
            type="button"
            onClick={refreshData}
            disabled={refreshing}
          >
            <RefreshCw className={refreshing ? "spin" : ""} size={16} />
            刷新
          </button>
        </div>
      </header>
      {toast ? <div className={`toast ${toast.tone}`}>{toast.message}</div> : null}

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
        <div className={`status-item module-sync-status ${moduleSync?.status || "idle"}`} title={moduleSync?.message || ""}>
          <Layers size={16} />
          <span>模块更新</span>
          <strong>{moduleSyncLabel(moduleSync?.status)}</strong>
          <small>{moduleSync?.updated_count ?? 0}</small>
        </div>
        <label className="search-box">
          <Search size={16} />
          <input
            placeholder="输入代码"
            value={selectedSymbol}
            onChange={(event) => setSelectedSymbol(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && selectedSymbol && loadHistory(selectedSymbol)}
          />
        </label>
      </section>
      {moduleSync?.message ? (
        <section className={`module-sync-log ${moduleSync.status}`}>
          <strong>模块日志</strong>
          <span>{moduleSync.message}</span>
        </section>
      ) : null}

      <section className="filters">
        <div className="filter-title">
          <Filter size={15} />
          筛选
        </div>
        <FilterSelect label="信号级别" value={severity} options={severityOptions} onChange={setSeverity} />
        <FilterSelect label="所属模块" value={moduleId} options={moduleOptions} wide onChange={setModuleId} />
        {severity || moduleId ? (
          <button
            className="clear-filter"
            type="button"
            onClick={() => {
              setSeverity("");
              setModuleId("");
            }}
          >
            <RotateCcw size={14} />
            清空
          </button>
        ) : null}
      </section>

      <section className="workspace">
        <SignalTable signals={signals} selectedSymbol={selectedSymbol} updatedAt={status?.finished_at || status?.started_at} onSelectSymbol={loadHistory} />
        <KLineChart history={history} />
      </section>

      <section className="panel config-panel">
        <div className="panel-title">可调算法项</div>
        <div className="config-grid">
          {config.map((item) => (
            <div className={`config-item ${item.key === "break_tolerance_pct" ? "highlight-config" : ""}`} key={item.key}>
              <strong>{item.label || item.key}</strong>
              <span>{formatConfigValue(item)} / {item.unit}</span>
              <p>{item.description}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
