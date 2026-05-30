import { Panel } from "./Panel";
import type { Portfolio, OpenPosition } from "../types";

interface PortfolioPanelProps {
  portfolio: Portfolio;
  positions: OpenPosition[];
}

const INITIAL_BUDGET = 1000;

export function PortfolioPanel({ portfolio, positions }: PortfolioPanelProps) {
  const binanceBalance  = portfolio.binance_balance ?? portfolio.balance;
  const effectiveBudget = portfolio.trading_budget ?? INITIAL_BUDGET;
  const budgetPnl       = portfolio.budget_pnl ?? portfolio.pnl;
  const budgetPnlPct    = portfolio.budget_pnl_pct ?? portfolio.pnl_pct;
  const pnlPositive     = budgetPnl >= 0;

  const barPct = Math.max(0, Math.min(150, (effectiveBudget / INITIAL_BUDGET) * 100));

  return (
    <Panel title="Portfolio">
      <div className="p-4 space-y-4">
        {/* Binance Account Balance */}
        <div>
          <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: "#8888aa" }}>
            Binance Account
          </p>
          <p
            className="text-2xl font-bold tabular-nums"
            style={{ fontFamily: "'JetBrains Mono', monospace", color: "#e8e8f0" }}
          >
            ${binanceBalance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
        </div>

        {/* Divider */}
        <div style={{ height: "1px", background: "rgba(255,255,255,0.05)" }} />

        {/* Trading Budget */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>
              Trading Budget
            </span>
            <div className="flex items-center gap-1.5">
              <span
                className="text-sm font-semibold tabular-nums"
                style={{ fontFamily: "'JetBrains Mono', monospace", color: "#e8e8f0" }}
              >
                ${effectiveBudget.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              {budgetPnl !== 0 && (
                <span
                  className="text-[10px] tabular-nums font-medium"
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    color: pnlPositive ? "#22d27a" : "#f05060",
                  }}
                >
                  ({pnlPositive ? "+" : ""}{budgetPnl.toFixed(2)})
                </span>
              )}
            </div>
          </div>

          {/* Bar */}
          <div
            className="relative h-1.5 rounded-full overflow-hidden"
            style={{ background: "rgba(255,255,255,0.06)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${Math.min(100, barPct)}%`,
                background: pnlPositive
                  ? "linear-gradient(90deg, #22d27a, #22d27aaa)"
                  : "linear-gradient(90deg, #f05060, #f05060aa)",
                boxShadow: pnlPositive ? "0 0 8px rgba(34,210,122,0.5)" : "0 0 8px rgba(240,80,96,0.5)",
              }}
            />
          </div>

          <div className="flex justify-between">
            <span className="text-[10px]" style={{ color: "#44445a" }}>
              Base ${INITIAL_BUDGET.toLocaleString()}
            </span>
            <span
              className="text-[10px] tabular-nums font-medium"
              style={{ color: pnlPositive ? "#22d27a" : "#f05060" }}
            >
              {pnlPositive ? "+" : ""}{budgetPnlPct.toFixed(2)}% return
            </span>
          </div>
        </div>

        {/* Total PnL */}
        <div
          className="flex items-center justify-between rounded-lg px-3 py-2.5"
          style={{
            background: pnlPositive ? "rgba(34,210,122,0.08)" : "rgba(240,80,96,0.08)",
            border: `1px solid ${pnlPositive ? "rgba(34,210,122,0.2)" : "rgba(240,80,96,0.2)"}`,
          }}
        >
          <span className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>
            Total PnL
          </span>
          <div className="text-right">
            <p
              className="font-semibold tabular-nums text-sm"
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                color: pnlPositive ? "#22d27a" : "#f05060",
              }}
            >
              {pnlPositive ? "+" : ""}{budgetPnl.toFixed(2)} USDT
            </p>
            <p
              className="text-[10px] tabular-nums"
              style={{ color: pnlPositive ? "rgba(34,210,122,0.6)" : "rgba(240,80,96,0.6)" }}
            >
              {pnlPositive ? "+" : ""}{budgetPnlPct.toFixed(2)}%
            </p>
          </div>
        </div>

        {/* Open Positions */}
        {positions.length > 0 && (
          <div>
            <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "#44445a" }}>
              Open Positions ({positions.length})
            </p>
            <div className="space-y-1.5">
              {positions.map((pos, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-xs rounded-lg px-2.5 py-2"
                  style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.05)" }}
                >
                  <span className="font-semibold" style={{ color: "#e8e8f0" }}>{pos.symbol}</span>
                  <span
                    className="font-bold text-[11px]"
                    style={{ color: pos.side === "BUY" ? "#22d27a" : "#f05060" }}
                  >
                    {pos.side}
                  </span>
                  <span className="font-mono tabular-nums" style={{ color: "#8888aa" }}>{pos.qty}</span>
                  <span className="font-mono tabular-nums" style={{ color: "#e8e8f0" }}>
                    ${pos.price.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
