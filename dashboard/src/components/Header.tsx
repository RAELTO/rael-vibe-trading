import { Badge } from "./Badge";
import type { SystemStatus, RiskHealth } from "../types";

interface HeaderProps {
  connected: boolean;
  status: SystemStatus;
  cycle: number;
  riskHealth: RiskHealth;
  tradingMode: "FUTURES" | "SPOT";
}

export function Header({ connected, status, cycle, riskHealth, tradingMode }: HeaderProps) {
  const statusVariant = status === "running" ? "running" : status === "stopped" ? "stopped" : "idle";
  const riskVariantMap: Record<RiskHealth, "healthy" | "moderate" | "high" | "critical"> = {
    HEALTHY: "healthy", MODERATE: "moderate", HIGH_RISK: "high", CRITICAL: "critical",
  };

  return (
    <header
      className="flex items-center justify-between px-6 py-3 sticky top-0 z-10"
      style={{
        background: "rgba(3,3,10,0.85)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        backdropFilter: "blur(16px)",
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3">
        {/* Hex icon */}
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <path
            d="M12 2L21 7V17L12 22L3 17V7L12 2Z"
            stroke="#00d4ff"
            strokeWidth="1.5"
            fill="rgba(0,212,255,0.08)"
          />
          <circle cx="12" cy="12" r="3" fill="#00d4ff" fillOpacity="0.6" />
        </svg>
        <div className="flex items-center gap-2">
          <span
            className="font-bold text-sm tracking-tight"
            style={{ color: "#e8e8f0", fontFamily: "'Space Grotesk', sans-serif" }}
          >
            Vibe Trading
          </span>
          <span style={{ color: "#44445a", fontSize: "11px" }}>/ Agent Dashboard</span>
        </div>
      </div>

      {/* Right badges */}
      <div className="flex items-center gap-2.5">
        <Badge variant={tradingMode === "FUTURES" ? "futures" : "spot"}>{tradingMode}</Badge>
        <Badge variant={riskVariantMap[riskHealth]}>{riskHealth.replace("_", " ")}</Badge>
        <Badge variant={statusVariant}>{status}</Badge>
        {cycle > 0 && (
          <span
            className="text-[11px] font-mono tabular-nums"
            style={{ color: "#44445a" }}
          >
            #{cycle}
          </span>
        )}

        {/* Live indicator */}
        <div className="flex items-center gap-1.5 pl-1">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: connected ? "#00d4ff" : "#f05060",
              boxShadow: connected ? "0 0 6px #00d4ff" : "0 0 6px #f05060",
              animation: "pulse-dot 1.5s ease-in-out infinite",
            }}
          />
          <span
            className="text-[11px] font-medium"
            style={{ color: connected ? "#00d4ff" : "#f05060" }}
          >
            {connected ? "Live" : "Reconnecting"}
          </span>
        </div>
      </div>
    </header>
  );
}
