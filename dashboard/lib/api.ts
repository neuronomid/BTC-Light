const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SystemStatus {
  running: boolean;
  paused: boolean;
  equity: number;
  starting_equity: number;
  open_positions: number;
  closed_trades: number;
  daily_pnl: number;
  weekly_pnl: number;
  current_price: number | null;
  last_cycle: string | null;
  mode: string;
}

export interface Position {
  trade_id: string;
  symbol: string;
  action: string;
  entry_price: number;
  size: number;
  stop_loss: number;
  take_profit: number;
  opened_at: string;
  closed_at: string | null;
  conviction: number;
  reasoning: string;
  pnl: number;
  pnl_pct: number;
  status: string;
  exit_reason: string | null;
}

export interface TradeHistory {
  trades: Position[];
  total_count: number;
  total_pnl: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
}

export interface WalletBalance {
  balance: number;
  total_deposited: number;
  total_withdrawn: number;
  total_pnl: number;
}

export interface WalletTransaction {
  id: number;
  transaction_type: string;
  amount: number;
  balance_after: number;
  description: string | null;
  created_at: string;
}

export interface AgentOutput {
  agent_name: string;
  cycle_timestamp: string;
  output_data: Record<string, unknown>;
}

export interface SystemLog {
  id: number;
  level: string;
  source: string;
  message: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface ChartPoint {
  timestamp: string;
  price: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timeframe: string;
  trade_marker: Record<string, unknown> | null;
}

export interface StatisticalSnapshot {
  symbol: string;
  timeframe: string;
  timestamp: string;
  latest_close: number | null;
  regime: Record<string, unknown>;
  trend: Record<string, unknown>;
  volatility: Record<string, unknown>;
  change_point: Record<string, unknown>;
  tail_risk: Record<string, unknown>;
  efficiency: Record<string, unknown>;
  correlation: Record<string, unknown>;
  probability: Record<string, unknown> | null;
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err);
  }
  return res.json();
}

export const api = {
  status: () => fetchJson<SystemStatus>("/api/status"),
  start: () => fetchJson<{ message: string }>("/api/system/start", { method: "POST" }),
  pause: () => fetchJson<{ message: string }>("/api/system/pause", { method: "POST" }),
  resume: () => fetchJson<{ message: string }>("/api/system/resume", { method: "POST" }),
  shutdown: () => fetchJson<{ message: string }>("/api/system/shutdown", { method: "POST" }),
  reset: () => fetchJson<{ message: string }>("/api/system/reset", { method: "POST" }),

  openPositions: () => fetchJson<Position[]>("/api/positions/open"),
  closedTrades: (limit = 50, offset = 0) =>
    fetchJson<TradeHistory>(`/api/positions/closed?limit=${limit}&offset=${offset}`),

  walletBalance: () => fetchJson<WalletBalance>("/api/wallet/balance"),
  walletTransactions: (limit = 50) =>
    fetchJson<WalletTransaction[]>(`/api/wallet/transactions?limit=${limit}`),
  deposit: (amount: number, description?: string) =>
    fetchJson<{ message: string; balance: number }>("/api/wallet/deposit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, description }),
    }),
  withdraw: (amount: number, description?: string) =>
    fetchJson<{ message: string; balance: number }>("/api/wallet/withdraw", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, description }),
    }),

  agentOutputs: (agent?: string, limit = 20) =>
    fetchJson<AgentOutput[]>(`/api/agents/outputs?${agent ? `agent=${agent}&` : ""}limit=${limit}`),

  logs: (level?: string, source?: string, limit = 100) =>
    fetchJson<SystemLog[]>(`/api/logs?${level ? `level=${level}&` : ""}${source ? `source=${source}&` : ""}limit=${limit}`),

  chartData: (symbol = "BTC-USD", hours = 24, timeframe = "4h") =>
    fetchJson<ChartPoint[]>(`/api/chart/data?symbol=${symbol}&hours=${hours}&timeframe=${timeframe}`),

  statistics: () => fetchJson<StatisticalSnapshot | null>("/api/statistics/latest"),
};
