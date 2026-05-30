import { Badge, decisionVariant } from "./Badge";
import type { AgentVote } from "../types";

// Phase classification
const PIPELINE_ROLES: Record<string, "phase1" | "synthesis" | "gate" | "primary" | "audit"> = {
  "technical": "phase1",
  "sentiment": "phase1",
  "quant":     "phase1",
  "synthesis": "synthesis",
  "gate":      "gate",
  "deepseek-decision": "primary",
  "claude-auditor":    "audit",
};

const PHASE_COLORS: Record<string, string> = {
  phase1:    "#00d4ff",
  synthesis: "#a78bfa",
  gate:      "#f0a030",
  primary:   "#a78bfa",
  audit:     "#f0a030",
};

const AGENT_WEIGHTS: Record<string, number> = {
  "synthesis":    1.00,
  "technical":    0.50,
  "sentiment":    0.50,
  "quant":        0.50,
  "claude-sonnet": 0.38,
  "qwen-api":      0.20,
  "deepseek-v3":   0.18,
  "gpt-5.4-nano":  0.14,
  "kronos-mini":   0.05,
  "local-qwen":    0.05,
};

function agentWeight(id: string): number {
  if (id in AGENT_WEIGHTS) return AGENT_WEIGHTS[id];
  for (const [key, w] of Object.entries(AGENT_WEIGHTS)) {
    if (id.toLowerCase().includes(key.toLowerCase())) return w;
  }
  return 0;
}

function translateVote(vote: string, tradingMode?: string): string {
  if (tradingMode !== "FUTURES") return vote;
  if (vote === "BUY") return "LONG";
  if (vote === "SELL") return "SHORT";
  return vote;
}

function getPhase(agentId: string): "phase1" | "synthesis" | "gate" | "primary" | "audit" | null {
  const base = agentId.split("(")[0].trim().toLowerCase();
  return PIPELINE_ROLES[base] ?? null;
}

// ── Gradient divider (matches prototype exactly) ────────────────────────────
function PhaseDivider({ label, color }: { label: string; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "16px 0" }}>
      <div style={{
        flex: 1, height: 1,
        background: `linear-gradient(90deg, transparent, ${color}40, ${color}, ${color}40, transparent)`,
      }} />
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "5px 16px", borderRadius: 20,
        background: `${color}18`,
        border: `1px solid ${color}40`,
      }}>
        <div style={{
          width: 6, height: 6, borderRadius: "50%",
          background: color, boxShadow: `0 0 6px ${color}`,
        }} />
        <span style={{
          fontSize: 9, fontWeight: 700, color,
          fontFamily: "'JetBrains Mono', monospace",
          letterSpacing: "2px",
        }}>
          {label}
        </span>
      </div>
      <div style={{
        flex: 1, height: 1,
        background: `linear-gradient(90deg, transparent, ${color}40, ${color}, ${color}40, transparent)`,
      }} />
    </div>
  );
}

// ── Technical indicator chip (RSI/MACD/EMA the decision was based on) ───────
function IndChip({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <span style={{
      fontSize: 10, fontFamily: "'JetBrains Mono', monospace",
      background: "rgba(255,255,255,0.04)", borderRadius: 5, padding: "2px 7px",
      whiteSpace: "nowrap",
    }}>
      <span style={{ color: "#44445a", marginRight: 4 }}>{label}</span>
      <span style={{ color: color ?? "#e8e8f0", fontWeight: 600 }}>{value}</span>
    </span>
  );
}

// ── Single agent card (matches prototype AgentCard) ─────────────────────────
function AgentCard({ vote, tradingMode, phaseKey }: {
  vote: AgentVote;
  tradingMode?: string;
  phaseKey: "phase1" | "synthesis" | "gate" | "primary" | "audit" | "ensemble";
}) {
  const phaseColor = phaseKey === "ensemble"
    ? "#8888aa"
    : PHASE_COLORS[phaseKey] ?? "#8888aa";

  const [baseName, modelName] = vote.agent_id.includes("(")
    ? vote.agent_id.split("(").map((s, i) => i === 1 ? s.replace(")", "").trim() : s.trim())
    : [vote.agent_id.trim(), null];

  const translatedVote = translateVote(vote.vote, tradingMode);
  const sigColor = vote.vote === "BUY"
    ? "#22d27a" : vote.vote === "SELL"
    ? "#f05060" : "#f0a030";
  const sigBg = vote.vote === "BUY"
    ? "rgba(34,210,122,0.12)" : vote.vote === "SELL"
    ? "rgba(240,80,96,0.12)" : "rgba(240,160,48,0.12)";

  const pct = Math.round(vote.confidence * 100);

  const phaseLabelText =
    phaseKey === "phase1"    ? "PHASE1"
    : phaseKey === "synthesis" ? "SYNTHESIS"
    : phaseKey === "gate"      ? "GATE"
    : getPhase(vote.agent_id) === "primary" ? "PRIMARY"
    : getPhase(vote.agent_id) === "audit" ? "AUDIT"
    : `${(agentWeight(vote.agent_id) * 100).toFixed(0)}%`;

  return (
    <div
      className="animate-flow-in"
      style={{
        padding: "14px 16px",
        position: "relative",
        overflow: "hidden",
        background: "rgba(255,255,255,0.026)",
        border: `1px solid ${phaseColor}35`,
        borderRadius: "10px",
        boxShadow: `0 0 20px ${phaseColor}12`,
        // Flex column so reasoning grows to fill height (equalizes Phase 1 grid cards)
        display: "flex",
        flexDirection: "column",
        height: phaseKey === "phase1" ? "100%" : undefined,
      }}
    >
      {/* Top glow bar */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: `linear-gradient(90deg, transparent, ${phaseColor}, transparent)`,
        opacity: 0.7,
      }} />

      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: "#e8e8f0", fontFamily: "'Space Grotesk', sans-serif" }}>
            {baseName}
          </span>
          {modelName && (
            <span style={{
              fontSize: 10,
              fontFamily: "'JetBrains Mono', monospace",
              color: "#44445a",
              background: "rgba(255,255,255,0.05)",
              padding: "2px 6px",
              borderRadius: 4,
            }}>
              {modelName}
            </span>
          )}
          <span style={{
            fontSize: 10, fontWeight: 600,
            color: phaseColor,
            background: `${phaseColor}18`,
            padding: "2px 8px",
            borderRadius: 20,
            letterSpacing: "0.5px",
          }}>
            {phaseLabelText}
          </span>
        </div>
        {/* Signal badge */}
        <span style={{
          fontSize: 11, fontWeight: 700,
          color: sigColor,
          background: sigBg,
          padding: "3px 10px",
          borderRadius: 20,
          fontFamily: "'JetBrains Mono', monospace",
          letterSpacing: "1px",
          border: `1px solid ${sigColor}30`,
        }}>
          {translatedVote}
        </span>
      </div>

      {/* Confidence bar */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
          <span style={{
            fontSize: 10, color: "#44445a",
            fontFamily: "'JetBrains Mono', monospace",
            letterSpacing: "0.5px",
          }}>
            CONFIDENCE
          </span>
          <span style={{
            fontSize: 10, fontWeight: 700,
            color: phaseColor,
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            {pct}%
          </span>
        </div>
        <div style={{ height: 3, background: "rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
          <div style={{
            width: `${pct}%`, height: "100%",
            background: phaseColor,
            borderRadius: 2,
            boxShadow: `0 0 6px ${phaseColor}80`,
            transition: "width 0.8s ease",
          }} />
        </div>
      </div>

      {/* Technical chips — los indicadores que el decisor consideró (solo si vienen con el voto) */}
      {vote.indicators && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
          {vote.indicators.rsi != null && (
            <IndChip label="RSI" value={vote.indicators.rsi.toFixed(1)}
              color={vote.indicators.rsi > 70 ? "#f05060" : vote.indicators.rsi < 30 ? "#22d27a" : "#e8e8f0"} />
          )}
          {vote.indicators.macd != null && (
            <IndChip label="MACD" value={vote.indicators.macd >= 0 ? `+${vote.indicators.macd.toFixed(0)}` : vote.indicators.macd.toFixed(0)}
              color={vote.indicators.macd >= 0 ? "#22d27a" : "#f05060"} />
          )}
          {vote.indicators.ema20 != null && (
            <IndChip label="EMA20" value={`${(vote.indicators.ema20 / 1000).toFixed(2)}k`} />
          )}
          {vote.indicators.ema50 != null && (
            <IndChip label="EMA50" value={`${(vote.indicators.ema50 / 1000).toFixed(2)}k`} />
          )}
        </div>
      )}

      {/* Reasoning — flex:1 for phase1 so all cards in the row share the tallest height */}
      <p style={{
        fontSize: 11,
        color: "#8888aa",
        lineHeight: 1.6,
        fontFamily: "'JetBrains Mono', monospace",
        margin: 0,
        flex: phaseKey === "phase1" ? 1 : undefined,
      } as React.CSSProperties}>
        {vote.reasoning}
      </p>
    </div>
  );
}

// ── Ensemble card (legacy weighted voting) ──────────────────────────────────
function EnsembleCard({ vote, tradingMode }: { vote: AgentVote; tradingMode?: string }) {
  return <AgentCard vote={vote} tradingMode={tradingMode} phaseKey="ensemble" />;
}

// ── Main panel ──────────────────────────────────────────────────────────────
interface AgentVotesPanelProps {
  votes: AgentVote[];
  tradingMode?: string;
  cols?: 1 | 3;
}

function isPipelineMode(votes: AgentVote[]): boolean {
  return votes.some(v => getPhase(v.agent_id) !== null);
}

export function AgentVotesPanel({ votes, tradingMode, cols = 3 }: AgentVotesPanelProps) {
  // Deduplicate: latest vote per agent
  const seen = new Set<string>();
  const current: AgentVote[] = [];
  for (const v of votes) {
    if (!seen.has(v.agent_id)) {
      seen.add(v.agent_id);
      current.push(v);
    }
  }

  const pipeline = isPipelineMode(current);

  if (!pipeline) {
    // Ensemble fallback — original weighted list
    const sorted = [...current].sort((a, b) => agentWeight(b.agent_id) - agentWeight(a.agent_id));
    return (
      <section className="glass-panel rounded-xl flex flex-col overflow-hidden animate-flow-in">
        <header
          className="flex items-center justify-between px-4 py-3"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
        >
          <h2 className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#8888aa" }}>
            Agent Votes
          </h2>
        </header>
        <div style={{ padding: 16, display: "grid", gridTemplateColumns: cols === 1 ? "1fr" : "repeat(auto-fit, minmax(200px, 1fr))", gap: 8 }}>
          {sorted.map(v => <EnsembleCard key={v.agent_id} vote={v} tradingMode={tradingMode} />)}
        </div>
      </section>
    );
  }

  // Pipeline / single-decision mode
  const primary = current.filter(v => {
    const phase = getPhase(v.agent_id);
    return phase === "primary" || phase === "audit";
  });
  const phase1 = current.filter(v => getPhase(v.agent_id) === "phase1");
  const synthesis = current.find(v => getPhase(v.agent_id) === "synthesis");
  const gate = current.find(v => getPhase(v.agent_id) === "gate");

  return (
    <section className="glass-panel rounded-xl overflow-hidden animate-flow-in">
      {/* Panel header */}
      <header
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <h2 className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#8888aa" }}>
          Analysis Pipeline
        </h2>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%",
            background: "#00d4ff", boxShadow: "0 0 6px #00d4ff",
            animation: "pulse-dot 1.5s ease-in-out infinite",
          }} />
          <span style={{
            fontSize: 9, color: "#00d4ff",
            fontFamily: "'JetBrains Mono', monospace",
            letterSpacing: "1px",
            fontWeight: 700,
          }}>
            {primary.length > 0 ? "DECISION ENGINE" : "PHASE 1 - SPECIALISTS"}
          </span>
        </div>
      </header>

      <div className="p-4">
        {/* Single-decision mode */}
        {primary.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8, marginBottom: 4 }}>
            {primary.map((v) => {
              const phase = getPhase(v.agent_id);
              return (
                <AgentCard
                  key={v.agent_id}
                  vote={v}
                  tradingMode={tradingMode}
                  phaseKey={phase === "audit" ? "audit" : "primary"}
                />
              );
            })}
          </div>
        )}

        {/* Phase 1 — responsive grid: 3-col desktop, 1-col tablet/mobile */}
        {phase1.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: cols === 1 ? "1fr" : "repeat(auto-fit, minmax(200px, 1fr))",
              gap: 8,
              marginBottom: 4,
              alignItems: "stretch",  // all cells same height → cards stretch uniformly
            }}
          >
            {phase1.map((v, i) => (
              <div key={v.agent_id} style={{ animationDelay: `${i * 80}ms` }}>
                <AgentCard vote={v} tradingMode={tradingMode} phaseKey="phase1" />
              </div>
            ))}
          </div>
        )}

        {/* Phase 2 — Synthesis */}
        {synthesis && (
          <>
            <PhaseDivider label="PHASE 2 — SYNTHESIS" color="#a78bfa" />
            <AgentCard vote={synthesis} tradingMode={tradingMode} phaseKey="synthesis" />
          </>
        )}

        {/* Phase 3 — Risk Gate */}
        {gate && (
          <>
            <PhaseDivider label="PHASE 3 — RISK GATE" color="#f0a030" />
            <AgentCard vote={gate} tradingMode={tradingMode} phaseKey="gate" />
          </>
        )}

        {primary.length === 0 && phase1.length === 0 && !synthesis && !gate && (
          <p className="text-xs italic py-2" style={{ color: "#44445a" }}>
            Waiting for agents...
          </p>
        )}
      </div>

      {/* Recent history */}
      {votes.length > current.length && (
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          <p
            className="text-[10px] uppercase tracking-wider px-4 py-2"
            style={{ color: "#44445a" }}
          >
            Recent
          </p>
          <div className="pb-2">
            {votes.slice(current.length, current.length + 5).map((v, i) => {
              const phase = getPhase(v.agent_id);
              const phaseColor = phase ? PHASE_COLORS[phase] : "#8888aa";
              const translatedVote = translateVote(v.vote, tradingMode);
              const sigColor = v.vote === "BUY" ? "#22d27a" : v.vote === "SELL" ? "#f05060" : "#f0a030";
              return (
                <div
                  key={i}
                  className="flex items-center gap-3 px-4 py-1.5"
                  style={{
                    opacity: 0.45,
                    borderTop: "1px solid rgba(255,255,255,0.04)",
                  }}
                >
                  <span
                    className="text-[11px] truncate flex-1 font-mono"
                    style={{ color: "#8888aa" }}
                  >
                    {v.agent_id.split("(")[0].trim()}
                  </span>
                  {phase && (
                    <span style={{
                      fontSize: 9, color: phaseColor,
                      background: `${phaseColor}15`,
                      padding: "1px 6px", borderRadius: 10,
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 600,
                    }}>
                      {phase.toUpperCase()}
                    </span>
                  )}
                  <span style={{
                    fontSize: 10, fontWeight: 700,
                    color: sigColor,
                    fontFamily: "'JetBrains Mono', monospace",
                  }}>
                    {translatedVote}
                  </span>
                  <span className="text-[10px] font-mono" style={{ color: "#44445a" }}>
                    {new Date(v.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
