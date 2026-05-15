import type { ConfigItem, HistoryResponse, ScanStatus, Signal, Stock } from "../types/api";

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
  stocks: (q: string) => request<Stock[]>(`/api/stocks?q=${encodeURIComponent(q)}`),
  history: (symbol: string) => request<HistoryResponse>(`/api/stocks/${symbol}/history`)
};
