import type { ConfigItem, HistoryRange, HistoryResponse, ModuleSyncStatus, ScanStatus, Signal, Stock, StockModule } from "../types/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  config: () => request<{ thresholds: ConfigItem[]; scan_cron: string }>("/api/config"),
  scanStatus: () => request<ScanStatus | null>("/api/scan/status"),
  runScan: () => request<{ status: string; scanned_count: number; signal_count: number; message: string }>("/api/scan/run", { method: "POST" }),
  signals: (params: URLSearchParams) => request<Signal[]>(`/api/signals?${params.toString()}`),
  stockStatuses: (params: URLSearchParams) => request<Signal[]>(`/api/stock-statuses?${params.toString()}`),
  modules: () => request<StockModule[]>("/api/modules"),
  moduleSyncStatus: () => request<ModuleSyncStatus>("/api/modules/sync/status"),
  runModuleSync: () => request<ModuleSyncStatus>("/api/modules/sync", { method: "POST" }),
  stocks: (q: string) => request<Stock[]>(`/api/stocks?q=${encodeURIComponent(q)}`),
  history: (symbol: string, range: HistoryRange) => request<HistoryResponse>(`/api/stocks/${symbol}/history?range=${range}`)
};
