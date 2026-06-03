import { AlertTriangle, Clock, Info } from "lucide-react";
import { Panel } from "./Panel";
import type { ActivePosition } from "../types";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// Inline info icon + hover tooltip, placed next to a label.
function InfoDot({ tip, side = "left", vertical = "down" }: { tip: string; side?: "left" | "right"; vertical?: "up" | "down" }) {
  return (
    <span className="relative group inline-flex items-center" style={{ cursor: "help" }}>
      <Info size={11} style={{ opacity: 0.5 }} />
      <span
        role="tooltip"
        className="pointer-events-none opacity-0 group-hover:opacity-100"
        style={{
          position: "absolute",
          ...(vertical === "up" ? { bottom: "calc(100% + 6px)" } : { top: "calc(100% + 6px)" }),
          ...(side === "left" ? { left: 0 } : { right: 0 }),
          width: 200,
          padding: "6px 9px",
          borderRadius: 6,
          background: "#08080f",
          border: "1px solid rgba(0,212,255,0.2)",
          boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
          color: "#c8c8d8",
          fontSize: 10,
          lineHeight: 1.4,
          fontWeight: 400,
          textTransform: "none",
          letterSpacing: "normal",
          whiteSpace: "normal",
          textAlign: "left",
          zIndex: 20,
          transition: "opacity 0.15s ease",
        }}
      >
        {tip}
      </span>
    </span>
  );
}

interface PositionPanelProps {
  position: ActivePosition | null;
  tradingMode: "FUTURES" | "SPOT";
}

function fmt(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function pctDiff(a: number, b: number) {
  return b > 0 ? ((a - b) / b) * 100 : 0;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function ProgressBar({ pct, color }: { pct: number; color: string }) {
  const clamped = Math.min(100, Math.max(0, pct));
  return (
    <div
      className="h-1.5 w-full rounded-full overflow-hidden"
      style={{ background: "rgba(255,255,255,0.06)" }}
    >
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${clamped}%`,
          background: color,
          boxShadow: `0 0 6px ${color}80`,
        }}
      />
    </div>
  );
}

function DataCell({ label, value, highlight }: { label: string; value: string; highlight?: string }) {
  return (
    <div
      className="rounded-lg px-2.5 py-2 space-y-0.5"
      style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.05)" }}
    >
      <p className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>{label}</p>
      <p
        className="text-xs font-semibold tabular-nums"
        style={{ fontFamily: "'JetBrains Mono', monospace", color: highlight ?? "#e8e8f0" }}
      >
        {value}
      </p>
    </div>
  );
}

export function PositionPanel({ position, tradingMode }: PositionPanelProps) {
  async function toggleMode() {
    const next = tradingMode === "FUTURES" ? "SPOT" : "FUTURES";
    await fetch(`${API}/mode/${next}`, { method: "POST" }).catch(() => null);
  }

  const isLong = position?.side === "LONG";
  const sideColor = isLong ? "#22d27a" : "#f05060";
  const accentColor = position ? sideColor : undefined;

  const modeToggle = (
    <button
      onClick={toggleMode}
      className="text-[11px] font-semibold px-2.5 py-1 rounded transition-colors"
      style={{
        background: tradingMode === "FUTURES" ? "rgba(0,212,255,0.12)" : "rgba(136,136,170,0.08)",
        color: tradingMode === "FUTURES" ? "#00d4ff" : "#8888aa",
        border: `1px solid ${tradingMode === "FUTURES" ? "rgba(0,212,255,0.3)" : "rgba(136,136,170,0.2)"}`,
      }}
    >
      {tradingMode}
    </button>
  );

  if (!position) {
    return (
      <Panel title="Active Position" action={modeToggle}>
        <div className="p-4">
          <p className="text-xs italic" style={{ color: "#44445a" }}>No open position</p>
        </div>
      </Panel>
    );
  }

  const pnlPos = position.unrealized_pnl >= 0;
  const pnlPct = pctDiff(position.mark_price, position.entry_price) * position.leverage;
  const tp = position.tp_price;
  const sl = position.sl_price;

  const tpProgress = tp
    ? isLong
      ? Math.max(0, (position.mark_price - position.entry_price) / (tp - position.entry_price) * 100)
      : Math.max(0, (position.entry_price - position.mark_price) / (position.entry_price - tp) * 100)
    : null;

  const slDanger = sl
    ? isLong
      ? Math.max(0, (position.entry_price - position.mark_price) / (position.entry_price - sl) * 100)
      : Math.max(0, (position.mark_price - position.entry_price) / (sl - position.entry_price) * 100)
    : null;

  const estimatedTpPnl = tp
    ? ((tp - position.entry_price) * position.quantity * (isLong ? 1 : -1))
    : null;
  const estimatedSlLoss = sl
    ? ((sl - position.entry_price) * position.quantity * (isLong ? 1 : -1))
    : null;

  return (
    <Panel title="Active Position" action={modeToggle} accentColor={accentColor}>
      <div className="p-3 space-y-3">
        {/* Side + Symbol + Leverage */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className="text-sm font-bold tracking-wide"
              style={{ color: sideColor, textShadow: `0 0 8px ${sideColor}60` }}
            >
              {position.side}
            </span>
            <span className="text-xs font-medium" style={{ color: "#e8e8f0" }}>{position.symbol}</span>
            <span
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
              style={{ background: "rgba(255,255,255,0.06)", color: "#8888aa" }}
            >
              {position.leverage}×
            </span>
          </div>
          {position.open_time && (
            <div className="flex items-center gap-1 text-[10px]" style={{ color: "#44445a" }}>
              <Clock className="w-3 h-3" />
              {timeAgo(position.open_time)}
            </div>
          )}
        </div>

        {/* Entry / Mark / PnL grid */}
        <div className="grid grid-cols-3 gap-1.5">
          <DataCell label="Entry" value={`$${fmt(position.entry_price)}`} />
          <DataCell label="Mark" value={`$${fmt(position.mark_price)}`} />
          <div
            className="rounded-lg px-2.5 py-2 space-y-0.5"
            style={{
              background: pnlPos ? "rgba(34,210,122,0.08)" : "rgba(240,80,96,0.08)",
              border: `1px solid ${pnlPos ? "rgba(34,210,122,0.2)" : "rgba(240,80,96,0.2)"}`,
            }}
          >
            <p className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>PnL</p>
            <p
              className="text-xs font-bold tabular-nums"
              style={{ fontFamily: "'JetBrains Mono', monospace", color: pnlPos ? "#22d27a" : "#f05060" }}
            >
              {pnlPos ? "+" : ""}{position.unrealized_pnl.toFixed(2)}
            </p>
            <p
              className="text-[10px] tabular-nums"
              style={{ color: pnlPos ? "rgba(34,210,122,0.6)" : "rgba(240,80,96,0.6)" }}
            >
              {pnlPos ? "+" : ""}{pnlPct.toFixed(2)}%
            </p>
          </div>
        </div>

        {/* Take Profit */}
        {tp && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>Take Profit</span>
              <div className="flex items-center gap-2">
                <span className="font-mono tabular-nums font-semibold" style={{ color: "#22d27a" }}>
                  ${fmt(tp)}
                </span>
                {estimatedTpPnl !== null && (
                  <span className="text-[10px] font-mono tabular-nums" style={{ color: "rgba(34,210,122,0.6)" }}>
                    +${estimatedTpPnl.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
            {tpProgress !== null && <ProgressBar pct={tpProgress} color="#22d27a" />}
            <p className="text-[10px] text-right" style={{ color: "#44445a" }}>
              {tp > 0 ? `${Math.abs(pctDiff(tp, position.mark_price)).toFixed(2)}% away` : ""}
            </p>
          </div>
        )}

        {/* Stop Loss */}
        {sl && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>Stop Loss</span>
              <div className="flex items-center gap-2">
                <span className="font-mono tabular-nums font-semibold" style={{ color: "#f05060" }}>
                  ${fmt(sl)}
                </span>
                {estimatedSlLoss !== null && (
                  <span className="text-[10px] font-mono tabular-nums" style={{ color: "rgba(240,80,96,0.6)" }}>
                    {estimatedSlLoss.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
            {slDanger !== null && <ProgressBar pct={slDanger} color="#f05060" />}
            <p className="text-[10px] text-right" style={{ color: "#44445a" }}>
              {sl > 0 ? `${Math.abs(pctDiff(sl, position.mark_price)).toFixed(2)}% away` : ""}
            </p>
          </div>
        )}

        {/* Liquidation */}
        <div
          className="flex items-center justify-between rounded-lg px-3 py-2"
          style={{
            background: "rgba(240,80,96,0.05)",
            border: "1px solid rgba(240,80,96,0.2)",
          }}
        >
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3" style={{ color: "#f05060" }} />
            <span className="text-[10px] uppercase tracking-widest" style={{ color: "rgba(240,80,96,0.8)" }}>
              Liquidation
            </span>
            <InfoDot
              side="left"
              vertical="up"
              tip="Price at which Binance force-closes the position. In cross margin it sits far away — your full balance backs it — and your stop-loss triggers long before this."
            />
          </div>
          <span
            className="text-xs font-semibold tabular-nums font-mono"
            style={{ color: "#f05060" }}
          >
            ${fmt(position.liquidation_price)}
          </span>
        </div>
      </div>
    </Panel>
  );
}
