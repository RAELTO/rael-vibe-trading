import { Panel } from "./Panel";
import type { NewsContext } from "../types";

interface NewsPanelProps {
  news: NewsContext | null;
}

function SentimentBar({ value }: { value: number }) {
  const isPos = value >= 0;
  const absPct = Math.abs(value) * 50;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] w-4 font-mono" style={{ color: "#f05060" }}>−1</span>
      <div
        className="flex-1 h-1.5 rounded-full overflow-hidden relative"
        style={{ background: "rgba(255,255,255,0.06)" }}
      >
        <div className="absolute inset-y-0 left-1/2 w-px" style={{ background: "rgba(255,255,255,0.12)" }} />
        <div
          className="absolute inset-y-0 rounded-full transition-all duration-500"
          style={{
            left: isPos ? "50%" : `${50 - absPct}%`,
            width: `${absPct}%`,
            background: isPos ? "#22d27a" : "#f05060",
            boxShadow: isPos ? "0 0 6px rgba(34,210,122,0.5)" : "0 0 6px rgba(240,80,96,0.5)",
          }}
        />
      </div>
      <span className="text-[10px] w-4 text-right font-mono" style={{ color: "#22d27a" }}>+1</span>
    </div>
  );
}

export function NewsPanel({ news }: NewsPanelProps) {
  return (
    <Panel title="Market Intelligence">
      {!news || news.message ? (
        <div className="flex items-center justify-center h-20 gap-2" style={{ color: "#44445a" }}>
          <span className="text-xs">No news data yet</span>
        </div>
      ) : (
        <div className="p-4 space-y-3">
          {/* Sentiment */}
          {typeof news.sentiment === "number" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>
                  Market Sentiment
                </span>
                <span
                  className="text-xs font-semibold tabular-nums font-mono"
                  style={{ color: news.sentiment > 0 ? "#22d27a" : news.sentiment < 0 ? "#f05060" : "#f0a030" }}
                >
                  {news.sentiment > 0 ? "+" : ""}{news.sentiment.toFixed(2)}
                </span>
              </div>
              <SentimentBar value={news.sentiment} />
            </div>
          )}

          {/* Impact */}
          {news.impact && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-widest" style={{ color: "#8888aa" }}>Impact</span>
              <span
                className="text-[11px] font-bold uppercase tracking-wide"
                style={{
                  color: news.impact === "HIGH" ? "#f05060" : news.impact === "MEDIUM" ? "#f0a030" : "#8888aa",
                }}
              >
                {news.impact}
              </span>
            </div>
          )}

          {/* Summary */}
          {news.summary && (
            <p
              className="text-[11px] leading-relaxed"
              style={{
                color: "#8888aa",
                fontFamily: "'JetBrains Mono', monospace",
                borderTop: "1px solid rgba(255,255,255,0.05)",
                paddingTop: "12px",
              }}
            >
              {news.summary}
            </p>
          )}

          {/* Asset scores */}
          {news.assets && Object.keys(news.assets).length > 0 && (
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: "12px" }} className="space-y-2">
              <p className="text-[10px] uppercase tracking-widest mb-1" style={{ color: "#44445a" }}>
                Asset Scores
              </p>
              {Object.entries(news.assets).map(([asset, score]) => (
                <div key={asset} className="flex items-center gap-2">
                  <span className="text-[11px] w-12 font-semibold" style={{ color: "#e8e8f0" }}>{asset}</span>
                  <div
                    className="flex-1 h-1 rounded-full overflow-hidden"
                    style={{ background: "rgba(255,255,255,0.06)" }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.abs(score) * 100}%`,
                        background: score > 0 ? "#22d27a" : "#f05060",
                      }}
                    />
                  </div>
                  <span
                    className="text-[10px] w-8 text-right tabular-nums font-mono"
                    style={{ color: score > 0 ? "#22d27a" : "#f05060" }}
                  >
                    {score > 0 ? "+" : ""}{score.toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
