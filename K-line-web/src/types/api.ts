export type Signal = {
  id?: number;
  symbol: string;
  trade_date: string;
  signal_type: string;
  severity: "entry" | "watch" | "risk" | "exit";
  title: string;
  description: string;
  close: number;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
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
    severity: Signal["severity"];
    title: string;
    description: string;
  }>;
};

export type HistoryResponse = {
  symbol: string;
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

export type ConfigItem = {
  key: string;
  label?: string;
  value: string | number;
  description: string;
  unit: string;
};
