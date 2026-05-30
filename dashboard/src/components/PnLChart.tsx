import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell, BarChart, Bar,
} from "recharts";
import { Panel } from "./Panel";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface PnLPoint {
  id: number;
  ts: string;
  symbol: string;
  side: string;
  pnl: number;
  cumulative_pnl: number;
  exit_reason: string;
  mode: "FUTURES" | "SPOT";
}

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

            {/* Per-trade bars */}
            <div>
              <p className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "#44445a" }}>
                Per Trade
                <span className="ml-2 font-mono" style={{ color: "#00d4ff" }}>■ Futures</span>
                <span className="ml-1.5 font-mono" style={{ color: "#44445a" }}>■ Spot</span>
              </p>
              <ResponsiveContainer width="100%" height={80}>
                <BarChart data={points} margin={{ top: 2, right: 4, left: 0, bottom: 0 }}>
                  <XAxis dataKey="id" hide />
                  <YAxis hide domain={["auto", "auto"]} />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
                  <Tooltip content={<PnLTooltip />} />
                  <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
                    {points.map((p, i) => (
                      <Cell
                        key={i}
                        fill={
                          p.pnl >= 0
                            ? p.mode === "FUTURES" ? "#00d4ff" : "#22d27a"
                            : p.mode === "FUTURES" ? "#f05060" : "#7f1d1d"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
