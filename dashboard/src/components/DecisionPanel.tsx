import { useEffect, useState } from "react";
import { Badge, decisionVariant } from "./Badge";
import type { DecisionEntry, ActivePosition } from "../types";

// Fallback si el backend aún no envió la config (evento WS "init")
const DEFAULT_CYCLE_SECONDS = 900;

interface DecisionPanelProps {
  decision: DecisionEntry | null;
  tradingMode?: string;
  intervalSeconds?: number;
  activePosition?: ActivePosition | null;
}

function translateDecision(d: string, mode?: string) {
  if (mode !== "FUTURES") return d;
  if (d === "BUY") return "LONG";
  if (d === "SELL") return "SHORT";
  return d;
}

function useCycleProgress(lastTs: string | null, cycleSeconds: number) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!lastTs) { setProgress(0); return; }
    function update() {
      const elapsed = (Date.now() - new Date(lastTs as string).getTime()) / 1000;
      setProgress(Math.max(0, Math.min(1, elapsed / cycleSeconds)));
    }
    update();
    const id = setInterval(update, 10_000);
    return () => clearInterval(id);
  }, [lastTs, cycleSeconds]);

  return progress;
}

function ConvictionGauge({ score, decision }: { score: number; decision?: string }) {
  const pct = Math.min(1, Math.abs(score));
  const isBuy  = decision === "BUY";
  const isSell = decision === "SELL";
  const arcColor  = isBuy ? "#22d27a" : isSell ? "#f05060" : "#f0a030";
  const glowColor = isBuy ? "rgba(34,210,122,0.4)" : isSell ? "rgba(240,80,96,0.4)" : "rgba(240,160,48,0.4)";

  const r = 36;
  const circumference = 2 * Math.PI * r;
  const dash = circumference * pct;

  return (
    <div className="flex flex-col items-center gap-1 shrink-0">
      <div className="relative" style={{ width: 92, height: 92 }}>
        <svg width="92" height="92" viewBox="0 0 92 92" style={{ transform: "rotate(-90deg)" }}>
          <circle cx="46" cy="46" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
          <circle
            cx="46" cy="46" r={r} fill="none"
            stroke={arcColor} strokeWidth="5"
            strokeDasharray={`${dash} ${circumference}`}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 5px ${glowColor})` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-0">
          <span style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 16, fontWeight: 700, color: arcColor, lineHeight: 1,
          }}>
            {(pct * 100).toFixed(0)}%
          </span>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 8, color: arcColor, letterSpacing: "1px", opacity: 0.7,
          }}>
            CONVICTION
          </span>
        </div>
      </div>
    </div>
  );
}

function parseReason(raw: string): string {
  if (!raw.startsWith("[")) return raw;
  const parts = raw.split(" | ");
  const first = parts[0] ?? raw;
  const cleaned = first.replace(/^\[[^\]]+\]\s*\w+\s*\([^)]+\):\s*/, "").trim();
  return cleaned || first;
}

export function DecisionPanel({ decision, tradingMode, intervalSeconds, activePosition }: DecisionPanelProps) {
  const cycleSeconds = intervalSeconds ?? DEFAULT_CYCLE_SECONDS;
  const cycleProgress = useCycleProgress(decision?.ts ?? null, cycleSeconds);
  const minutesLeft = Math.max(0, Math.round((1 - cycleProgress) * (cycleSeconds / 60)));

  // Con una posición abierta el decisor se pausa (máx. 1 posición) hasta que
  // la operación cierre por TP/SL. Mostramos eso en vez de "NEXT CYCLE 0m".
  const isPaused = !!activePosition;

  const sigColor = !decision
    ? "#8888aa"
    : decision.decision === "BUY"  ? "#22d27a"
    : decision.decision === "SELL" ? "#f05060"
    : "#f0a030";

  return (
    <section className="glass-panel rounded-xl flex flex-col overflow-hidden animate-flow-in" style={{ height: "100%" }}>
      {/* Header */}
      <header
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <h2 style={{
          fontSize: 10, fontWeight: 600, textTransform: "uppercase",
          letterSpacing: "0.12em", color: "#8888aa",
        }}>
          Last Decision
        </h2>

        {/* Cycle progress / paused indicator */}
        {isPaused ? (
          <div className="flex items-center gap-1.5">
            <span className="animate-pulse-dot" style={{
              width: 6, height: 6, borderRadius: "50%",
              background: "#f0a030", boxShadow: "0 0 6px #f0a030",
            }} />
            <span style={{
              fontSize: 9, color: "#f0a030",
              fontFamily: "'JetBrains Mono', monospace",
              whiteSpace: "nowrap", letterSpacing: "0.5px",
            }}>
              PAUSED · IN POSITION
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div style={{ height: 2, width: 44, background: "rgba(255,255,255,0.07)", borderRadius: 1, overflow: "hidden" }}>
              <div style={{
                width: `${cycleProgress * 100}%`, height: "100%",
                background: "#00d4ff",
                boxShadow: "0 0 4px #00d4ff",
                transition: "width 10s linear",
              }} />
            </div>
            <span style={{
              fontSize: 9, color: "#44445a",
              fontFamily: "'JetBrains Mono', monospace",
              whiteSpace: "nowrap",
            }}>
              NEXT CYCLE {minutesLeft}m
            </span>
          </div>
        )}
      </header>

      {/* Body */}
      <div className="flex-1 p-4">
        {!decision ? (
          <div className="flex items-center justify-center h-24" style={{ color: "#44445a" }}>
            <span className="text-xs">Waiting for first decision...</span>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
            {/* Gauge */}
            <ConvictionGauge score={decision.score} decision={decision.decision} />

            {/* Content */}
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Symbol + signal */}
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
                <span style={{
                  fontSize: 18, fontWeight: 700,
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: "-0.5px", color: "#e8e8f0",
                }}>
                  {decision.symbol}
                </span>
                <span style={{
                  fontSize: 11, fontWeight: 800,
                  color: sigColor,
                  background: `${sigColor}22`,
                  border: `1px solid ${sigColor}50`,
                  padding: "3px 12px", borderRadius: 6,
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: "2px",
                  boxShadow: `0 0 12px ${sigColor}30`,
                }}>
                  {translateDecision(decision.decision, tradingMode)}
                </span>
              </div>

              {/* Synthesis reasoning label */}
              <div style={{
                fontSize: 9, color: "#44445a",
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: "1px", marginBottom: 6,
              }}>
                SYNTHESIS REASONING
              </div>

              {/* Reasoning text */}
              <p style={{
                fontSize: 11,
                color: "#8888aa",
                lineHeight: 1.7,
                fontFamily: "'JetBrains Mono', monospace",
                margin: 0,
                display: "-webkit-box",
                WebkitLineClamp: 6,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              } as React.CSSProperties}>
                {parseReason(decision.reason)}
              </p>

              {/* Timestamp */}
              <div style={{
                marginTop: 10, fontSize: 10, color: "#44445a",
                fontFamily: "'JetBrains Mono', monospace",
              }}>
                {new Date(decision.ts).toLocaleTimeString([], {
                  hour: "2-digit", minute: "2-digit", second: "2-digit",
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
