export type StockModule = {
  id?: number;
  module_key?: string;
  name: string;
  type: "market" | "chain" | "industry" | "concept" | "signal" | "custom" | string;
  description?: string;
  source: string;
  stock_count?: number;
  score?: number | null;
  reason?: string;
};

export type Signal = {
  id?: number;
  symbol: string;
  name?: string;
  trade_date: string;
  signal_type: string;
  severity: "entry" | "watch" | "risk" | "exit" | "normal";
  title: string;
  description: string;
  close?: number | null;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  modules?: StockModule[];
};

export type KLineBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  signals: Array<{
    signal_type: string;
    severity: "entry" | "watch" | "risk" | "exit";
    title: string;
    description: string;
  }>;
};

export type HistoryRange = "daily" | "monthly" | "yearly";

export type HistoryResponse = {
  symbol: string;
  name?: string;
  bars: KLineBar[];
};

export type Stock = {
  symbol: string;
  name: string;
};

export type ScanStatus = {
  id: number;
  started_at: string;
  finished_at?: string;
  status: string;
  scanned_count: number;
  signal_count: number;
  message?: string;
};

export type ModuleSyncStatus = {
  status: "idle" | "running" | "success" | "failed" | string;
  started_at?: string | null;
  finished_at?: string | null;
  updated_count: number;
  message?: string;
};

export type ConfigItem = {
  key: string;
  label?: string;
  value: string | number;
  description: string;
  unit: string;
};
