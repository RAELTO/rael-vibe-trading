import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import { Info } from "lucide-react";
import { Panel } from "./Panel";
import { HoverTip } from "./HoverTip";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface PnLPoint {
  id: number;
  ts: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  leverage: number;
  notional: number;
  pnl: number;
  cumulative_pnl: number;
  exit_reason: string;
  mode: "FUTURES" | "SPOT";
}

function fmtSize(v: number | null | undefined): string {
  if (!v) return "—";
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

// Column header with a hover tooltip explaining the value.
function InfoHeader({ label, tip, tipSide = "right" }: { label: string; tip: string; tipSide?: "left" | "right" }) {
  return (
    <HoverTip tip={tip} align={tipSide}>
      {label}
      <Info size={11} style={{ opacity: 0.45 }} />
    </HoverTip>
  );
}

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "—";
  return v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmtTime(ts: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function reasonLabel(reason: string): string {
  const r = (reason || "").toUpperCase();
  if (r.includes("TAKE_PROFIT") || r === "TP") return "TP";
  if (r.includes("STOP_LOSS") || r === "SL") return "SL";
  if (r.includes("LIQUIDAT")) return "LIQ";
  if (r.includes("TRAIL")) return "TRAIL";
  return reason || "—";
}

// "YYYY-MM-DD" → ms at local start-of-day (matches the locale times shown in the table).
function dayStartMs(value: string): number | null {
  if (!value) return null;
  const [y, m, d] = value.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d).getTime();
}

const dateInputStyle: React.CSSProperties = {
  colorScheme: "dark",
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 6,
  color: "#c8c8d8",
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 10.5,
  padding: "3px 6px",
  minWidth: 0,
};

// Tabla de registro de trades — más reciente primero, con filtro por rango y scroll interno.
function TradesTable({ points }: { points: PnLPoint[] }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const fromMs = dayStartMs(from);
  const toMs = dayStartMs(to);
  const toEndMs = toMs != null ? toMs + 24 * 3600 * 1000 - 1 : null; // inclusive end-of-day

  const rows = [...points]
    .reverse()
    .filter((t) => {
      const ms = new Date(t.ts).getTime();
      if (isNaN(ms)) return true;
      if (fromMs != null && ms < fromMs) return false;
      if (toEndMs != null && ms > toEndMs) return false;
      return true;
    });

  const filtered = !!from || !!to;

  return (
    <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 12 }}>
      {/* Header: title + date-range filter */}
      <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
        <p className="text-[10px] uppercase tracking-widest" style={{ color: "#44445a" }}>
          Trade Log <span style={{ color: "#33334a" }}>({rows.length})</span>
        </p>
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => { setFrom(""); setTo(""); }}
            title="Clear date range — show all trades"
            className="text-[9px] uppercase tracking-wide rounded px-2 py-1 transition-colors"
            style={{
              color: filtered ? "#8888aa" : "#00d4ff",
              background: filtered ? "rgba(255,255,255,0.04)" : "rgba(0,212,255,0.12)",
              border: `1px solid ${filtered ? "rgba(255,255,255,0.08)" : "rgba(0,212,255,0.3)"}`,
              cursor: "pointer",
            }}
          >
            All
          </button>
          <span className="text-[9px] uppercase tracking-wide" style={{ color: "#44445a" }}>From</span>
          <input type="date" value={from} max={to || undefined}
            onChange={(e) => setFrom(e.target.value)} style={dateInputStyle} aria-label="From date" />
          <span className="text-[9px] uppercase tracking-wide" style={{ color: "#44445a" }}>To</span>
          <input type="date" value={to} min={from || undefined}
            onChange={(e) => setTo(e.target.value)} style={dateInputStyle} aria-label="To date" />
        </div>
      </div>

      {/* Scrollable table with sticky header */}
      <div style={{ maxHeight: 260, overflowY: "auto", overflowX: "auto" }}>
        <table className="w-full" style={{ borderCollapse: "collapse", fontFamily: "'JetBrains Mono', monospace" }}>
          <thead>
            <tr style={{ color: "#44445a", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em" }}>
              <th className="text-left font-medium py-1 pr-2"  style={stickyTh}>Time</th>
              <th className="text-left font-medium py-1 pr-2"  style={stickyTh}>Side</th>
              <th className="text-right font-medium py-1 pr-2" style={stickyTh}>
                <InfoHeader label="Entry" tip="Average fill price when the position was opened." />
              </th>
              <th className="text-right font-medium py-1 pr-2" style={stickyTh}>
                <InfoHeader label="Exit" tip="Price at which the position was closed." />
              </th>
              <th className="text-right font-medium py-1 pr-2" style={stickyTh}>
                <InfoHeader label="Size" tip="Position notional in USDT — the money placed on the trade." />
              </th>
              <th className="text-center font-medium py-1 pr-2" style={stickyTh}>
                <InfoHeader label="Reason" tip="How the trade closed: TP take-profit, SL stop-loss, LIQ liquidation, TRAIL trailing stop." />
              </th>
              <th className="text-right font-medium py-1"      style={stickyTh}>
                <InfoHeader label="PnL" tip="Realized profit/loss in USDT for the trade." />
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-4 text-center text-[11px]" style={{ color: "#44445a" }}>
                  No trades in selected range
                </td>
              </tr>
            ) : rows.map((t) => {
              const win = t.pnl >= 0;
              const sideColor = t.side === "LONG" ? "#22d27a" : "#f05060";
              return (
                <tr key={t.id} style={{ borderTop: "1px solid rgba(255,255,255,0.04)", fontSize: 10.5 }}>
                  <td className="py-1.5 pr-2" style={{ color: "#8888aa", whiteSpace: "nowrap" }}>{fmtTime(t.ts)}</td>
                  <td className="py-1.5 pr-2" style={{ color: sideColor, fontWeight: 700 }}>{t.side}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums" style={{ color: "#c8c8d8" }}>{fmtPrice(t.entry_price)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums" style={{ color: "#c8c8d8" }}>{fmtPrice(t.exit_price)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums" style={{ color: "#8888aa", whiteSpace: "nowrap" }}>{fmtSize(t.notional)}</td>
                  <td className="py-1.5 pr-2 text-center" style={{ color: "#8888aa" }}>{reasonLabel(t.exit_reason)}</td>
                  <td className="py-1.5 text-right tabular-nums font-semibold" style={{ color: win ? "#22d27a" : "#f05060" }}>
                    {win ? "+" : ""}{t.pnl.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const stickyTh: React.CSSProperties = {
  position: "sticky",
  top: 0,
  background: "#0a0a14",
  zIndex: 1,
  whiteSpace: "nowrap",
};

interface PnLTooltipProps {
  active?: boolean;
  payload?: { payload: PnLPoint }[];
}

function PnLTooltip({ active, payload }: PnLTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const pos = d.pnl >= 0;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs border shadow-xl"
      style={{ background: "#08080f", borderColor: "rgba(0,212,255,0.15)" }}
    >
      <p className="font-mono mb-1" style={{ color: "#8888aa" }}>
        {d.ts ? d.ts.slice(0, 16).replace("T", " ") : "—"}
      </p>
      <p className="font-semibold mb-0.5" style={{ color: "#e8e8f0" }}>{d.symbol} {d.side}</p>
      <p className="font-bold font-mono" style={{ color: pos ? "#22d27a" : "#f05060" }}>
        {pos ? "+" : ""}{d.pnl.toFixed(2)} USDT
      </p>
      <p className="font-mono" style={{ color: "#8888aa" }}>
        Cum: {d.cumulative_pnl >= 0 ? "+" : ""}{d.cumulative_pnl.toFixed(2)} USDT
      </p>
      <p className="mt-1 text-[10px]" style={{ color: d.mode === "FUTURES" ? "#00d4ff" : "#8888aa" }}>
        {d.mode} · {d.exit_reason}
      </p>
    </div>
  );
}

export function PnLChart() {
  const [points, setPoints] = useState<PnLPoint[]>([]);
  const [totalPnl, setTotalPnl] = useState(0);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API}/pnl-history?limit=50`);
        const data = await res.json();
        setPoints(data.points ?? []);
        setTotalPnl(data.total_pnl ?? 0);
      } catch {
        // backend not up
      }
    }
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const totalPos = totalPnl >= 0;
  const cumulColor = totalPos ? "#22d27a" : "#f05060";

  const titleAction = points.length > 0 ? (
    <span
      className="text-xs font-bold tabular-nums font-mono"
      style={{ color: totalPos ? "#22d27a" : "#f05060" }}
    >
      {totalPos ? "+" : ""}{totalPnl.toFixed(2)} USDT
    </span>
  ) : undefined;

  return (
    <Panel title="PnL History" action={titleAction}>
      <div className="p-4">
        {points.length === 0 ? (
          <p className="text-xs italic" style={{ color: "#44445a" }}>No closed trades yet</p>
        ) : (
          <div className="space-y-4">
            {/* Cumulative line */}
            <div>
              <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "#44445a" }}>
                Cumulative
              </p>
              <ResponsiveContainer width="100%" height={100}>
                <AreaChart data={points} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={cumulColor} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={cumulColor} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="id" hide />
                  <YAxis hide domain={["auto", "auto"]} />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" strokeDasharray="3 3" />
                  <Tooltip content={<PnLTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="cumulative_pnl"
                    stroke={cumulColor}
                    strokeWidth={2}
                    fill="url(#pnlGrad)"
                    dot={false}
                    activeDot={{ r: 3, fill: cumulColor }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Trade log table */}
            <TradesTable points={points} />
          </div>
        )}
      </div>
    </Panel>
  );
}
