import { useEffect, useState } from "react";
import { Panel } from "./Panel";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface Bucket {
  bucket: string;
  n: number;
  tp_first: number;
  sl_first: number;
  expired: number;
  tp_first_rate: number | null;
}

interface Summary {
  total: number;
  directional: number;
  resolved: number;
  pending: number;
  executed: number;
  by_direction: Record<string, number>;
}

const GREEN = "#22d27a";
const RED = "#f05060";
const MUTED = "#8888aa";
const DIM = "#44445a";

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-wider" style={{ color: DIM }}>{label}</span>
      <span className="text-sm font-bold font-mono tabular-nums" style={{ color: color ?? "#e8e8f0" }}>
        {value}
      </span>
    </div>
  );
}

export function ShadowPanel() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [calibration, setCalibration] = useState<Bucket[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API}/shadow/calibration`);
        const data = await res.json();
        setSummary(data.summary ?? null);
        setCalibration(data.calibration ?? []);
      } catch {
        // backend not up
      }
    }
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const buy = summary?.by_direction?.BUY ?? 0;
  const sell = summary?.by_direction?.SELL ?? 0;
  const dirTotal = buy + sell;
  const sellPct = dirTotal > 0 ? (sell / dirTotal) * 100 : 50;
  const skewed = dirTotal >= 5 && (sellPct >= 80 || sellPct <= 20);

  const action = summary ? (
    <span className="text-[10px] font-mono tabular-nums" style={{ color: MUTED }}>
      {summary.resolved}/{summary.directional} resolved
    </span>
  ) : undefined;

  return (
    <Panel title="Shadow Calibration" action={action}>
      <div className="p-4 flex flex-col gap-4">
        {/* Summary stats */}
        <div className="grid grid-cols-4 gap-3">
          <Stat label="Signals" value={summary?.directional ?? 0} />
          <Stat label="Pending" value={summary?.pending ?? 0} color={MUTED} />
          <Stat label="Resolved" value={summary?.resolved ?? 0} />
          <Stat
            label="Executed"
            value={`${summary?.executed ?? 0}/${summary?.directional ?? 0}`}
          />
        </div>

        {/* Directional bias (vigila el sesgo short 8/8) */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="text-[9px] uppercase tracking-wider" style={{ color: DIM }}>
              Direction bias
            </span>
            <span className="text-[10px] font-mono tabular-nums" style={{ color: skewed ? RED : MUTED }}>
              {buy} BUY · {sell} SELL{skewed ? " ⚠" : ""}
            </span>
          </div>
          <div className="flex h-2 rounded-full overflow-hidden" style={{ background: "#1a1a28" }}>
            <div style={{ width: `${100 - sellPct}%`, background: GREEN }} title={`${buy} BUY`} />
            <div style={{ width: `${sellPct}%`, background: RED }} title={`${sell} SELL`} />
          </div>
        </div>

        {/* Calibration curve: tasa TP-first por bucket de confianza */}
        <div className="flex flex-col gap-2">
          <span className="text-[9px] uppercase tracking-wider" style={{ color: DIM }}>
            TP-first rate by confidence
          </span>
          {calibration.length === 0 ? (
            <p className="text-xs italic" style={{ color: DIM }}>
              {(summary?.pending ?? 0) > 0
                ? "Accumulating — signals not resolved yet."
                : "No signals yet."}
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {calibration.map((b) => {
                const rate = b.tp_first_rate;
                const pct = rate == null ? 0 : rate * 100;
                const color = rate == null ? DIM : rate >= 0.5 ? GREEN : RED;
                return (
                  <div key={b.bucket} className="flex items-center gap-2">
                    <span className="text-[10px] font-mono tabular-nums w-20 shrink-0" style={{ color: MUTED }}>
                      {b.bucket}
                    </span>
                    <div className="flex-1 h-3 rounded-sm overflow-hidden" style={{ background: "#14141f" }}>
                      <div
                        className="h-full rounded-sm transition-all"
                        style={{ width: `${pct}%`, background: color }}
                      />
                    </div>
                    <span className="text-[10px] font-mono tabular-nums w-24 text-right shrink-0" style={{ color }}>
                      {rate == null ? "—" : `${pct.toFixed(0)}%`}
                      <span style={{ color: DIM }}> (n={b.n})</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
