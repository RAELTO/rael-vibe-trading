import type { ReactNode } from "react";
import type { Decision, RiskHealth } from "../types";

interface BadgeProps {
  children: ReactNode;
  variant: "buy" | "sell" | "hold" | "healthy" | "moderate" | "high" | "critical" | "idle" | "running" | "stopped" | "neutral" | "futures" | "spot";
}

const VARIANTS: Record<BadgeProps["variant"], string> = {
  buy:      "text-[#22d27a] border-[#22d27a40] bg-[rgba(34,210,122,0.12)]",
  sell:     "text-[#f05060] border-[#f0506040] bg-[rgba(240,80,96,0.12)]",
  hold:     "text-[#f0a030] border-[#f0a03040] bg-[rgba(240,160,48,0.12)]",
  healthy:  "text-[#22d27a] border-[#22d27a40] bg-[rgba(34,210,122,0.12)]",
  moderate: "text-[#f0a030] border-[#f0a03040] bg-[rgba(240,160,48,0.12)]",
  high:     "text-[#f05060] border-[#f0506040] bg-[rgba(240,80,96,0.12)]",
  critical: "text-[#f05060] border-[#f0506060] bg-[rgba(240,80,96,0.2)]",
  idle:     "text-[#8888aa] border-[#8888aa30] bg-[rgba(136,136,170,0.08)]",
  running:  "text-[#00d4ff] border-[#00d4ff40] bg-[rgba(0,212,255,0.12)]",
  stopped:  "text-[#8888aa] border-[#8888aa30] bg-[rgba(136,136,170,0.08)]",
  neutral:  "text-[#8888aa] border-[#8888aa30] bg-[rgba(136,136,170,0.08)]",
  futures:  "text-[#00d4ff] border-[#00d4ff40] bg-[rgba(0,212,255,0.12)]",
  spot:     "text-[#8888aa] border-[#8888aa30] bg-[rgba(136,136,170,0.08)]",
};

export function Badge({ children, variant }: BadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[11px] font-semibold tracking-wide uppercase ${VARIANTS[variant]}`}>
      {children}
    </span>
  );
}

export function decisionVariant(d: Decision): BadgeProps["variant"] {
  return d === "BUY" ? "buy" : d === "SELL" ? "sell" : "hold";
}

export function riskVariant(r: RiskHealth): BadgeProps["variant"] {
  const map: Record<RiskHealth, BadgeProps["variant"]> = {
    HEALTHY: "healthy", MODERATE: "moderate", HIGH_RISK: "high", CRITICAL: "critical",
  };
  return map[r];
}
