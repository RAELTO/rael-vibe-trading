import { Panel } from "./Panel";
import type { StrategyReview, TradeLesson } from "../types";

interface StrategyPanelProps {
  review: StrategyReview | null | undefined;
  lessons: TradeLesson[] | undefined;
}

function gradeColor(grade: string): string {
  const g = (grade || "").toUpperCase();
  if (g === "A" || g === "B") return "#22d27a";
  if (g === "C") return "#f0a030";
  if (g === "D" || g === "F") return "#f05060";
  return "#8888aa";
}

function GradeBadge({ grade }: { grade: string }) {
  const color = gradeColor(grade);
  return (
    <div
      className="flex items-center justify-center rounded-lg shrink-0"
      style={{
        width: 44, height: 44,
        border: `1px solid ${color}55`,
        background: `${color}12`,
        boxShadow: `0 0 14px ${color}22`,
      }}
    >
      <span
        className="font-bold"
        style={{ fontSize: 22, color, fontFamily: "'Space Grotesk', sans-serif", lineHeight: 1 }}
      >
        {(grade || "—").toUpperCase()}
      </span>
    </div>
  );
}

export function StrategyPanel({ review, lessons }: StrategyPanelProps) {
  const hasReview = !!review && !!review.summary;
  const list = lessons ?? [];

  return (
    <Panel title="Strategy Insights">
      <div className="p-4 space-y-4">
        {/* Daily review */}
        {hasReview ? (
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <GradeBadge grade={review!.grade} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>
                    Daily Review · {review!.review_date}
                  </span>
                  <span
                    className="text-[11px] font-semibold font-mono tabular-nums"
                    style={{ color: review!.net_pnl >= 0 ? "#22d27a" : "#f05060" }}
                  >
                    {review!.net_pnl >= 0 ? "+" : ""}{review!.net_pnl.toFixed(2)} USDT
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-[10px] font-mono" style={{ color: "#8888aa" }}>
                    Win {review!.win_rate}%
                  </span>
                  <span className="text-[10px] font-mono" style={{ color: "#44445a" }}>
                    {review!.total_trades} ops
                  </span>
                </div>
              </div>
            </div>

            <p
              className="text-[11px] leading-relaxed"
              style={{ color: "#c8c8d8", fontFamily: "'JetBrains Mono', monospace" }}
            >
              {review!.summary}
            </p>

            {review!.adjustments && review!.adjustments.length > 0 && (
              <div className="space-y-1.5" style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 12 }}>
                <p className="text-[10px] uppercase tracking-widest" style={{ color: "#44445a" }}>
                  Suggested Adjustments
                </p>
                {review!.adjustments.map((a, i) => (
                  <div key={i} className="flex gap-2">
                    <span style={{ color: "#00d4ff", fontSize: 11 }}>▸</span>
                    <span className="text-[11px] leading-snug" style={{ color: "#8888aa" }}>{a}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-16" style={{ color: "#44445a" }}>
            <span className="text-xs">No daily review yet — generated once trades close</span>
          </div>
        )}

        {/* Lessons learned */}
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 12 }} className="space-y-2">
          <p className="text-[10px] uppercase tracking-widest" style={{ color: "#44445a" }}>
            Lessons Learned ({list.length})
          </p>
          {list.length === 0 ? (
            <p className="text-[11px]" style={{ color: "#44445a" }}>
              Post-mortems will appear here after trades close.
            </p>
          ) : (
            <div className="space-y-2">
              {list.slice(0, 8).map((l, i) => {
                const win = l.outcome === "WIN";
                const color = win ? "#22d27a" : "#f05060";
                return (
                  <div
                    key={`${l.trade_id}-${i}`}
                    className="rounded-lg p-2.5"
                    style={{ background: "rgba(255,255,255,0.025)" }}
                  >
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span
                        className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
                        style={{ color, background: `${color}18` }}
                      >
                        {l.outcome} {l.pnl >= 0 ? "+" : ""}{l.pnl.toFixed(2)}
                      </span>
                      {l.tag && (
                        <span className="text-[10px] font-mono truncate" style={{ color: "#8888aa" }}>
                          {l.tag}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] leading-snug" style={{ color: "#c8c8d8" }}>
                      {l.lesson}
                    </p>
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
