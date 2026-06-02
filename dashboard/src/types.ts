export type Decision = "BUY" | "SELL" | "HOLD";
export type SystemStatus = "idle" | "running" | "stopped";
export type RiskHealth = "HEALTHY" | "MODERATE" | "HIGH_RISK" | "CRITICAL";

export interface VoteIndicators {
  rsi?: number;
  macd?: number;
  ema20?: number;
  ema50?: number;
  price?: number;
}

export interface AgentVote {
  agent_id: string;
  vote: Decision;
  confidence: number;
  reasoning: string;
  ts: string;
  indicators?: VoteIndicators;
}

export interface DecisionEntry {
  symbol: string;
  decision: Decision;
  score: number;
  reason: string;
  ts: string;
}

export interface Portfolio {
  balance: number;          // balance real Binance USDT
  binance_balance: number;
  trading_budget: number;   // límite operativo ($1,000)
  pnl: number;              // PnL acumulado sobre el budget (trades cerrados)
  pnl_pct: number;
  budget_pnl: number;
  budget_pnl_pct: number;
}

export interface OpenPosition {
  symbol: string;
  side: string;
  qty: number;
  price: number;
  sl: number;
  tp: number;
  ts: string;
}

export interface ActivePosition {
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  liquidation_price: number;
  leverage: number;
  sl_price: number | null;
  tp_price: number | null;
  open_time: string | null;
}

export interface NewsContext {
  sentiment?: number;
  impact?: string;
  summary?: string;
  assets?: Record<string, number>;
  message?: string;
}

export interface StrategyReview {
  review_date: string;
  grade: string;          // A-F
  win_rate: number;
  total_trades: number;
  net_pnl: number;
  summary: string;
  adjustments: string[];
  ts: string;
}

export interface TradeLesson {
  trade_id: number;
  side: string;
  outcome: string;        // WIN | LOSS
  pnl: number;
  exit_reason: string;
  tag: string;
  lesson: string;
  ts: string;
}

export interface RuntimeConfig {
  analysis_interval_seconds: number;
  trading_hours_enabled: boolean;
  trading_hours_start: number;
  trading_hours_end: number;
  trading_timezone: string;
}

export interface AppState {
  system_status: SystemStatus;
  current_cycle: number;
  last_decision: DecisionEntry | null;
  last_news: NewsContext | null;
  portfolio: Portfolio;
  open_positions: OpenPosition[];
  agent_votes: AgentVote[];
  risk_health: RiskHealth;
  errors: { message: string; ts: string }[];
  trading_mode: "FUTURES" | "SPOT";
  active_position: ActivePosition | null;
  hard_stop_message: string | null;
  strategy_review?: StrategyReview | null;
  lessons?: TradeLesson[];
  config?: RuntimeConfig;
}

export interface WsMessage {
  event: string;
  data: unknown;
  ts: string;
}
