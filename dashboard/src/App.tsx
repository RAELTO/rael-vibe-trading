import { useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useWindowSize } from "./hooks/useWindowSize";
import { Header } from "./components/Header";
import { PortfolioPanel } from "./components/PortfolioPanel";
import { PositionPanel } from "./components/PositionPanel";
import { AgentVotesPanel } from "./components/AgentVotesPanel";
import { DecisionPanel } from "./components/DecisionPanel";
import { NewsPanel } from "./components/NewsPanel";
import { StrategyPanel } from "./components/StrategyPanel";
import { MarketChart } from "./components/MarketChart";
import { PnLChart } from "./components/PnLChart";
import { ShadowPanel } from "./components/ShadowPanel";
import { ErrorLog } from "./components/ErrorLog";
import { HardStopBanner } from "./components/HardStopBanner";
import { MobileTabBar, type MobileTab } from "./components/MobileTabBar";

// ── Ambient background (shared across all layouts) ─────────────────────────
function BgFx() {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden" style={{ zIndex: 0 }}>
      <div className="absolute inset-0 bg-grid" />
      <div className="absolute" style={{
        top: "-20%", left: "-10%", width: "50vw", height: "50vh", borderRadius: "50%",
        background: "radial-gradient(ellipse, rgba(0,212,255,0.07) 0%, transparent 70%)",
      }} />
      <div className="absolute" style={{
        bottom: "-20%", right: "-10%", width: "50vw", height: "50vh", borderRadius: "50%",
        background: "radial-gradient(ellipse, rgba(167,139,250,0.06) 0%, transparent 70%)",
      }} />
    </div>
  );
}

// ── Sidebar (desktop + tablet) ─────────────────────────────────────────────
function Sidebar({ state, width }: { state: ReturnType<typeof useWebSocket>["state"]; width: number }) {
  return (
    <div style={{ width, flexShrink: 0, overflow: "hidden" }}>
      <div style={{ height: "100%", overflowY: "auto" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 0 24px 12px" }}>
          <PortfolioPanel portfolio={state.portfolio} positions={state.open_positions} />
          <PositionPanel position={state.active_position} tradingMode={state.trading_mode} />
          <NewsPanel news={state.last_news} />
        </div>
      </div>
    </div>
  );
}

// ── Scrollable main wrapper: separates flex sizing from scroll ─────────────
// Pattern: outer takes the flex space, inner scrolls. Children in a plain
// block column (not a flex child context), so they never get shrunk.
function ScrollMain({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
      <div style={{ height: "100%", overflowY: "auto" }}>
        <div style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
          padding: "12px 12px 24px 8px",
        }}>
          {children}
        </div>
      </div>
    </div>
  );
}

// ── Desktop main content ───────────────────────────────────────────────────
function DesktopMain({ state, symbol }: { state: ReturnType<typeof useWebSocket>["state"]; symbol: string }) {
  return (
    <ScrollMain>
      {/* Top row: Decision (340px) + Market (1fr) — both stretch to same height */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 340px) minmax(0, 1fr)",
        gap: 10,
        alignItems: "stretch",
      }}>
        <DecisionPanel decision={state.last_decision} tradingMode={state.trading_mode} intervalSeconds={state.config?.analysis_interval_seconds} activePosition={state.active_position} />
        <MarketChart symbol={symbol} leverage={state.active_position?.leverage} cols={4} />
      </div>
      <PnLChart />
      <ShadowPanel />
      <AgentVotesPanel votes={state.agent_votes} tradingMode={state.trading_mode} cols={3} />
      <StrategyPanel review={state.strategy_review} lessons={state.lessons} />
      {state.errors.length > 0 && <ErrorLog errors={state.errors} />}
    </ScrollMain>
  );
}

// ── Tablet main content (single column) ───────────────────────────────────
function TabletMain({ state, symbol }: { state: ReturnType<typeof useWebSocket>["state"]; symbol: string }) {
  return (
    <ScrollMain>
      <DecisionPanel decision={state.last_decision} tradingMode={state.trading_mode} intervalSeconds={state.config?.analysis_interval_seconds} activePosition={state.active_position} />
      <MarketChart symbol={symbol} leverage={state.active_position?.leverage} cols={2} />
      <PnLChart />
      <ShadowPanel />
      <AgentVotesPanel votes={state.agent_votes} tradingMode={state.trading_mode} cols={1} />
      <StrategyPanel review={state.strategy_review} lessons={state.lessons} />
      {state.errors.length > 0 && <ErrorLog errors={state.errors} />}
    </ScrollMain>
  );
}

// ── Mobile tab content ─────────────────────────────────────────────────────
function MobileScrollArea({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ flex: 1, overflow: "hidden" }}>
      <div style={{ height: "100%", overflowY: "auto" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "10px 10px 24px" }}>
          {children}
        </div>
      </div>
    </div>
  );
}

function MobileContent({ tab, state, symbol }: {
  tab: MobileTab;
  state: ReturnType<typeof useWebSocket>["state"];
  symbol: string;
}) {
  if (tab === "overview") return (
    <MobileScrollArea>
      <DecisionPanel decision={state.last_decision} tradingMode={state.trading_mode} intervalSeconds={state.config?.analysis_interval_seconds} activePosition={state.active_position} />
      <MarketChart symbol={symbol} leverage={state.active_position?.leverage} cols={2} />
      <PnLChart />
    </MobileScrollArea>
  );

  if (tab === "position") return (
    <MobileScrollArea>
      <PortfolioPanel portfolio={state.portfolio} positions={state.open_positions} />
      <PositionPanel position={state.active_position} tradingMode={state.trading_mode} />
    </MobileScrollArea>
  );

  if (tab === "intel") return (
    <MobileScrollArea>
      <NewsPanel news={state.last_news} />
    </MobileScrollArea>
  );

  if (tab === "pipeline") return (
    <MobileScrollArea>
      <AgentVotesPanel votes={state.agent_votes} tradingMode={state.trading_mode} cols={1} />
      <ShadowPanel />
      <StrategyPanel review={state.strategy_review} lessons={state.lessons} />
      {state.errors.length > 0 && <ErrorLog errors={state.errors} />}
    </MobileScrollArea>
  );

  return null;
}

// ── Root ───────────────────────────────────────────────────────────────────
export default function App() {
  const { state, connected } = useWebSocket();
  const { bp } = useWindowSize();
  const [mobileTab, setMobileTab] = useState<MobileTab>("overview");

  const symbol = state.last_decision?.symbol ?? "BTCUSDT";
  const isMobile = bp === "mobile";
  const sidebarWidth = bp === "tablet" ? 240 : 290;

  return (
    <div style={{
      height: "100vh",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      background: "#03030a",
      color: "#e8e8f0",
      position: "relative",
    }}>
      <BgFx />

      <div style={{ position: "relative", zIndex: 1, height: "100%", display: "flex", flexDirection: "column" }}>
        {state.hard_stop_message && <HardStopBanner message={state.hard_stop_message} />}

        <Header
          connected={connected}
          status={state.system_status}
          cycle={state.current_cycle}
          riskHealth={state.risk_health}
          tradingMode={state.trading_mode}
        />

        {/* ── Mobile layout ── */}
        {isMobile ? (
          <>
            <MobileContent tab={mobileTab} state={state} symbol={symbol} />
            <MobileTabBar active={mobileTab} onChange={setMobileTab} />
          </>
        ) : (
          /* ── Desktop / Tablet layout ── */
          <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
            <Sidebar state={state} width={sidebarWidth} />
            {bp === "desktop"
              ? <DesktopMain state={state} symbol={symbol} />
              : <TabletMain  state={state} symbol={symbol} />
            }
          </div>
        )}
      </div>
    </div>
  );
}
