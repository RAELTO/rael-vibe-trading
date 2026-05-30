import { useEffect, useRef, useState, useCallback } from "react";
import type { AppState, WsMessage } from "../types";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";
const PING_INTERVAL = 25_000;

const LS_KEY = "vibe_trading_state";

function loadPersistedState(): Partial<AppState> {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    // Solo restaurar datos que sobreviven entre sesiones
    return {
      last_decision: parsed.last_decision ?? null,
      last_news:     parsed.last_news     ?? null,
      portfolio:     parsed.portfolio     ?? { balance: 0, binance_balance: 0, trading_budget: 1000, pnl: 0, pnl_pct: 0, budget_pnl: 0, budget_pnl_pct: 0 },
      agent_votes:   parsed.agent_votes   ?? [],
    };
  } catch {
    return {};
  }
}

const initialState: AppState = {
  system_status: "idle",
  current_cycle: 0,
  last_decision: null,
  last_news: null,
  portfolio: { balance: 0, binance_balance: 0, trading_budget: 1000, pnl: 0, pnl_pct: 0, budget_pnl: 0, budget_pnl_pct: 0 },
  open_positions: [],
  agent_votes: [],
  risk_health: "HEALTHY",
  errors: [],
  trading_mode: "FUTURES",
  active_position: null,
  hard_stop_message: null,
  ...loadPersistedState(),
};

function persistState(s: AppState) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      last_decision: s.last_decision,
      last_news:     s.last_news,
      portfolio:     s.portfolio,
      agent_votes:   s.agent_votes.slice(0, 20),
    }));
  } catch { /* storage full — ignore */ }
}

export function useWebSocket() {
  const [state, setState] = useState<AppState>(initialState);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const apply = useCallback((msg: WsMessage) => {
    setState((prev) => {
      let next: AppState;
      switch (msg.event) {
        case "init":
          next = msg.data as AppState; break;
        case "cycle_start": {
          const d = msg.data as { cycle: number };
          next = { ...prev, current_cycle: d.cycle, system_status: "running" }; break;
        }
        case "agent_vote": {
          const v = msg.data as AppState["agent_votes"][number];
          next = { ...prev, agent_votes: [v, ...prev.agent_votes].slice(0, 20) }; break;
        }
        case "decision":
          next = { ...prev, last_decision: msg.data as AppState["last_decision"] }; break;
        case "order_placed": {
          const o = msg.data as AppState["open_positions"][number];
          next = { ...prev, open_positions: [...prev.open_positions, o] }; break;
        }
        case "portfolio_update":
          next = { ...prev, portfolio: msg.data as AppState["portfolio"] }; break;
        case "news_update":
          next = { ...prev, last_news: msg.data as AppState["last_news"] }; break;
        case "position_update": {
          const pos = msg.data as AppState["active_position"];
          next = { ...prev, active_position: pos }; break;
        }
        case "mode_change": {
          const m = msg.data as { mode: "FUTURES" | "SPOT" };
          next = { ...prev, trading_mode: m.mode, active_position: null }; break;
        }
        case "hard_stop": {
          const h = msg.data as { message: string };
          next = { ...prev, hard_stop_message: h.message }; break;
        }
        case "error": {
          const e = msg.data as AppState["errors"][number];
          next = { ...prev, errors: [e, ...prev.errors].slice(0, 10) }; break;
        }
        default:
          next = prev; break;
      }
      persistState(next);
      return next;
    });
  }, []);

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        pingRef.current = setInterval(() => ws.send("ping"), PING_INTERVAL);
      };

      ws.onmessage = (e) => {
        try {
          const msg: WsMessage = JSON.parse(e.data);
          if (msg.event !== "pong") apply(msg);
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (pingRef.current) clearInterval(pingRef.current);
        reconnectTimer = setTimeout(connect, 3_000);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (pingRef.current) clearInterval(pingRef.current);
      wsRef.current?.close();
    };
  }, [apply]);

  return { state, connected };
}
