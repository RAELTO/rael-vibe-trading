"""
core/orchestrator.py — Vibe Trading Orchestrator
=================================================
Punto de entrada único del sistema.  Arranca:
  1. FastAPI + WebSocket server  (uvicorn, modo asyncio)
  2. WebSearchAgent loop         (cada NEWS_INTERVAL_SECONDS, default 1800)
  3. Trading loop principal      (cada ANALYSIS_INTERVAL_SECONDS, default 1200)

Uso:
    python core/orchestrator.py
"""

import asyncio
import contextlib
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import uvicorn
from dotenv import load_dotenv

# ─── path setup ───────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

load_dotenv(os.path.join(ROOT, ".env"))

# ─── imports internos ─────────────────────────────────────────────────────────
from agents.claude_agent    import ClaudeAgent
from agents.qwen_agent      import QwenAPIAgent
from agents.deepseek_agent  import DeepSeekAgent
from agents.local_agent     import LocalAgent
from agents.web_search_agent import WebSearchAgent
from agents.base_agent      import TradingSignal, AgentVote

# Pipeline agents (Plan A / Plan B)
from agents.technical_agent import TechnicalAgent
from agents.sentiment_agent import SentimentAgent
from agents.quant_agent     import QuantAgent
from agents.synthesis_agent import SynthesisAgent
from agents.gate_agent      import GateAgent
from agents.deepseek_decision_agent import DeepSeekDecisionAgent
from agents.claude_audit_agent import ClaudeAuditAgent

from core.decider       import Decider
from core.risk_manager  import RiskManager, OrderRequest
from core.state_store   import StateStore
from core.epoch_manager import EpochManager

from execution.binance_testnet import BinanceTestnetClient
from execution.binance_futures import BinanceFuturesClient

# FastAPI app_state y helpers de broadcast
from api.main import (
    app as fastapi_app,
    app_state,
    broadcast_cycle_start,
    broadcast_agent_vote,
    broadcast_decision,
    broadcast_order,
    broadcast_portfolio,
    broadcast_news,
    broadcast_error,
    broadcast_position_update,
    broadcast_mode_change,
    broadcast_hard_stop,
)

# ─── constantes ───────────────────────────────────────────────────────────────
ANALYSIS_INTERVAL  = int(os.getenv("ANALYSIS_INTERVAL_SECONDS", "1200"))
AGENT_TIMEOUT      = int(os.getenv("AGENT_TIMEOUT_SECONDS", "60"))
API_HOST           = os.getenv("API_HOST", "0.0.0.0")
API_PORT           = int(os.getenv("API_PORT", "8000"))
POSITION_MONITOR   = int(os.getenv("POSITION_MONITOR_INTERVAL", "180"))   # 3 min
FUTURES_LEVERAGE   = int(os.getenv("FUTURES_LEVERAGE", "3"))

# Decision mode: DEEPSEEK_SINGLE (low-cost) | MULTI_AGENT (3-phase pipeline) | ENSEMBLE (old weighted vote)
DECISION_MODE      = os.getenv("DECISION_MODE", "DEEPSEEK_SINGLE").upper()
# Pipeline mode kept for backward compatibility.
PIPELINE_MODE      = os.getenv("PIPELINE_MODE", "MULTI_AGENT")
MIN_CONVICTION     = float(os.getenv("MIN_CONVICTION", "0.60"))
PHASE1_TIMEOUT     = int(os.getenv("PHASE1_TIMEOUT_SECONDS", "30"))
SYNTHESIS_TIMEOUT  = int(os.getenv("SYNTHESIS_TIMEOUT_SECONDS", "60"))
GATE_TIMEOUT       = int(os.getenv("GATE_TIMEOUT_SECONDS", "15"))
DECISION_TIMEOUT   = int(os.getenv("DEEPSEEK_DECISION_TIMEOUT_SECONDS", "45"))
CLAUDE_AUDIT_ENABLED = os.getenv("CLAUDE_AUDIT_ENABLED", "true").lower() == "true"
CLAUDE_AUDIT_MIN_CONF = float(os.getenv("CLAUDE_AUDIT_MIN_CONF", "0.58"))
CLAUDE_AUDIT_MAX_CONF = float(os.getenv("CLAUDE_AUDIT_MAX_CONF", "0.66"))

# Horario de trading — limita SOLO el loop de decisiones (el monitor de posiciones sigue 24/7).
# Ventana [START, END) en la zona TRADING_TIMEZONE. Si START > END, la ventana cruza medianoche.
TRADING_HOURS_ENABLED = os.getenv("TRADING_HOURS_ENABLED", "false").lower() == "true"
TRADING_HOURS_START   = int(os.getenv("TRADING_HOURS_START", "8"))
TRADING_HOURS_END     = int(os.getenv("TRADING_HOURS_END", "20"))
TRADING_TIMEZONE      = os.getenv("TRADING_TIMEZONE", "UTC")
OFF_HOURS_RECHECK     = 300   # re-chequear cada 5 min cuando estamos fuera de horario

# Trailing stop — solo activo en modo FUTURES
TRAIL_ACTIVATION_PCT = 0.008   # precio debe moverse +0.8% a favor antes de activar
TRAIL_DISTANCE_PCT   = 0.012   # SL se mantiene 1.2% del precio actual (< 1.5% inicial)
TRAIL_MIN_STEP_PCT   = 0.003   # mínimo movimiento para justificar cancelar/reemplazar la orden

TRADING_UNIVERSE = ["BTCUSDT"]

TRADING_BUDGET    = float(os.getenv("TRADING_BUDGET_USDT", "1000.0"))  # referencia de capital inicial
MAX_TRADING_LOSS  = float(os.getenv("MAX_TRADING_LOSS_USDT", "600.0")) # pérdida máxima acumulada antes de hard stop
MIN_POSITION_USDT = float(os.getenv("MIN_POSITION_USDT", "500.0"))     # posición mínima en futuros
MAX_POSITION_USDT = float(os.getenv("MAX_POSITION_USDT", "1000.0"))    # posición máxima en futuros

DEMO_INITIAL_BALANCE = 5000.0  # Balance que da Binance testnet tras un reset
DEMO_RESET_MIN_JUMP  = 300.0   # Salto mínimo de balance para detectar un reset


# ─── helpers ──────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _log(msg: str, level: str = "INFO"):
    tag = {"INFO": "\033[36m[INFO]\033[0m", "WARN": "\033[33m[WARN]\033[0m",
           "ERR": "\033[31m[ERR ]\033[0m", "OK": "\033[32m[ OK ]\033[0m"}.get(level, "[    ]")
    print(f"{tag} {_ts()} {msg}")


def _silence_connection_reset(loop, context):
    """
    Exception handler del event loop.

    En Windows (ProactorEventLoop), cuando un cliente WebSocket del dashboard
    cierra la conexión de golpe (recarga de página, HMR de Vite), asyncio lanza
    ConnectionResetError [WinError 10054] desde
    _ProactorBasePipeTransport._call_connection_lost al hacer socket.shutdown().
    Es ruido cosmético inofensivo — lo silenciamos y delegamos el resto.
    """
    exc = context.get("exception")
    if isinstance(exc, ConnectionResetError):
        return
    loop.default_exception_handler(context)


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class TradingOrchestrator:

    # Agentes de API de pago — candidatos a reconexión automática
    RECONNECTABLE_IDS = {"claude-sonnet", "qwen-api", "deepseek-v3", "gpt-5.4-nano",
                         "technical", "sentiment", "synthesis", "gate"}
    RECONNECT_MAX_ATTEMPTS = 3
    RECONNECT_INTERVAL     = 60   # segundos entre intentos

    def __init__(self):
        self.voting_agents: list = []
        self.local_agent   = LocalAgent()
        self.news_agent    = WebSearchAgent()
        self.decider       = Decider()
        self.risk          = RiskManager()
        self.spot          = BinanceTestnetClient()
        self.futures       = BinanceFuturesClient()
        self.store         = StateStore()
        self.epoch         = None

        # Pipeline agents (initialized in startup() if PIPELINE_MODE == "MULTI_AGENT")
        self._tech_agent:  TechnicalAgent  | None = None
        self._sent_agent:  SentimentAgent  | None = None
        self._quant_agent: QuantAgent      | None = None
        self._synth_agent: SynthesisAgent  | None = None
        self._gate_agent:  GateAgent       | None = None
        self._pipeline_ready = False
        self._decision_agent: DeepSeekDecisionAgent | None = None
        self._audit_agent: ClaudeAuditAgent | None = None
        self._single_decision_ready = False

        # Modo de trading — FUTURES por defecto, SPOT como secundario
        self.trading_mode: str = os.getenv("TRADING_MODE", "FUTURES").upper()

        self._cycle           = 0
        self._decision_log: list[dict] = []
        self._active_trade_id: int | None = None   # trade futures abierto
        self._sl_order_id:    int | None = None    # ID de la orden SL activa en Binance
        self._hard_stop       = False              # True cuando se alcanza el límite de pérdida

        # Detección de reset de balance Binance testnet
        self._prev_binance_balance: float | None = None

        # Cola de reconexión: {agent: intentos_realizados}
        self._reconnect_queue: dict = {}

    @property
    def _client(self):
        """Retorna el cliente activo según el modo de trading."""
        return self.futures if self.trading_mode == "FUTURES" else self.spot

    # ── Startup ───────────────────────────────────────────────────────────────

    async def startup(self):
        """Health-check de todos los agentes; excluye los que fallen."""
        _log(f"DECISION_MODE={DECISION_MODE}", "INFO")

        if DECISION_MODE == "DEEPSEEK_SINGLE":
            self._decision_agent = DeepSeekDecisionAgent()
            ok = await self._check_agent(self._decision_agent)
            if ok is True:
                self._single_decision_ready = True
                _log(f"  decision/{self._decision_agent.model} -> OK", "OK")
            else:
                _log(f"  decision/deepseek -> FAIL ({ok})", "ERR")
            if CLAUDE_AUDIT_ENABLED:
                self._audit_agent = ClaudeAuditAgent()
                _log(f"  auditor/{self._audit_agent.model} -> lazy", "INFO")
            candidates = []
        elif DECISION_MODE == "ENSEMBLE":
            candidates = [
                ClaudeAgent(),
                QwenAPIAgent(),
                DeepSeekAgent(),
                self.local_agent,
            ]
        else:
            candidates = []
        if candidates:
            _log("Verificando agentes ensemble...", "INFO")
            results = await asyncio.gather(
                *[self._check_agent(a) for a in candidates],
                return_exceptions=True,
            )

            for agent, ok in zip(candidates, results):
                if ok is True:
                    self.voting_agents.append(agent)
                    _log(f"  {agent.agent_id} -> OK", "OK")
                else:
                    _log(f"  {agent.agent_id} -> FAIL ({ok})", "WARN")

            _log(f"{len(self.voting_agents)} agentes listos para votar.", "OK")
        else:
            _log("Ensemble legacy desactivado para este modo.", "INFO")

        # Pipeline agents health check
        if DECISION_MODE == "MULTI_AGENT":
            _log(f"PIPELINE_MODE=MULTI_AGENT — iniciando agentes de pipeline...", "INFO")
            pipeline_candidates = [
                ("technical",  TechnicalAgent()),
                ("sentiment",  SentimentAgent()),
                ("quant",      QuantAgent()),
                ("synthesis",  SynthesisAgent()),
                ("gate",       GateAgent()),
            ]
            pipeline_results = await asyncio.gather(
                *[self._check_agent(a) for _, a in pipeline_candidates],
                return_exceptions=True,
            )
            attrs = ["_tech_agent", "_sent_agent", "_quant_agent", "_synth_agent", "_gate_agent"]
            pipeline_ok = True
            for (name, agent), ok, attr in zip(pipeline_candidates, pipeline_results, attrs):
                if ok is True:
                    setattr(self, attr, agent)
                    _log(f"  pipeline/{name} ({agent.model}) -> OK", "OK")
                else:
                    _log(f"  pipeline/{name} -> FAIL ({ok})", "WARN")
                    pipeline_ok = False
            # Require at minimum technical + synthesis (gate is optional, sentiment is optional)
            self._pipeline_ready = (self._tech_agent is not None and self._synth_agent is not None)
            if self._pipeline_ready:
                _log("Pipeline MULTI_AGENT listo.", "OK")
            else:
                _log("Pipeline MULTI_AGENT incompleto — falta technical o synthesis. Fallback a ENSEMBLE.", "WARN")

        # Sincronizar balance inicial según el modo activo
        app_state["trading_mode"] = self.trading_mode
        # Publicar config runtime para que el frontend no hardcodee el intervalo/horario
        app_state["config"] = {
            "analysis_interval_seconds": ANALYSIS_INTERVAL,
            "trading_hours_enabled":     TRADING_HOURS_ENABLED,
            "trading_hours_start":       TRADING_HOURS_START,
            "trading_hours_end":         TRADING_HOURS_END,
            "trading_timezone":          TRADING_TIMEZONE,
        }
        _log(f"Modo de trading: {self.trading_mode}", "OK")
        try:
            if self.trading_mode == "FUTURES":
                balance = self.futures.get_futures_balance()
            else:
                balance = self.spot.get_portfolio_value()
            effective = self._effective_budget()
            self.risk.update_balance(min(balance, effective))
            app_state["portfolio"]["balance"] = balance
            _log(f"Balance inicial ({self.trading_mode}): ${balance:,.2f} USDT (operativo: ${effective:,.2f})", "OK")
        except Exception as e:
            _log(f"Error obteniendo balance: {e}", "WARN")
            balance = TRADING_BUDGET

        # Inicializar EpochManager con el budget efectivo actual
        initial = self._effective_budget()
        self.epoch = EpochManager(initial_balance=initial)

        # Restaurar estado del día de hoy si existe
        restored = self.store.restore_risk_state(self.risk)
        if restored:
            _log(
                f"Estado restaurado: daily_loss=${self.risk.state.daily_loss:.2f} "
                f"open_positions={self.risk.state.open_positions}",
                "OK",
            )
        else:
            _log("Sin estado previo hoy — iniciando fresco.", "INFO")

        # Reconciliar trades OPEN en DB con posiciones reales en Binance
        # (detecta cierres offline: SL/TP disparado, liquidación, cierre manual)
        if self.trading_mode == "FUTURES":
            await self._reconcile_open_trades()
        else:
            # SPOT: restauración simple sin reconciliación
            try:
                open_trades = self.store.get_open_trades()
                if open_trades:
                    t = open_trades[0]
                    self._active_trade_id = t["id"]
                    self._sl_order_id     = t.get("sl_order_id")
                    _log(
                        f"Trade abierto restaurado: #{t['id']} {t['side']} {t['symbol']} "
                        f"@ ${t['entry_price']:,.2f}",
                        "WARN",
                    )
            except Exception as e:
                _log(f"Error restaurando trade abierto: {e}", "WARN")

    async def _check_agent(self, agent) -> bool:
        try:
            return await asyncio.wait_for(agent.health_check(), timeout=30)
        except Exception as e:
            return e

    def _resolve_close_from_binance(self, trade: dict) -> tuple[float, str]:
        """
        Determina el precio y la razón de cierre REALES de un trade cuya posición ya no
        existe en Binance, consultando el historial (REALIZED_PNL + fills de cierre).

        Devuelve (exit_price, exit_reason). Si Binance no responde, hace fallback
        conservador a (entry_price, "OFFLINE_CLOSE"). Compartido por la reconciliación
        de arranque y por el monitor de posiciones, para que un cierre por TP/SL nunca
        se registre erróneamente como LIQUIDATED con PnL 0.
        """
        symbol = trade["symbol"]
        exit_price  = trade["entry_price"]   # fallback conservador
        exit_reason = "OFFLINE_CLOSE"
        try:
            ts_open = trade.get("ts_open", "")
            start_ms = (
                int(datetime.fromisoformat(ts_open).timestamp() * 1000)
                if ts_open else None
            )

            # a) PnL realizado desde Binance income history
            income_records = self.futures.client.futures_income_history(
                symbol=symbol,
                incomeType="REALIZED_PNL",
                startTime=start_ms,
                limit=20,
            )
            realized_pnl = (
                sum(float(r["income"]) for r in income_records)
                if income_records else None
            )

            # b) Fills de cierre para obtener el precio de salida real
            fills = self.futures.client.futures_account_trades(
                symbol=symbol,
                startTime=start_ms,
                limit=50,
            )
            entry_side  = trade["side"]
            close_side  = "SELL" if entry_side in ("BUY", "LONG") else "BUY"
            close_fills = [f for f in (fills or []) if f["side"] == close_side]
            if close_fills:
                exit_price = float(close_fills[-1]["price"])

            # c) Inferir exit_reason a partir del PnL real y la cercanía al SL
            sl = trade.get("sl_price")
            tp = trade.get("tp_price")
            if realized_pnl is not None:
                if realized_pnl > 0:
                    exit_reason = "TP"
                elif tp and sl and abs(exit_price - sl) <= abs(sl * 0.002):
                    exit_reason = "SL"
                elif realized_pnl < -(trade["entry_price"] * trade["quantity"] * 0.05):
                    exit_reason = "LIQUIDATED"
                else:
                    exit_reason = "SL"
        except Exception as e:
            _log(f"[Reconcile] Error buscando cierre en Binance: {e} — usando entry_price", "WARN")

        return exit_price, exit_reason

    async def _reconcile_open_trades(self):
        """
        Verifica al arrancar que cada trade OPEN en la DB tenga posición real en Binance.

        Si la posición ya no existe (SL/TP disparado, liquidación o cierre manual mientras
        el orquestador estaba apagado), busca el precio y PnL de cierre en el historial de
        Binance y cierra el trade en DB para mantener coherencia.
        """
        open_trades = self.store.get_open_trades()
        if not open_trades:
            return

        for trade in open_trades:
            symbol = trade["symbol"]

            # ── 1. Verificar si la posición sigue abierta en Binance ─────────────
            try:
                pos = self.futures.get_position(symbol)
            except Exception as e:
                _log(f"[Reconcile] Error consultando {symbol}: {e}", "WARN")
                pos = None

            if pos:
                # Posición sigue activa — restaurar estado en memoria
                self._active_trade_id = trade["id"]
                self._sl_order_id     = trade.get("sl_order_id")
                _log(
                    f"[Reconcile] Trade #{trade['id']} activo en Binance — "
                    f"{pos['side']} {symbol} @ ${trade['entry_price']:,.2f} "
                    f"| SL order={self._sl_order_id}",
                    "OK",
                )
                continue

            # ── 2. Posición cerrada offline — buscar datos de cierre ──────────────
            _log(
                f"[Reconcile] Trade #{trade['id']} cerrado offline ({symbol}) — "
                f"consultando historial Binance...",
                "WARN",
            )

            exit_price, exit_reason = self._resolve_close_from_binance(trade)

            # ── 3. Cancelar órdenes residuales ────────────────────────────────────
            try:
                self.futures.cancel_all_orders(symbol)
            except Exception:
                pass

            # ── 4. Cerrar en DB ───────────────────────────────────────────────────
            pnl = self.store.close_trade(
                trade_id=trade["id"],
                cycle=self._cycle,
                exit_price=exit_price,
                exit_reason=exit_reason,
            )
            self.risk.state.open_positions = max(0, self.risk.state.open_positions - 1)

            _log(
                f"[Reconcile] Trade #{trade['id']} cerrado en DB: "
                f"{exit_reason} @ ${exit_price:,.2f} | PnL={pnl:+.4f} USDT",
                "OK",
            )

            try:
                self.store.log_system_event(
                    "OFFLINE_CLOSE",
                    self.trading_mode,
                    self._compute_effective_balance(),
                    {
                        "trade_id":   trade["id"],
                        "symbol":     symbol,
                        "exit_reason": exit_reason,
                        "exit_price": exit_price,
                        "pnl":        pnl,
                    },
                )
            except Exception:
                pass

    # ── News loop ─────────────────────────────────────────────────────────────

    async def run_news_loop(self):
        """Corre WebSearchAgent de forma independiente."""
        _log("WebSearchAgent loop iniciado.", "INFO")
        while True:
            try:
                await self.news_agent.run_cycle()
                ctx = self.news_agent.get_latest_context()
                if ctx and ctx.get("overall_sentiment") is not None:
                    await broadcast_news({
                        "sentiment": ctx.get("overall_sentiment", 0.0),
                        "impact":    ctx.get("market_impact", "LOW"),
                        "summary":   ctx.get("crypto_summary", ""),
                        "assets":    ctx.get("asset_scores", {}),
                        "key_events": ctx.get("key_events", []),
                        "avoid_trading": ctx.get("avoid_trading", False),
                        "avoid_reason":  ctx.get("avoid_reason", ""),
                    })
            except Exception as e:
                _log(f"WebSearchAgent error: {e}", "ERR")

            await asyncio.sleep(self.news_agent.interval_seconds)

    # ── Trading loop ──────────────────────────────────────────────────────────

    def _within_trading_hours(self) -> bool:
        """
        True si la hora actual cae dentro de la ventana [START, END) en TRADING_TIMEZONE.
        Solo aplica al loop de decisiones; el monitor de posiciones corre 24/7.
        Si la zona horaria es inválida, hace fallback a UTC (no bloquea por error de config).
        """
        if not TRADING_HOURS_ENABLED:
            return True
        if TRADING_TIMEZONE.upper() == "UTC":
            tz = timezone.utc   # no depende de tzdata
        else:
            try:
                tz = ZoneInfo(TRADING_TIMEZONE)
            except (ZoneInfoNotFoundError, ValueError):
                _log(f"TRADING_TIMEZONE inválida '{TRADING_TIMEZONE}' (¿falta tzdata?), usando UTC.", "WARN")
                tz = timezone.utc
        hour = datetime.now(tz).hour
        if TRADING_HOURS_START == TRADING_HOURS_END:
            return True   # ventana de 24h
        if TRADING_HOURS_START < TRADING_HOURS_END:
            return TRADING_HOURS_START <= hour < TRADING_HOURS_END
        # Ventana que cruza medianoche (p.ej. 20→6)
        return hour >= TRADING_HOURS_START or hour < TRADING_HOURS_END

    async def run_trading_loop(self):
        """Loop principal de trading — un ciclo cada ANALYSIS_INTERVAL segundos."""
        _log(f"Trading loop iniciado. Intervalo: {ANALYSIS_INTERVAL}s ({ANALYSIS_INTERVAL//60} min)", "INFO")
        if TRADING_HOURS_ENABLED:
            _log(
                f"Horario de trading activo: {TRADING_HOURS_START:02d}:00–{TRADING_HOURS_END:02d}:00 "
                f"{TRADING_TIMEZONE} (el monitor de posiciones sigue 24/7).",
                "INFO",
            )

        self._was_off_hours = False

        while True:
            # Hard stop — no continuar si se alcanzó el límite de pérdida
            if self._hard_stop:
                _log("Sistema en HARD STOP. Trading suspendido. Reinicia assets para continuar.", "ERR")
                await asyncio.sleep(ANALYSIS_INTERVAL)
                continue

            # Horario de trading — fuera de la ventana, pausar SOLO las decisiones nuevas.
            # Una posición abierta sigue gestionada por run_position_monitor_loop (SL/TP/trailing).
            if not self._within_trading_hours():
                _log(
                    f"Fuera de horario de trading ({TRADING_HOURS_START:02d}:00–"
                    f"{TRADING_HOURS_END:02d}:00 {TRADING_TIMEZONE}) — decisor en pausa.",
                    "INFO",
                )
                self._was_off_hours = True
                # Mantener vivo el dashboard (precio, indicadores, balance) sin gastar LLM
                await self._refresh_idle_dashboard()
                await asyncio.sleep(min(ANALYSIS_INTERVAL, OFF_HOURS_RECHECK))
                continue

            # Reanudación tras una pausa: reconciliar contra Binance antes de decidir.
            # Salvaguarda por si el monitor no alcanzó a registrar un cierre durante la pausa.
            if self._was_off_hours:
                self._was_off_hours = False
                _log("Reanudando tras pausa — reconciliando estado con Binance...", "INFO")
                try:
                    if self.trading_mode == "FUTURES":
                        await self._reconcile_open_trades()
                except Exception as e:
                    _log(f"Error en reconciliación de reanudación: {e}", "WARN")

            try:
                await self._run_cycle()
            except Exception as e:
                err = f"Cycle error: {e}"
                _log(err, "ERR")
                traceback.print_exc()
                await broadcast_error(err)

            _log(f"Esperando {ANALYSIS_INTERVAL}s hasta próximo ciclo...", "INFO")
            await asyncio.sleep(ANALYSIS_INTERVAL)

    async def _run_cycle(self):
        self._cycle += 1
        _log(f"\n{'='*55}", "INFO")
        _log(f"CICLO #{self._cycle} — {datetime.now(timezone.utc).isoformat()}", "INFO")
        _log(f"{'='*55}", "INFO")

        # Elegir top N pares a analizar
        symbols = self._pick_symbols()
        _log(f"Candidatos: {symbols}", "INFO")

        await broadcast_cycle_start(self._cycle, symbols)

        # Detectar trades cerrados (SL/TP ejecutados) desde el ciclo anterior
        await self._check_closed_trades()

        # Construir contexto una sola vez
        try:
            if self.trading_mode == "FUTURES":
                balance = self.futures.get_futures_balance()
            else:
                balance = self.spot.get_portfolio_value()
            self.risk.update_balance(min(balance, self._effective_budget()))
        except Exception:
            balance = self.risk.state.portfolio_balance

        # Verificar hard stop: pérdida acumulada sobre trades cerrados supera el límite
        total_pnl = self.store.get_total_pnl()
        if total_pnl <= -MAX_TRADING_LOSS:
            await self._trigger_hard_stop(balance)
            return

        news_ctx = self.news_agent.get_latest_context()
        context  = self._build_context(balance, news_ctx)

        # Obtener market_data según el modo activo
        market_data_map: dict[str, dict] = {}
        for sym in symbols:
            try:
                md = self._client.get_market_data(sym)
                market_data_map[sym] = md
                app_state.setdefault("market_data", {})[sym] = md
                futures_extra = ""
                if self.trading_mode == "FUTURES":
                    futures_extra = (
                        f" | Funding={md.get('funding_rate', 0):+.4f}% "
                        f"OI={md.get('open_interest', 0):,.0f} "
                        f"L/S={md.get('long_short_ratio', 1):.2f}"
                    )
                _log(
                    f"  {sym}: ${md['price']:,.2f} | RSI={md['rsi']} | MACD={md['macd']}{futures_extra}",
                    "INFO",
                )
            except Exception as e:
                _log(f"  {sym}: error obteniendo datos — {e}", "WARN")

        if not market_data_map:
            _log("Sin datos de mercado disponibles, saltando ciclo.", "WARN")
            return

        symbol      = TRADING_UNIVERSE[0]
        market_data = market_data_map[symbol]

        # Enriquecer posición activa con precio actual y P&L flotante
        if "active_position" in context:
            pos   = context["active_position"]
            entry = pos["entry_price"]
            mark  = market_data["price"]
            qty   = pos["quantity"]
            lev   = pos.get("leverage", 1)
            sign  = 1 if pos["side"] in ("BUY", "LONG") else -1
            pos["mark_price"]     = round(mark, 2)
            pos["unrealized_pnl"] = round((mark - entry) * qty * sign, 4)
            pos["pnl_pct"]        = round(sign * (mark - entry) / entry * 100 * lev, 2)
            if pos.get("sl_price"):
                pos["distance_to_sl_pct"] = round(abs(mark - pos["sl_price"]) / mark * 100, 2)
            if pos.get("tp_price"):
                pos["distance_to_tp_pct"] = round(abs(pos["tp_price"] - mark) / mark * 100, 2)

        # ── Dispatch to pipeline or ensemble ──────────────────────────────────
        if DECISION_MODE == "DEEPSEEK_SINGLE" and self._single_decision_ready:
            # Con posiciÃ³n activa: skip decisor, solo monitorear via position loop
            if self._active_trade_id is not None:
                _log(
                    f"PosiciÃ³n activa #{self._active_trade_id} â€” decisor en pausa hasta TP/SL.",
                    "INFO",
                )
                await self._update_portfolio(balance)
                return
            await self._run_single_decision_cycle(symbol, market_data, context, balance, news_ctx)
            return

        if DECISION_MODE == "MULTI_AGENT" and self._pipeline_ready:
            # Con posición activa: skip agentes, solo monitorear via position loop
            if self._active_trade_id is not None:
                _log(
                    f"Posición activa #{self._active_trade_id} — agentes en pausa hasta TP/SL.",
                    "INFO",
                )
                await self._update_portfolio(balance)
                return
            await self._run_pipeline_cycle(symbol, market_data, context, balance, news_ctx)
            return

        # ── ENSEMBLE (legacy weighted-vote path) ──────────────────────────────
        signals = await self._collect_votes(market_data, context)
        if not signals:
            _log("Sin votos válidos este ciclo, saltando.", "WARN")
            return

        result = self.decider.decide(signals, news_ctx)

        # Tomar decisión final
        decision   = result["decision"]
        score      = result["consensus_score"]
        reasoning  = " | ".join(result["reasoning"][:3])

        _log(
            f"DECISION: {decision} | Score: {score:.3f} | "
            f"Consensus: {result['reached_consensus']}",
            "OK" if decision != "HOLD" else "INFO",
        )

        await broadcast_decision(symbol, decision, score, reasoning)

        # Persistir decisión y estado de riesgo
        result["symbol"] = symbol
        self.store.save_decision(self._cycle, result)
        self.store.save_risk_state(
            self.risk.state.daily_loss,
            self.risk.state.open_positions,
            balance,
        )

        # Guardar en historial de contexto en memoria
        self._decision_log.insert(0, {
            "symbol": symbol, "decision": decision,
            "score": score, "ts": datetime.now(timezone.utc).isoformat(),
        })
        self._decision_log = self._decision_log[:10]

        # Actualizar portfolio en dashboard
        await self._update_portfolio(balance)

        # EpochManager: verificar drawdown al final del ciclo
        if self.epoch:
            epoch_result = self.epoch.tick(balance, self._cycle, self.store)
            if epoch_result.get("paused"):
                _log("Sistema pausado por EpochManager — demasiados resets consecutivos.", "ERR")
                await broadcast_error("SYSTEM PAUSED: consecutive drawdown resets exceeded limit.")
                return
            if epoch_result.get("reset"):
                self.risk.state.daily_loss     = 0.0
                self.risk.state.open_positions = 0
                _log(f"Nueva época iniciada. Conservative mode: {epoch_result.get('conservative')}", "WARN")

        # Ejecutar si corresponde
        if decision in ("BUY", "SELL") and result["reached_consensus"]:
            if news_ctx.get("avoid_trading") and score < 0.80:
                _log(f"AVOID TRADING activo: {news_ctx.get('avoid_reason')}", "WARN")
                return

            await self._execute_order(symbol, decision, score, market_data, balance, signals)

    # ── Multi-Agent Pipeline (Plan A / B) ────────────────────────────────────

    async def _run_single_decision_cycle(
        self,
        symbol: str,
        market_data: dict,
        context: dict,
        balance: float,
        news_ctx: dict,
    ):
        """Low-cost mode: one DeepSeek V4 Pro decision + optional Claude audit + local RiskManager."""
        _log("DEEPSEEK_SINGLE - análisis decisor único...", "INFO")
        try:
            signal = await asyncio.wait_for(
                self._decision_agent.analyze(market_data, context),
                timeout=DECISION_TIMEOUT,
            )
        except Exception as e:
            _log(f"DeepSeek decision FAILED: {e}", "ERR")
            await broadcast_error(f"DeepSeek decision failed: {e}")
            return

        vote = signal.vote.value
        conviction = float(signal.confidence)
        reasoning = signal.reasoning

        _log(
            f"DEEPSEEK DECISION: {vote} | conviction={conviction:.3f}",
            "OK" if vote != "HOLD" else "INFO",
        )
        vote_indicators = {
            "rsi":   market_data.get("rsi"),
            "macd":  market_data.get("macd"),
            "ema20": market_data.get("ema20"),
            "ema50": market_data.get("ema50"),
            "price": market_data.get("price"),
        }
        await broadcast_agent_vote(signal.agent_id, vote, conviction, reasoning, indicators=vote_indicators)
        await broadcast_decision(symbol, vote, conviction, reasoning)

        decision_result = {
            "decision": vote,
            "consensus_score": conviction,
            "conviction": conviction,
            "dominant_dimension": "deepseek_single",
            "confluences": [],
            "conflicts": "",
            "reached_consensus": conviction >= MIN_CONVICTION and vote in ("BUY", "SELL"),
            "agents_voted": [signal.agent_id],
            "reasoning": [reasoning],
            "symbol": symbol,
        }
        self.store.save_decision(self._cycle, decision_result)
        self.store.save_risk_state(
            self.risk.state.daily_loss,
            self.risk.state.open_positions,
            balance,
        )
        self._decision_log.insert(0, {
            "symbol": symbol, "decision": vote,
            "score": conviction, "ts": datetime.now(timezone.utc).isoformat(),
        })
        self._decision_log = self._decision_log[:10]

        await self._update_portfolio(balance)

        if self.epoch:
            epoch_result = self.epoch.tick(balance, self._cycle, self.store)
            if epoch_result.get("paused"):
                _log("Sistema pausado por EpochManager.", "ERR")
                await broadcast_error("SYSTEM PAUSED: consecutive drawdown resets exceeded limit.")
                return
            if epoch_result.get("reset"):
                self.risk.state.daily_loss = 0.0
                self.risk.state.open_positions = 0
                _log(f"Nueva época. Conservative: {epoch_result.get('conservative')}", "WARN")

        if vote not in ("BUY", "SELL") or conviction < MIN_CONVICTION:
            return

        if news_ctx.get("avoid_trading") and conviction < 0.80:
            _log(f"AVOID TRADING activo: {news_ctx.get('avoid_reason')}", "WARN")
            return

        if (
            self._audit_agent
            and CLAUDE_AUDIT_ENABLED
            and CLAUDE_AUDIT_MIN_CONF <= conviction <= CLAUDE_AUDIT_MAX_CONF
        ):
            _log("CLAUDE AUDIT - señal borderline, revisando antes de ejecutar...", "INFO")
            try:
                audit = await asyncio.wait_for(
                    self._audit_agent.audit_decision(signal, market_data, context),
                    timeout=SYNTHESIS_TIMEOUT,
                )
                approved = bool(audit.get("approved", False))
                reason = audit.get("reason", "")
                await broadcast_agent_vote(
                    agent_id=f"{self._audit_agent.agent_id}({self._audit_agent.model})",
                    vote=vote if approved else "HOLD",
                    confidence=conviction if approved else 0.2,
                    reasoning=reason,
                )
                self.store.save_gate_result(self._cycle, symbol, approved, f"Claude audit: {reason}")
                if not approved:
                    _log(f"Claude audit BLOQUEO: {reason}", "WARN")
                    await broadcast_error(f"Claude audit rejected: {reason}")
                    return
            except Exception as e:
                _log(f"Claude audit failed; bloqueando por conservador: {e}", "WARN")
                await broadcast_error(f"Claude audit failed: {e}")
                return

        await self._execute_order(symbol, vote, conviction, market_data, balance, [signal])

    async def _run_pipeline_cycle(
        self,
        symbol: str,
        market_data: dict,
        context: dict,
        balance: float,
        news_ctx: dict,
    ):
        """3-phase pipeline: Phase1 specialists → Phase2 synthesis → Phase3 gate."""

        # ── PHASE 1 — parallel specialist analysis ────────────────────────────
        _log("PIPELINE Phase 1 — análisis especialistas en paralelo...", "INFO")

        phase1_map: list[tuple[str, object]] = []
        if self._tech_agent:
            phase1_map.append(("technical", self._tech_agent.analyze(market_data, context)))
        if self._sent_agent:
            phase1_map.append(("sentiment", self._sent_agent.analyze(market_data, context)))
        if self._quant_agent:
            phase1_map.append(("quant", self._quant_agent.analyze(market_data, context)))

        raw_p1 = await asyncio.gather(
            *[asyncio.wait_for(coro, timeout=PHASE1_TIMEOUT) for _, coro in phase1_map],
            return_exceptions=True,
        )

        analyses: list[dict] = []
        direction_map = {"BULLISH": "BUY", "BEARISH": "SELL", "NEUTRAL": "HOLD"}

        for (name, _), result in zip(phase1_map, raw_p1):
            if isinstance(result, Exception):
                _log(f"  Phase1 [{name}] ERROR: {result}", "WARN")
                await broadcast_error(f"Pipeline Phase1 [{name}]: {result}")
                continue
            analyses.append(result)
            await broadcast_agent_vote(
                agent_id=result.get("agent_id", name),
                vote=direction_map.get(result.get("direction", "NEUTRAL"), "HOLD"),
                confidence=result.get("confidence", 0.0),
                reasoning=result.get("analysis", ""),
            )
            _log(
                f"  [{result.get('agent_id', name)}] {result.get('direction')} "
                f"conf={result.get('confidence', 0):.2f} quality={result.get('signal_quality', '')}",
                "INFO",
            )

        if not analyses:
            _log("Phase 1: ningún especialista respondió, saltando ciclo.", "WARN")
            return

        # Persist Phase 1 analyses
        self.store.save_phase1_analyses(self._cycle, symbol, analyses)

        # ── PHASE 2 — Claude synthesis ────────────────────────────────────────
        _log("PIPELINE Phase 2 — síntesis Claude...", "INFO")
        try:
            synthesis = await asyncio.wait_for(
                self._synth_agent.synthesize(analyses, market_data, context),
                timeout=SYNTHESIS_TIMEOUT,
            )
        except Exception as e:
            _log(f"Phase 2 synthesis FAILED: {e}", "ERR")
            await broadcast_error(f"Pipeline Phase2 synthesis: {e}")
            return

        vote       = synthesis.get("vote", "HOLD")
        conviction = float(synthesis.get("conviction", 0.0))
        reasoning  = synthesis.get("reasoning", "")

        _log(
            f"SYNTHESIS: {vote} | conviction={conviction:.3f} | "
            f"dominant={synthesis.get('dominant_dimension')}",
            "OK" if vote != "HOLD" else "INFO",
        )

        # Broadcast synthesis as agent_vote (shows in AgentVotesPanel) + decision
        await broadcast_agent_vote(
            agent_id=synthesis.get("agent_id", "synthesis"),
            vote=vote,
            confidence=conviction,
            reasoning=reasoning,
        )
        await broadcast_decision(symbol, vote, conviction, reasoning)

        # Persist decision (pipeline format)
        decision_result = {
            "decision":          vote,
            "consensus_score":   conviction,
            "conviction":        conviction,
            "dominant_dimension": synthesis.get("dominant_dimension"),
            "confluences":       synthesis.get("confluences", []),
            "conflicts":         synthesis.get("conflicts", ""),
            "reached_consensus": conviction >= MIN_CONVICTION and vote in ("BUY", "SELL"),
            "agents_voted":      [a.get("agent_id") for a in analyses] + [synthesis.get("agent_id")],
            "reasoning":         [reasoning],
            "symbol":            symbol,
        }
        self.store.save_decision(self._cycle, decision_result)
        self.store.save_risk_state(
            self.risk.state.daily_loss,
            self.risk.state.open_positions,
            balance,
        )
        self._decision_log.insert(0, {
            "symbol": symbol, "decision": vote,
            "score": conviction, "ts": datetime.now(timezone.utc).isoformat(),
        })
        self._decision_log = self._decision_log[:10]

        await self._update_portfolio(balance)

        # EpochManager tick
        if self.epoch:
            epoch_result = self.epoch.tick(balance, self._cycle, self.store)
            if epoch_result.get("paused"):
                _log("Sistema pausado por EpochManager.", "ERR")
                await broadcast_error("SYSTEM PAUSED: consecutive drawdown resets exceeded limit.")
                return
            if epoch_result.get("reset"):
                self.risk.state.daily_loss     = 0.0
                self.risk.state.open_positions = 0
                _log(f"Nueva época. Conservative: {epoch_result.get('conservative')}", "WARN")

        # ── PHASE 3 — Gate approval ───────────────────────────────────────────
        if vote not in ("BUY", "SELL") or conviction < MIN_CONVICTION:
            return

        if news_ctx.get("avoid_trading") and conviction < 0.80:
            _log(f"AVOID TRADING activo: {news_ctx.get('avoid_reason')}", "WARN")
            return

        if self._gate_agent:
            _log("PIPELINE Phase 3 — gate approval...", "INFO")
            try:
                gate = await asyncio.wait_for(
                    self._gate_agent.check(synthesis, self.risk.state),
                    timeout=GATE_TIMEOUT,
                )
            except Exception as e:
                _log(f"Phase 3 gate FAILED: {e} — bloqueando ejecución", "WARN")
                await broadcast_error(f"Pipeline Phase3 gate: {e}")
                return

            approved    = gate.get("approved", False)
            gate_reason = gate.get("reason", "")
            _log(
                f"GATE: {'APPROVED' if approved else 'REJECTED'} — {gate_reason}",
                "OK" if approved else "WARN",
            )
            self.store.save_gate_result(self._cycle, symbol, approved, gate_reason)
            gate_agent_id = f"{self._gate_agent.agent_id}({self._gate_agent.model})"
            await broadcast_agent_vote(
                agent_id=gate_agent_id,
                vote=vote if approved else "HOLD",
                confidence=conviction if approved else 0.2,
                reasoning=gate_reason,
            )
            if not approved:
                await broadcast_error(f"Gate rejected: {gate_reason}")
                return
        else:
            # Gate unavailable — apply local min conviction check
            if conviction < 0.65:
                _log(f"Gate no disponible, conviction {conviction:.2f} < 0.65 — bloqueando.", "WARN")
                return

        await self._execute_order(symbol, vote, conviction, market_data, balance, analyses)

    def _pick_symbols(self) -> list[str]:
        return TRADING_UNIVERSE

    def _build_context(self, balance: float, news_ctx: dict) -> dict:
        # Memoria episódica: últimas decisiones desde la DB (persiste entre reinicios)
        recent_str = "Sin historial"
        try:
            db_decisions = self.store.get_recent_decisions(limit=5)
            if db_decisions:
                recent_str = " | ".join(
                    f"{d['symbol']}:{d['decision']}(score={d['score']:.2f}, {d['ts'][:10]})"
                    for d in db_decisions
                )
        except Exception as e:
            # Fallback a memoria en RAM si la DB falla
            _log(f"[Context] DB de decisiones recientes falló, usando RAM: {e}", "WARN")
            recent_str = " | ".join(
                f"{d['symbol']}:{d['decision']}({d['score']:.2f})"
                for d in self._decision_log[:3]
            ) or "Sin historial"

        # PnL acumulado desde DB
        pnl_context = ""
        try:
            snapshots = self.store.get_portfolio_history(limit=1)
            if snapshots:
                s = snapshots[0]
                pnl_context = f" | Accumulated PnL: {s['pnl']:+.2f} USDT ({s['pnl_pct']:+.2f}%)"
        except Exception as e:
            _log(f"[Context] PnL acumulado no disponible: {e}", "WARN")

        # Post-mortem de época anterior si existe
        postmortem_ctx = ""
        if self.epoch:
            postmortem_ctx = self.epoch.get_postmortem_context(self.store)

        # Historial de trades con resultados reales (ganancias/pérdidas concretas)
        trade_history_str = "Sin operaciones cerradas aún"
        trade_stats_str   = ""
        try:
            recent_trades = self.store.get_recent_trades(limit=5)
            closed = [t for t in recent_trades if t["status"] == "CLOSED"]
            if closed:
                trade_history_str = " | ".join(
                    f"{t['side']}@${t['entry_price']:,.0f}→${t['exit_price']:,.0f} "
                    f"({t['exit_reason']}) {t['pnl']:+.2f}USDT"
                    for t in closed
                )
            stats = self.store.get_trade_stats()
            if stats["total"] > 0:
                streak_txt = (
                    f"+{stats['streak']} ganadora" if stats["streak"] > 0
                    else f"{stats['streak']} perdedora" if stats["streak"] < 0
                    else "sin racha"
                )
                trade_stats_str = (
                    f"Win rate: {stats['win_rate']}% ({stats['total']} ops) | "
                    f"Avg profit: ${stats['avg_profit']:+.2f} | "
                    f"Avg loss: ${stats['avg_loss']:.2f} | "
                    f"Racha actual: {streak_txt}"
                )
        except Exception as e:
            _log(f"[Context] Historial/stats de trades no disponible: {e}", "WARN")

        # Análisis previos del pipeline (Phase 1 últimos ciclos)
        prev_votes_str = "No executed trades yet"
        try:
            prev_votes_str = self.store.get_last_trade_context()
        except Exception as e:
            _log(f"[Context] Contexto de último trade no disponible: {e}", "WARN")

        phase1_history_str = ""
        try:
            phase1_history_str = self.store.get_phase1_summary(cycles=3)
        except Exception as e:
            _log(f"[Context] Resumen phase1 no disponible: {e}", "WARN")

        # Rendimiento histórico por agente (aciertos/errores en trades reales)
        agent_perf_str = ""
        try:
            agent_perf_str = self.store.get_agent_performance_summary(self.trading_mode)
        except Exception as e:
            _log(f"[Context] Rendimiento por agente no disponible: {e}", "WARN")

        # Eventos críticos del sistema (liquidaciones, resets, cambios de modo)
        system_events_str = ""
        try:
            system_events_str = self.store.get_system_events_summary(limit=3)
        except Exception as e:
            _log(f"[Context] Eventos de sistema no disponibles: {e}", "WARN")

        ctx: dict = {
            "news_sentiment":       news_ctx.get("overall_sentiment", 0.0),
            "news_impact":          news_ctx.get("market_impact", "LOW"),
            "key_events":           news_ctx.get("key_events", []),
            "news_bias":            news_ctx.get("recommended_action_bias", "HOLD"),
            "geopolitical_summary": news_ctx.get("geopolitical_summary", ""),
            "catalyst_evidence":    news_ctx.get("catalyst_evidence", ""),
            "verified_catalyst":    news_ctx.get("verified_catalyst", False),
            "catalyst_veracity":    news_ctx.get("catalyst_veracity", 0.0),
            "avoid_trading":        news_ctx.get("avoid_trading", False),
            "avoid_reason":         news_ctx.get("avoid_reason", ""),
            "news_sources":         news_ctx.get("sources", []),
            "recent_decisions":     recent_str,
            "trading_mode":         self.trading_mode,
            "is_futures":           self.trading_mode == "FUTURES",
            "trade_history":        trade_history_str,
            "trade_stats":          trade_stats_str,
            "prev_agent_votes":     prev_votes_str,
            "phase1_history":       phase1_history_str,
            "agent_performance":    agent_perf_str,
            "system_events":        system_events_str,
            "portfolio_balance":    f"{balance:.2f}",
            "open_positions":       self.risk.state.open_positions,
            "daily_pnl":            f"{-self.risk.state.daily_loss:+.2f}{pnl_context}",
            "epoch_postmortem":     postmortem_ctx,
        }

        # Posición activa (solo si hay un trade abierto) — mark_price y PnL
        # se enriquecen en el ciclo de trading una vez que se tienen datos de mercado.
        if self._active_trade_id:
            try:
                open_trades = self.store.get_open_trades()
                trade = next((t for t in open_trades if t["id"] == self._active_trade_id), None)
                if trade:
                    ctx["active_position"] = {
                        "side":        trade["side"],
                        "symbol":      trade["symbol"],
                        "entry_price": trade["entry_price"],
                        "quantity":    trade["quantity"],
                        "sl_price":    trade["sl_price"],
                        "tp_price":    trade["tp_price"],
                        "leverage":    trade.get("leverage", 1),
                        "open_since":  trade["ts_open"],
                    }
            except Exception:
                pass

        return ctx

    # ── Votes ─────────────────────────────────────────────────────────────────

    async def _collect_votes(
        self, market_data: dict, context: dict
    ) -> list[TradingSignal]:
        """Lanza todos los agentes en paralelo con timeout individual."""

        async def _safe_analyze(agent) -> TradingSignal | None:
            try:
                sig = await asyncio.wait_for(
                    agent.analyze(market_data, context),
                    timeout=AGENT_TIMEOUT,
                )
                # Si el agente estaba en reconexión y respondió bien, limpiarlo
                if agent in self._reconnect_queue:
                    del self._reconnect_queue[agent]
                    _log(f"  [{agent.agent_id}] respondió — removido de cola de reconexión", "OK")

                _log(
                    f"  [{agent.agent_id}] {sig.vote.value} conf={sig.confidence:.2f}",
                    "INFO",
                )
                await broadcast_agent_vote(
                    agent_id=sig.agent_id,   # incluye (modelo) en el nombre
                    vote=sig.vote.value,
                    confidence=sig.confidence,
                    reasoning=sig.reasoning,
                )
                return sig
            except asyncio.TimeoutError:
                _log(f"  [{agent.agent_id}] TIMEOUT ({AGENT_TIMEOUT}s)", "WARN")
                await broadcast_error(f"Agent timeout: {agent.agent_id}")
                self._enqueue_reconnect(agent)
                return None
            except Exception as e:
                _log(f"  [{agent.agent_id}] ERROR: {e}", "WARN")
                await broadcast_error(f"Agent error [{agent.agent_id}]: {e}")
                self._enqueue_reconnect(agent)
                return None

        _log(f"Lanzando {len(self.voting_agents)} agentes en paralelo...", "INFO")
        raw = await asyncio.gather(*[_safe_analyze(a) for a in self.voting_agents])
        return [s for s in raw if s is not None]

    def _enqueue_reconnect(self, agent):
        """Encola un agente de pago para reintento de reconexión (si no está ya encolado)."""
        if agent.agent_id not in self.RECONNECTABLE_IDS:
            return
        if agent not in self._reconnect_queue:
            self._reconnect_queue[agent] = 0
            _log(f"  [{agent.agent_id}] encolado para reconexión automática", "WARN")

    async def _check_closed_trades(self):
        """
        Detecta si algún trade abierto fue cerrado (SL/TP/liquidación) entre ciclos.

        Para FUTURES usa _resolve_close_from_binance como ÚNICA fuente de verdad
        (precio y razón reales desde el historial) — coherente con el PositionMonitor
        y la reconciliación de arranque. Para SPOT mantiene el emparejamiento por precio.
        """
        open_trades = self.store.get_open_trades()
        if not open_trades:
            return

        # ── FUTURES: fuente de verdad única ───────────────────────────────────
        if self.trading_mode == "FUTURES":
            for trade in open_trades:
                symbol = trade["symbol"]
                try:
                    pos = self.futures.get_position(symbol)
                except Exception as e:
                    _log(f"[CheckClosed] Error consultando {symbol}: {e}", "WARN")
                    continue
                if pos:
                    continue   # sigue abierta

                try:
                    self.futures.cancel_all_orders(symbol)
                except Exception:
                    pass

                exit_price, exit_reason = self._resolve_close_from_binance(trade)
                pnl = self.store.close_trade(trade["id"], self._cycle, exit_price, exit_reason)
                if self._active_trade_id == trade["id"]:
                    self._active_trade_id = None
                    self._sl_order_id = None
                if self.risk.state.open_positions > 0:
                    self.risk.state.open_positions -= 1
                await broadcast_position_update(None)
                _log(
                    f"[CheckClosed] Trade #{trade['id']} cerrado: {exit_reason} "
                    f"@ ${exit_price:,.2f} | PnL={pnl:+.4f} USDT",
                    "OK" if exit_reason == "TP" else "WARN",
                )
            return

        # ── SPOT: emparejamiento por precio (heurístico legacy) ────────────────
        try:
            filled = self._client.get_recent_filled_orders(TRADING_UNIVERSE[0], limit=30)
        except Exception:
            return

        for trade in open_trades:
            sl  = trade.get("sl_price")
            tp  = trade.get("tp_price")
            exit_price  = None
            exit_reason = None

            for o in filled:
                price = o["price"]
                if tp and abs(price - tp) / tp < 0.001:
                    exit_price  = price
                    exit_reason = "TP"
                    break
                if sl and abs(price - sl) / sl < 0.001:
                    exit_price  = price
                    exit_reason = "SL"
                    break

            if exit_price:
                self.store.close_trade(trade["id"], self._cycle, exit_price, exit_reason)
                pnl_sign = "+" if exit_reason == "TP" else "-"
                _log(
                    f"Trade #{trade['id']} cerrado por {exit_reason} "
                    f"@ ${exit_price:,.2f} ({pnl_sign})",
                    "OK" if exit_reason == "TP" else "WARN",
                )
                if self.risk.state.open_positions > 0:
                    self.risk.state.open_positions -= 1

    # ── Execution ─────────────────────────────────────────────────────────────

    async def _execute_order(
        self,
        symbol: str,
        side: str,       # BUY/SELL en spot | LONG/SHORT en futures (convertido aquí)
        score: float,
        market_data: dict,
        balance: float,
        signals: list,
    ):
        price = market_data["price"]

        if self.trading_mode == "FUTURES":
            await self._execute_futures_order(symbol, side, score, price, balance, signals)
        else:
            await self._execute_spot_order(symbol, side, score, price, market_data, balance, signals)

    async def _execute_futures_order(
        self, symbol: str, decision: str, score: float,
        price: float, balance: float, signals: list,
    ):
        # Una sola posición activa a la vez
        if self._active_trade_id is not None:
            _log(f"[Futures] Trade #{self._active_trade_id} ya activo — bloqueando nueva ejecución", "WARN")
            return
        open_trades = self.store.get_open_trades()
        if open_trades:
            _log(f"[Futures] {len(open_trades)} trade(s) abierto(s) en DB — bloqueando", "WARN")
            return

        # BUY → LONG, SELL → SHORT
        side = "LONG" if decision == "BUY" else "SHORT"

        # Position sizing conviction-based: escala de MIN_POSITION_USDT a MAX_POSITION_USDT
        # conviction 0.60 → $500 | conviction 1.0 → $1000
        t = min(1.0, max(0.0, (score - MIN_CONVICTION) / max(0.01, 1.0 - MIN_CONVICTION)))
        position_usdt = round(MIN_POSITION_USDT + t * (MAX_POSITION_USDT - MIN_POSITION_USDT), 2)
        qty = self.futures._adjust_quantity(symbol, round(position_usdt / price, 6))
        if qty <= 0:
            _log(f"[Futures] Qty ajustada = 0, saltando.", "WARN")
            return

        # Gate-check
        gate_ok = True if DECISION_MODE == "DEEPSEEK_SINGLE" else await self.local_agent.gate_check(decision, score)
        if not gate_ok:
            _log(f"[Futures] Gate-check BLOQUEÓ {side} score={score:.3f}", "WARN")
            return

        # Calcular precios
        sl  = self.futures.calculate_sl(side, price)
        tp  = self.futures.calculate_tp(side, price)
        liq = self.futures.calculate_liquidation_price(side, price, FUTURES_LEVERAGE)
        margin = self.futures.calculate_margin(price, qty, FUTURES_LEVERAGE)

        # Validación de riesgo futures
        order_req = OrderRequest(
            symbol=symbol, side=side, quantity=qty,
            price=price, confidence=score,
            stop_loss_pct=0.015, take_profit_pct=0.025,
        )
        approved, reason = self.risk.validate_futures_order(order_req, FUTURES_LEVERAGE, liq)
        if not approved:
            _log(f"[Futures] RiskManager BLOQUEÓ: {reason}", "WARN")
            await broadcast_error(f"Futures order blocked: {reason}")
            return

        try:
            result = self.futures.open_position(symbol, side, qty, FUTURES_LEVERAGE)
            fill_price = result.get("price", price)
            liq_actual = self.futures.calculate_liquidation_price(side, fill_price, FUTURES_LEVERAGE)

            _log(
                f"[Futures] POSICIÓN ABIERTA: {side} {qty} {symbol} @ ${fill_price:,.2f} "
                f"| Nocional=${position_usdt:,.0f} Margen=${margin:,.2f} "
                f"| SL=${sl:,.2f} TP=${tp:,.2f} LIQ=${liq_actual:,.2f} LEV={FUTURES_LEVERAGE}x",
                "OK",
            )

            # Colocar SL/TP automáticos y guardar SL order ID para trailing
            try:
                sl_result = self.futures.place_stop_loss(symbol, side, sl)
                self._sl_order_id = sl_result.get("order_id")
                self.futures.place_take_profit(symbol, side, tp)
            except Exception as e:
                _log(f"[Futures] SL/TP placement error: {e}", "WARN")

            self.risk.open_position()
            await broadcast_order(symbol, side, qty, fill_price, sl, tp)

            # Registrar en DB — incluye sl_order_id para poder restaurarlo tras reinicio
            trade_id = self.store.open_trade(
                cycle=self._cycle, symbol=symbol, side=side,
                entry_price=fill_price, quantity=qty,
                sl_price=sl, tp_price=tp, signals=signals,
                mode="FUTURES", leverage=FUTURES_LEVERAGE,
                liquidation_price=liq_actual, margin_used=margin,
                sl_order_id=self._sl_order_id,
            )
            self._active_trade_id = trade_id

            # Registrar evento en system_events
            self.store.log_system_event(
                "POSITION_OPEN", "FUTURES", balance,
                {"side": side, "entry": fill_price, "leverage": FUTURES_LEVERAGE,
                 "liq": liq_actual, "score": score},
            )

        except Exception as e:
            err = f"[Futures] Error abriendo posición {side} {symbol}: {e}"
            _log(err, "ERR")
            await broadcast_error(err)

    async def _execute_spot_order(
        self, symbol: str, side: str, score: float,
        price: float, market_data: dict, balance: float, signals: list,
    ):
        qty = self.risk.calculate_quantity(symbol, price)
        qty = self.spot._adjust_quantity(symbol, qty)
        if qty <= 0:
            _log(f"[Spot] Qty ajustada = 0, saltando.", "WARN")
            return

        gate_ok = True if DECISION_MODE == "DEEPSEEK_SINGLE" else await self.local_agent.gate_check(side, score)
        if not gate_ok:
            _log(f"[Spot] Gate-check BLOQUEÓ {side} score={score:.3f}", "WARN")
            return

        order_req = OrderRequest(
            symbol=symbol, side=side, quantity=qty,
            price=price, confidence=score,
        )
        approved, reason = self.risk.validate_order(order_req)
        if not approved:
            _log(f"[Spot] RiskManager BLOQUEÓ: {reason}", "WARN")
            await broadcast_error(f"Spot order blocked: {reason}")
            return

        sl = self.spot._round_price(symbol, self.risk.calculate_stop_loss(side, price))
        tp = self.spot._round_price(symbol, self.risk.calculate_take_profit(side, price))

        try:
            result = self.spot.place_market_order(symbol, side, qty)
            fill_price = result.get("price", price)
            _log(
                f"[Spot] ORDEN EJECUTADA: {side} {qty} {symbol} @ ${fill_price:,.2f} "
                f"| SL=${sl:,.2f} TP=${tp:,.2f}",
                "OK",
            )
            try:
                self.spot.place_stop_loss(symbol, side, qty, sl)
                self.spot.place_take_profit(symbol, side, qty, tp)
            except Exception as e:
                _log(f"[Spot] SL/TP error: {e}", "WARN")

            self.risk.open_position()
            await broadcast_order(symbol, side, qty, fill_price, sl, tp)

            trade_id = self.store.open_trade(
                cycle=self._cycle, symbol=symbol, side=side,
                entry_price=fill_price, quantity=qty,
                sl_price=sl, tp_price=tp, signals=signals,
                mode="SPOT", leverage=1,
            )
            self._active_trade_id = trade_id

        except Exception as e:
            err = f"[Spot] Error ejecutando {side} {symbol}: {e}"
            _log(err, "ERR")
            await broadcast_error(err)

    async def _check_balance_reset(self, current_balance: float):
        """
        Detecta si el usuario reinició el balance de Binance testnet (vuelve a ~$5,000).
        Condición: balance ≥ $4,900 Y saltó ≥ $300 respecto al ciclo anterior.
        Al detectar: registra el reset en DB, limpia hard stop y notifica al dashboard.
        """
        if self._prev_binance_balance is None:
            self._prev_binance_balance = current_balance
            return

        jump = current_balance - self._prev_binance_balance
        if current_balance >= (DEMO_INITIAL_BALANCE - 100) and jump >= DEMO_RESET_MIN_JUMP:
            _log(
                f"Reset de Binance detectado: ${self._prev_binance_balance:,.2f} → "
                f"${current_balance:,.2f} (+${jump:,.2f}) — "
                f"Presupuesto operativo reiniciado a ${TRADING_BUDGET:,.2f}",
                "OK",
            )
            self.store.reset_trading_budget(current_balance, self._prev_binance_balance)
            self.store.log_system_event(
                "BUDGET_RESET",
                self.trading_mode,
                current_balance,
                {
                    "prev_balance": self._prev_binance_balance,
                    "jump": round(jump, 2),
                    "trading_budget_reset_to": TRADING_BUDGET,
                },
            )
            # Limpiar hard stop si estaba activo
            if self._hard_stop:
                self._hard_stop = False
                _log("Hard stop desactivado — balance reiniciado.", "OK")
            # Limpiar mensaje de hard stop en el dashboard
            from api.main import app_state
            app_state["hard_stop_message"] = None

        self._prev_binance_balance = current_balance

    async def _update_portfolio(self, binance_balance: float):
        await self._check_balance_reset(binance_balance)
        budget_pnl      = round(self.store.get_total_pnl(), 4)
        effective_budget = self._effective_budget()
        # pnl_pct relativo al capital inicial ($1,000) para ver el retorno total
        budget_pnl_pct  = round(budget_pnl / TRADING_BUDGET * 100, 4) if TRADING_BUDGET > 0 else 0.0
        self.store.save_portfolio(self._cycle, binance_balance, budget_pnl, budget_pnl_pct)
        await broadcast_portfolio(binance_balance, effective_budget, budget_pnl, budget_pnl_pct)

    async def _refresh_idle_dashboard(self):
        """
        Refresco ligero del dashboard mientras el decisor está pausado (fuera de horario).
        Solo usa la API de Binance (sin LLM, sin costo) para mantener vivos el precio,
        los indicadores y el balance. NO guarda snapshot en DB para no inflar el historial.
        """
        try:
            balance = (
                self.futures.get_futures_balance()
                if self.trading_mode == "FUTURES"
                else self.spot.get_portfolio_value()
            )
        except Exception:
            balance = self.risk.state.portfolio_balance

        try:
            for sym in self._pick_symbols():
                app_state.setdefault("market_data", {})[sym] = self._client.get_market_data(sym)
        except Exception as e:
            _log(f"[Idle] Error refrescando market data: {e}", "WARN")

        try:
            budget_pnl = round(self.store.get_total_pnl(), 4)
            budget_pnl_pct = round(budget_pnl / TRADING_BUDGET * 100, 4) if TRADING_BUDGET > 0 else 0.0
            await broadcast_portfolio(balance, self._effective_budget(), budget_pnl, budget_pnl_pct)
        except Exception as e:
            _log(f"[Idle] Error actualizando portfolio: {e}", "WARN")

    # ── Reconnect loop ────────────────────────────────────────────────────────

    async def run_reconnect_loop(self):
        """
        Cada RECONNECT_INTERVAL segundos intenta reactivar agentes de pago caídos.
        Máximo RECONNECT_MAX_ATTEMPTS por agente; si no responde, se descarta definitivamente
        y los demás continúan con pesos redistribuidos automáticamente por el Decider.
        """
        _log("Reconnect loop iniciado.", "INFO")
        while True:
            await asyncio.sleep(self.RECONNECT_INTERVAL)

            if not self._reconnect_queue:
                continue

            permanently_down = []
            for agent, attempts in list(self._reconnect_queue.items()):
                new_attempts = attempts + 1
                self._reconnect_queue[agent] = new_attempts
                _log(
                    f"[Reconnect] {agent.agent_id} — intento {new_attempts}/{self.RECONNECT_MAX_ATTEMPTS}",
                    "WARN",
                )
                ok = await self._check_agent(agent)
                if ok is True:
                    del self._reconnect_queue[agent]
                    if agent not in self.voting_agents:
                        self.voting_agents.append(agent)
                    _log(f"[Reconnect] {agent.agent_id} RESTAURADO — vuelve al pool de votación", "OK")
                    await broadcast_error(f"Agent reconnected: {agent.agent_id}")
                elif new_attempts >= self.RECONNECT_MAX_ATTEMPTS:
                    del self._reconnect_queue[agent]
                    permanently_down.append(agent)
                    _log(
                        f"[Reconnect] {agent.agent_id} sin respuesta tras {new_attempts} intentos — descartado",
                        "ERR",
                    )
                    await broadcast_error(f"Agent permanently down: {agent.agent_id}")

            # Remover definitivamente del pool de votación
            for agent in permanently_down:
                if agent in self.voting_agents:
                    self.voting_agents.remove(agent)
                    _log(
                        f"[Reconnect] {agent.agent_id} removido del pool. "
                        f"Quedan {len(self.voting_agents)} agentes activos.",
                        "WARN",
                    )

    # ── Position Monitor (futures) ────────────────────────────────────────────

    def _compute_effective_balance(self) -> float:
        """Balance real USDT de Binance futures (para hard stop y risk checks)."""
        try:
            return self.futures.get_futures_balance()
        except Exception:
            return self.risk.state.portfolio_balance

    def _effective_budget(self) -> float:
        """
        Presupuesto operativo compuesto: capital inicial + PnL acumulado de trades cerrados.
        Persiste entre reinicios via DB. Nunca baja de 0.
        Ejemplos: start=$1000, +$200 profit → $1200; luego -$300 loss → $900.
        """
        total_pnl = self.store.get_total_pnl()
        return max(1.0, round(TRADING_BUDGET + total_pnl, 2))

    async def _trigger_hard_stop(self, effective_balance: float):
        """
        Cierra posiciones, cancela órdenes, registra en DB y notifica al dashboard.
        Se activa cuando el balance efectivo alcanza HARD_STOP_BALANCE ($600).
        """
        self._hard_stop = True
        total_loss = abs(self.store.get_total_pnl())
        msg  = (
            f"⛔ HARD STOP — Pérdida máxima alcanzada: ${total_loss:.2f} USDT "
            f"(límite: ${MAX_TRADING_LOSS:.0f} sobre presupuesto de ${TRADING_BUDGET:.0f}). "
            f"Reinicia los assets en demo.binance.com y reinicia el sistema."
        )
        _log(msg, "ERR")

        # 1. Cancelar todas las órdenes abiertas y cerrar posición si existe
        try:
            symbol = TRADING_UNIVERSE[0]
            self.futures.cancel_all_orders(symbol)
            pos = self.futures.get_position(symbol)
            if pos:
                self.futures.close_position_market(symbol, pos["side"], pos["quantity"])
                _log(f"[HardStop] Posición {pos['side']} cerrada.", "WARN")
        except Exception as e:
            _log(f"[HardStop] Error cerrando posición: {e}", "WARN")

        # 2. Cerrar trade en DB si hay uno abierto
        if self._active_trade_id:
            try:
                md = self.futures.get_market_data(TRADING_UNIVERSE[0])
                self.store.close_trade(
                    self._active_trade_id, self._cycle,
                    md["price"], "HARD_STOP",
                )
                self.risk.state.open_positions = 0
                self._active_trade_id = None
            except Exception as e:
                _log(f"[HardStop] Error cerrando trade en DB: {e}", "WARN")

        # 3. Registrar en system_events
        self.store.log_system_event(
            "HARD_STOP", self.trading_mode, effective_balance,
            {
                "loss":            round(total_loss, 2),
                "trading_budget":  TRADING_BUDGET,
                "max_loss_limit":  MAX_TRADING_LOSS,
                "cycle":           self._cycle,
                "message":         "Límite de pérdida alcanzado. Reiniciar assets.",
            },
        )

        # 4. Notificar dashboard
        await broadcast_hard_stop(msg)
        await broadcast_position_update(None)

    async def _check_trailing_stop(self, pos: dict):
        """
        Mueve el SL hacia arriba (LONG) o abajo (SHORT) si el precio se ha movido
        lo suficiente a favor. Solo actúa si:
          - La posición se movió >= TRAIL_ACTIVATION_PCT desde la entrada
          - El nuevo SL mejora el actual en >= TRAIL_MIN_STEP_PCT
        """
        if not self._active_trade_id or not self._sl_order_id:
            return

        side         = pos["side"]
        entry_price  = pos["entry_price"]
        current_price = pos.get("mark_price") or entry_price

        move_pct = (
            (current_price - entry_price) / entry_price
            if side == "LONG"
            else (entry_price - current_price) / entry_price
        )

        if move_pct < TRAIL_ACTIVATION_PCT:
            return

        new_sl = (
            current_price * (1 - TRAIL_DISTANCE_PCT)
            if side == "LONG"
            else current_price * (1 + TRAIL_DISTANCE_PCT)
        )
        symbol = TRADING_UNIVERSE[0]
        new_sl = self.futures._round_price(symbol, new_sl)

        open_trades = self.store.get_open_trades()
        trade = next((t for t in open_trades if t["id"] == self._active_trade_id), None)
        if not trade:
            return

        current_sl = trade.get("sl_price", 0) or 0
        if current_sl == 0:
            return

        improvement = (
            (new_sl - current_sl) / current_sl
            if side == "LONG"
            else (current_sl - new_sl) / current_sl
        )
        if improvement < TRAIL_MIN_STEP_PCT:
            return

        try:
            self.futures.cancel_order(symbol, self._sl_order_id)
            sl_result = self.futures.place_stop_loss(symbol, side, new_sl)
            self._sl_order_id = sl_result.get("order_id")
            self.store.update_trade_sl(self._active_trade_id, new_sl, self._sl_order_id)
            _log(
                f"[Trailing] SL movido: ${current_sl:,.1f} → ${new_sl:,.1f} "
                f"(move={move_pct*100:.2f}%)",
                "OK",
            )
        except Exception as e:
            _log(f"[Trailing] Error al mover SL: {e}", "WARN")

    async def run_position_monitor_loop(self):
        """
        Loop ligero cada POSITION_MONITOR segundos (default 3 min).
        Sin agentes — solo consulta Binance para:
          1. Actualizar PnL no realizado de la posición activa
          2. Detectar liquidaciones (posición desapareció sin SL/TP esperado)
          3. Emitir funding fee acumulado al trade en DB
        """
        _log(f"Position monitor iniciado (cada {POSITION_MONITOR}s).", "INFO")
        _funding_ticks = 0   # ticks desde último cobro de funding (cada 8h = 160 ticks a 3min)
        FUNDING_TICKS_PER_PERIOD = max(1, (8 * 3600) // POSITION_MONITOR)

        while True:
            await asyncio.sleep(POSITION_MONITOR)
            _funding_ticks += 1

            if self.trading_mode != "FUTURES" or not self._active_trade_id:
                continue

            try:
                pos = self.futures.get_position(TRADING_UNIVERSE[0])
                if pos:
                    # Enriquecer con SL/TP y tiempo de apertura desde la DB
                    if self._active_trade_id:
                        open_trades = self.store.get_open_trades()
                        trade = next((t for t in open_trades if t["id"] == self._active_trade_id), None)
                        if trade:
                            pos["sl_price"]  = trade.get("sl_price")
                            pos["tp_price"]  = trade.get("tp_price")
                            pos["open_time"] = trade.get("ts_open")
                    # Posición abierta — actualizar dashboard y evaluar trailing stop
                    await broadcast_position_update(pos)
                    _log(
                        f"[Monitor] {pos['side']} PnL={pos['unrealized_pnl']:+.2f} USDT "
                        f"LIQ=${pos['liquidation_price']:,.0f}",
                        "INFO",
                    )
                    await self._check_trailing_stop(pos)

                    # Acumular funding fees reales desde Binance cada ~8h
                    if _funding_ticks >= FUNDING_TICKS_PER_PERIOD:
                        _funding_ticks = 0
                        try:
                            open_t = self.store.get_open_trades()
                            trade  = next((t for t in open_t if t["id"] == self._active_trade_id), None)
                            if trade:
                                # income desde la apertura del trade
                                import datetime as _dt
                                ts_open  = trade.get("ts_open", "")
                                since_ms = int(_dt.datetime.fromisoformat(ts_open).timestamp() * 1000) if ts_open else None
                                income = self.futures.client.futures_income_history(
                                    symbol=TRADING_UNIVERSE[0],
                                    incomeType="FUNDING_FEE",
                                    startTime=since_ms,
                                    limit=50,
                                )
                                total_fee = sum(float(r["income"]) for r in income) if income else 0.0
                                # Guardar solo el delta desde el último registro
                                prev = trade.get("funding_fees", 0.0) or 0.0
                                delta = round(total_fee - prev, 6)
                                if abs(delta) > 0.0001:
                                    self.store.add_funding_fee(self._active_trade_id, delta)
                                    _log(
                                        f"[Funding] Fee {'pagado' if delta > 0 else 'recibido'}: "
                                        f"${abs(delta):.4f} USDT (total acumulado: ${total_fee:+.4f})",
                                        "INFO",
                                    )
                        except Exception as e:
                            _log(f"[Funding] Error obteniendo income history: {e}", "WARN")
                else:
                    # Posición desapareció — puede ser liquidación o cierre por SL/TP
                    # El cierre normal lo maneja _check_closed_trades(); aquí detectamos liquidación
                    open_trades = self.store.get_open_trades()
                    if open_trades and self._active_trade_id:
                        active = next(
                            (t for t in open_trades if t["id"] == self._active_trade_id), None
                        )
                        if active:
                            # La posición ya no existe en Binance. Puede ser TP, SL, liquidación
                            # o cierre manual. Resolver el precio/razón REALES desde el historial
                            # (NO asumir liquidación: durante la pausa este es el único camino).
                            balance = self.futures.get_futures_balance()
                            try:
                                self.futures.cancel_all_orders(TRADING_UNIVERSE[0])
                            except Exception:
                                pass
                            exit_price, exit_reason = self._resolve_close_from_binance(active)
                            pnl = self.store.close_trade(
                                self._active_trade_id, self._cycle,
                                exit_price, exit_reason,
                            )
                            self.risk.state.open_positions = max(0, self.risk.state.open_positions - 1)
                            self._active_trade_id = None
                            self._sl_order_id = None
                            await broadcast_position_update(None)

                            event_type = "LIQUIDATION" if exit_reason == "LIQUIDATED" else "POSITION_CLOSE"
                            self.store.log_system_event(
                                event_type, "FUTURES", balance,
                                {
                                    "trade_id":   active["id"],
                                    "entry_price": active["entry_price"],
                                    "exit_price": exit_price,
                                    "exit_reason": exit_reason,
                                    "side":       active["side"],
                                    "pnl":        pnl,
                                    "detected_by": "position_monitor",
                                },
                            )
                            _log(
                                f"[Monitor] Trade #{active['id']} cerrado: {exit_reason} "
                                f"@ ${exit_price:,.2f} | PnL={pnl:+.4f} USDT | Balance: ${balance:.2f}",
                                "ERR" if exit_reason == "LIQUIDATED" else "OK",
                            )
                            if exit_reason == "LIQUIDATED":
                                await broadcast_error(
                                    f"LIQUIDATION detected: trade #{active['id']} @ ${exit_price:,.0f}"
                                )
            except Exception as e:
                _log(f"[Monitor] Error: {e}", "WARN")

    # ── Entry point ───────────────────────────────────────────────────────────

    async def run(self):
        # Silenciar el ruido de ConnectionResetError de los WebSocket en Windows
        asyncio.get_running_loop().set_exception_handler(_silence_connection_reset)

        await self.startup()

        # Arrancar el API server primero — el dashboard puede conectarse
        # mientras se carga el ciclo de noticias inicial
        _log("Iniciando API server...", "INFO")
        api_task = asyncio.create_task(self._serve_api())
        await asyncio.sleep(0.5)   # tiempo mínimo para que uvicorn haga bind del puerto

        # Correr WebSearchAgent una vez antes del primer ciclo de trading
        _log("Ejecutando primer ciclo de noticias antes de iniciar trading...", "INFO")
        try:
            await asyncio.wait_for(self.news_agent.run_cycle(), timeout=120)
        except asyncio.TimeoutError:
            _log("Timeout en primer ciclo de noticias, continuando con default context.", "WARN")
        except Exception as e:
            _log(f"Error en primer ciclo de noticias: {e}", "WARN")

        # Lanzar el resto de loops (api_task ya está corriendo)
        _log("Iniciando loops paralelos: News + Trading + Reconnect + Monitor", "OK")
        tasks = [
            api_task,
            asyncio.create_task(self.run_news_loop()),
            asyncio.create_task(self.run_trading_loop()),
            asyncio.create_task(self.run_reconnect_loop()),
            asyncio.create_task(self.run_position_monitor_loop()),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            # Ctrl+C: asyncio.run cancela la tarea principal → llegamos aquí.
            pass
        finally:
            await self._shutdown(tasks)

    async def _shutdown(self, tasks: list):
        """Apaga el servidor HTTP y cancela todos los loops de forma ordenada."""
        _log("Apagando: cerrando servidor y loops...", "WARN")
        # Pedir a uvicorn que cierre el puerto limpiamente
        if getattr(self, "_api_server", None) is not None:
            self._api_server.should_exit = True
        # Cancelar todas las tareas y esperar a que terminen
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        _log("Apagado completo.", "OK")

    async def _serve_api(self):
        """Arranca el servidor FastAPI dentro del mismo event loop."""
        config = uvicorn.Config(
            app=fastapi_app,
            host=API_HOST,
            port=API_PORT,
            log_level="warning",   # silencia uvicorn, no mezclar con nuestros logs
            timeout_graceful_shutdown=2,
        )
        server = uvicorn.Server(config)
        self._api_server = server
        # No dejar que uvicorn capture SIGINT/SIGTERM: queremos que asyncio.run maneje
        # Ctrl+C y cancele TODOS los loops de forma limpia (no solo el servidor HTTP).
        server.capture_signals = lambda: contextlib.nullcontext()
        _log(f"API en http://{API_HOST}:{API_PORT}", "OK")
        await server.serve()


# ─── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
 =========================================
   Vibe Trading -- Orchestrator v1.0
   Multi-Agent Crypto Trading System
 =========================================
""")
    orchestrator = TradingOrchestrator()
    try:
        asyncio.run(orchestrator.run())
    except KeyboardInterrupt:
        _log("Detenido por usuario (Ctrl+C)", "WARN")
    except Exception as e:
        _log(f"Error fatal: {e}", "ERR")
        traceback.print_exc()
        sys.exit(1)
