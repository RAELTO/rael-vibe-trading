import { useQuery } from "@tanstack/react-query";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface MarketData {
  symbol: string;
  price: number;
  rsi: number;
  macd: number;
  bb_upper: number;
  bb_lower: number;
  ema20: number;
  ema50: number;
  volume: number;
  closes: number[];
  high_24h?: number;
  low_24h?: number;
  change_24h_pct?: number;
  basis_pct?: number;
  index_price?: number;
  funding_rate?: number;
  open_interest?: number;
  long_short_ratio?: number;
}

interface IndicatorCellProps {
  label: string;
  value: string;
  color?: string;
  dim?: boolean;
}

function IndicatorCell({ label, value, color, dim }: IndicatorCellProps) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.025)",
        padding: "7px 9px", borderRadius: 6,
        opacity: dim ? 0.45 : 1,
      }}
    >
      <div style={{
        fontSize: 9, color: "#44445a",
        fontFamily: "'JetBrains Mono', monospace",
        letterSpacing: "1px", marginBottom: 3,
      }}>
        {label}
      </div>
      <div style={{
        fontSize: 11, fontWeight: 600,
        fontFamily: "'JetBrains Mono', monospace",
        color: color ?? "#e8e8f0",
      }}>
        {value}
      </div>
    </div>
  );
}

async function fetchMarket(symbol: string): Promise<MarketData | null> {
  const res = await fetch(`${API}/market/${symbol}`);
  if (!res.ok) return null;
  const data = await res.json();
  if (data.error) return null;
  return data as MarketData;
}

interface MarketChartProps {
  symbol?: string;
  leverage?: number;
  cols?: 2 | 4;
}

export function MarketChart({ symbol = "BTCUSDT", leverage, cols = 4 }: MarketChartProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["market", symbol],
    queryFn: () => fetchMarket(symbol),
    retry: false,
    refetchInterval: 30_000,
    staleTime: 25_000,
  });

  const closes = data?.closes ?? [];
  const chartData = closes.map((c, i) => ({ i, price: c }));

  const chgPos     = (data?.change_24h_pct ?? 0) >= 0;
  const priceColor = chgPos ? "#22d27a" : "#f05060";

  const rsiColor    = data ? (data.rsi > 70 ? "#f05060" : data.rsi < 30 ? "#22d27a" : "#e8e8f0") : "#e8e8f0";
  const macdColor   = data ? (data.macd > 0 ? "#22d27a" : "#f05060") : "#e8e8f0";
  const basisColor  = data?.basis_pct != null
    ? (data.basis_pct > 0.1 ? "#f05060" : data.basis_pct < -0.1 ? "#22d27a" : "#e8e8f0")
    : "#e8e8f0";
  const lsColor     = data?.long_short_ratio != null
    ? (data.long_short_ratio > 1.5 ? "#f05060" : data.long_short_ratio < 0.7 ? "#22d27a" : "#e8e8f0")
    : "#e8e8f0";
  const fundingColor = data?.funding_rate != null
    ? (data.funding_rate > 0.05 ? "#f05060" : data.funding_rate < -0.05 ? "#22d27a" : "#e8e8f0")
    : "#e8e8f0";

  const yMin = closes.length ? Math.min(...closes) * 0.9995 : "auto";
  const yMax = closes.length ? Math.max(...closes) * 1.0005 : "auto";

  // Build indicators list (always 4-col grid)
  const indicators: IndicatorCellProps[] = [];
  if (data) {
    if (data.rsi != null)   indicators.push({ label: "RSI", value: data.rsi.toFixed(1), color: rsiColor });
    if (data.macd != null)  indicators.push({ label: "MACD", value: data.macd >= 0 ? `+${data.macd.toFixed(0)}` : data.macd.toFixed(0), color: macdColor });
    if (data.ema20 != null) indicators.push({ label: "EMA20", value: `${(data.ema20 / 1000).toFixed(2)}k` });
    if (data.ema50 != null) indicators.push({ label: "EMA50", value: `${(data.ema50 / 1000).toFixed(2)}k` });
    if (data.basis_pct != null)
      indicators.push({ label: "BB WIDTH", value: `${data.basis_pct.toFixed(2)}%`, color: basisColor });
    if (data.funding_rate != null)
      indicators.push({ label: "FUNDING", value: `${data.funding_rate >= 0 ? "+" : ""}${data.funding_rate.toFixed(4)}%`, color: fundingColor });
    if (data.open_interest != null)
      indicators.push({ label: "OI", value: `+${(data.open_interest / 1e6).toFixed(1)}M` });
    if (data.long_short_ratio != null)
      indicators.push({ label: "L/S RATIO", value: data.long_short_ratio.toFixed(2), color: lsColor });
  }

  return (
    <section className="glass-panel rounded-xl flex flex-col overflow-hidden animate-flow-in" style={{ minWidth: 0, height: "100%" }}>
      {/* Header — price inline */}
      <header
        className="flex items-center justify-between px-4 py-3 flex-wrap gap-2"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{
            fontSize: 10, fontWeight: 600, textTransform: "uppercase",
            letterSpacing: "0.12em", color: "#8888aa",
          }}>
            Market — {symbol}
          </span>
          {data && (
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{
                fontSize: 22, fontWeight: 700,
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: "-0.5px",
                color: priceColor,
                textShadow: `0 0 20px ${priceColor}40`,
                transition: "color 0.5s",
              }}>
                ${data.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              {data.change_24h_pct != null && (
                <span style={{
                  fontSize: 12, fontWeight: 600,
                  fontFamily: "'JetBrains Mono', monospace",
                  color: chgPos ? "#22d27a" : "#f05060",
                }}>
                  {data.change_24h_pct >= 0 ? "+" : ""}{data.change_24h_pct.toFixed(2)}%
                </span>
              )}
            </div>
          )}
        </div>
        <span style={{
          fontSize: 9, color: "#44445a",
          fontFamily: "'JetBrains Mono', monospace",
          letterSpacing: "1px",
        }}>
          24H{leverage ? ` · ${leverage}× LEVERAGE` : ""}
        </span>
      </header>

      {/* Body */}
      <div className="flex-1 p-4 flex flex-col gap-3">
        {isLoading || !data ? (
          <div className="flex-1 flex items-center justify-center text-xs" style={{ color: "#44445a" }}>
            {isLoading ? "Loading market data..." : "No market data — start the orchestrator"}
          </div>
        ) : (
          <>
            {/* Price chart — flex-1 grows on desktop; minHeight + absolute wrapper
                garantizan altura en móvil (ResponsiveContainer colapsa a 0 dentro de
                cadenas flex sin altura definida). */}
            {chartData.length > 0 && (
              <div style={{ flex: 1, minHeight: 180, position: "relative" }}>
                <div style={{ position: "absolute", inset: 0 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
                    <defs>
                      <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor={priceColor} stopOpacity={0.22} />
                        <stop offset="95%" stopColor={priceColor} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="i" hide />
                    <YAxis hide domain={[yMin, yMax]} />
                    <Tooltip
                      content={({ active, payload }) =>
                        active && payload?.[0] ? (
                          <div style={{
                            background: "#08080f", borderRadius: 6, padding: "6px 10px",
                            border: "1px solid rgba(0,212,255,0.15)",
                          }}>
                            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "#00d4ff" }}>
                              ${Number(payload[0].value).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                            </span>
                          </div>
                        ) : null
                      }
                    />
                    {data.bb_upper && <ReferenceLine y={data.bb_upper} stroke="rgba(167,139,250,0.35)" strokeDasharray="3 3" />}
                    {data.bb_lower && <ReferenceLine y={data.bb_lower} stroke="rgba(167,139,250,0.35)" strokeDasharray="3 3" />}
                    {data.ema20   && <ReferenceLine y={data.ema20}    stroke="rgba(240,160,48,0.45)"  strokeDasharray="2 4" />}
                    {data.ema50   && <ReferenceLine y={data.ema50}    stroke="rgba(34,210,122,0.45)"  strokeDasharray="2 4" />}
                    <Area
                      type="monotone" dataKey="price"
                      stroke={priceColor} strokeWidth={1.5}
                      fill="url(#priceGrad)" dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Indicators grid — 4 cols on desktop, 2 on tablet/mobile */}
            <div style={{
              display: "grid",
              gridTemplateColumns: `repeat(${cols}, 1fr)`,
              gap: 6,
              borderTop: "1px solid rgba(255,255,255,0.05)",
              paddingTop: 10,
            }}>
              {indicators.map(ind => (
                <IndicatorCell key={ind.label} {...ind} />
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
