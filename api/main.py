import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# ── WebSocket connection manager ───────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] Client connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        print(f"[WS] Client disconnected. Total: {len(self.active)}")

    async def broadcast(self, event: str, data: Any):
        """Envía un evento a todos los clientes conectados."""
        message = json.dumps({"event": event, "data": data, "ts": datetime.now(timezone.utc).isoformat()})
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


# ── App state (compartido con el Orchestrator) ─────────────────────────────────

app_state: dict = {
    "system_status":  "idle",       # idle | running | stopped
    "trading_mode":   "FUTURES",    # FUTURES (default) | SPOT
    "current_cycle":  0,
    "last_decision":  None,
    "last_news":      None,
    "portfolio":      {"balance": 0.0, "pnl": 0.0, "pnl_pct": 0.0,
                       "binance_balance": 0.0, "trading_budget": 1000.0,
                       "budget_pnl": 0.0, "budget_pnl_pct": 0.0},
    "open_positions": [],
    "agent_votes":    [],
    "risk_health":    "HEALTHY",
    "errors":         [],
    "market_data":    {},
    "active_position":  None,        # posición futures activa
    "hard_stop_message": None,       # mensaje de hard stop si se alcanzó el límite
    "strategy_review":  None,        # última revisión estratégica diaria (Claude advisor)
    "lessons":          [],          # lecciones de post-mortem recientes (Claude advisor)
    "cooldown":         {"active": False, "loss_streak": 0, "remaining": "", "until": None},  # P1.5
    "config":         {              # configuración runtime (la setea el orquestador al arrancar)
        "analysis_interval_seconds": 900,
        "trading_hours_enabled":     False,
        "trading_hours_start":       8,
        "trading_hours_end":         20,
        "trading_timezone":          "UTC",
    },
}


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[API] Server started on port {os.getenv('API_PORT', 8000)}")
    yield
    print("[API] Server shutting down")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Vibe Trading API", version="1.0.0", lifespan=lifespan)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/state")
def get_state():
    return app_state


@app.get("/portfolio")
def get_portfolio():
    return app_state["portfolio"]


@app.get("/decisions")
def get_decisions():
    return {
        "last_decision": app_state["last_decision"],
        "agent_votes":   app_state["agent_votes"],
        "cycle":         app_state["current_cycle"],
    }


@app.get("/news")
def get_news():
    return app_state["last_news"] or {"message": "No news yet"}


@app.get("/risk")
def get_risk():
    return {
        "health":         app_state["risk_health"],
        "open_positions": app_state["open_positions"],
    }


@app.get("/market/{symbol}")
def get_market(symbol: str):
    data = app_state["market_data"].get(symbol.upper())
    if not data:
        return {"error": f"No data for {symbol} yet — start the orchestrator"}
    return data


@app.get("/mode")
def get_mode():
    return {"trading_mode": app_state["trading_mode"]}


@app.post("/mode/{mode}")
async def set_mode(mode: str):
    mode = mode.upper()
    if mode not in ("FUTURES", "SPOT"):
        return {"error": "Mode must be FUTURES or SPOT"}
    old_mode = app_state["trading_mode"]
    app_state["trading_mode"] = mode
    await manager.broadcast("mode_change", {"mode": mode, "previous": old_mode})
    return {"trading_mode": mode, "previous": old_mode}


@app.get("/position")
def get_position():
    return app_state.get("active_position") or {"message": "No active futures position"}


@app.get("/pnl-history")
def get_pnl_history(limit: int = 50):
    """Serie temporal de PnL por trade cerrado, con modo coloreado."""
    try:
        import sqlite3
        from pathlib import Path
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vibe_trading.db")
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT id, symbol, side, entry_price, exit_price, quantity, leverage, pnl,
                      exit_reason, ts_close, mode
               FROM trades WHERE status='CLOSED'
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        con.close()
        points = [
            {
                "id":          r["id"],
                "ts":          r["ts_close"],
                "symbol":      r["symbol"],
                "side":        r["side"],
                "entry_price": r["entry_price"],
                "exit_price":  r["exit_price"],
                "quantity":    r["quantity"],
                "leverage":    r["leverage"],
                "notional":    round((r["quantity"] or 0) * (r["entry_price"] or 0), 2),
                "pnl":         r["pnl"],
                "exit_reason": r["exit_reason"],
                "mode":        r["mode"] or "FUTURES",
            }
            for r in reversed(rows)
        ]
        # Calcular PnL acumulado
        cumulative = 0.0
        for p in points:
            cumulative += p["pnl"]
            p["cumulative_pnl"] = round(cumulative, 2)
        return {"points": points, "total_pnl": round(cumulative, 2)}
    except Exception as e:
        return {"error": str(e), "points": []}


@app.get("/shadow/calibration")
def get_shadow_calibration():
    """
    Harness contrafactual (P0.2): resumen + curva de calibración (tasa TP-first por bucket
    de confianza) sobre todas las señales del decisor, ejecutadas o no.
    """
    try:
        from core.state_store import StateStore
        store = StateStore()
        return {
            "summary":     store.get_shadow_summary(),
            "calibration": store.get_shadow_calibration(),
        }
    except Exception as e:
        return {"error": str(e), "summary": {}, "calibration": []}


# ── WebSocket ──────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    # Enviar estado actual al conectarse
    await ws.send_text(json.dumps({
        "event": "init",
        "data":  app_state,
        "ts":    datetime.now(timezone.utc).isoformat(),
    }))
    try:
        while True:
            # Mantener conexión viva con ping/pong
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── Broadcast helpers (usados por el Orchestrator) ─────────────────────────────

async def broadcast_cycle_start(cycle: int, pairs: list):
    app_state["current_cycle"] = cycle
    app_state["system_status"] = "running"
    await manager.broadcast("cycle_start", {"cycle": cycle, "pairs": pairs})


async def broadcast_agent_vote(agent_id: str, vote: str, confidence: float, reasoning: str, indicators: dict | None = None):
    vote_entry = {
        "agent_id":   agent_id,
        "vote":       vote,
        "confidence": confidence,
        "reasoning":  reasoning,
        "indicators": indicators,
        "ts":         datetime.now(timezone.utc).isoformat(),
    }
    app_state["agent_votes"] = [vote_entry] + app_state["agent_votes"][:19]  # últimos 20
    await manager.broadcast("agent_vote", vote_entry)


async def broadcast_decision(symbol: str, decision: str, score: float, reason: str):
    entry = {
        "symbol":   symbol,
        "decision": decision,
        "score":    score,
        "reason":   reason,
        "ts":       datetime.now(timezone.utc).isoformat(),
    }
    app_state["last_decision"] = entry
    await manager.broadcast("decision", entry)


async def broadcast_order(symbol: str, side: str, qty: float, price: float, sl: float, tp: float):
    entry = {
        "symbol": symbol,
        "side":   side,
        "qty":    qty,
        "price":  price,
        "sl":     sl,
        "tp":     tp,
        "ts":     datetime.now(timezone.utc).isoformat(),
    }
    # Reemplaza en vez de acumular — solo 1 entrada activa por símbolo
    app_state["open_positions"] = [
        p for p in app_state["open_positions"] if p["symbol"] != symbol
    ]
    app_state["open_positions"].append(entry)
    await manager.broadcast("order_placed", entry)


async def broadcast_portfolio(
    binance_balance: float,
    trading_budget: float,
    budget_pnl: float,
    budget_pnl_pct: float,
):
    app_state["portfolio"] = {
        "balance":         binance_balance,       # balance real Binance USDT
        "binance_balance": binance_balance,
        "trading_budget":  trading_budget,         # límite operativo ($1,000)
        "pnl":             budget_pnl,             # PnL acumulado sobre el budget
        "pnl_pct":         budget_pnl_pct,
        "budget_pnl":      budget_pnl,
        "budget_pnl_pct":  budget_pnl_pct,
    }
    await manager.broadcast("portfolio_update", app_state["portfolio"])


async def broadcast_news(context: dict):
    app_state["last_news"] = context
    await manager.broadcast("news_update", context)


async def broadcast_error(message: str):
    entry = {"message": message, "ts": datetime.now(timezone.utc).isoformat()}
    app_state["errors"] = [entry] + app_state["errors"][:9]  # últimos 10
    await manager.broadcast("error", entry)


async def broadcast_position_update(position: dict | None):
    app_state["active_position"] = position
    if position is None:
        app_state["open_positions"] = []
    # Enviar null (no {}) al cerrar: el frontend distingue "sin posición" de "posición con datos".
    await manager.broadcast("position_update", position)


async def broadcast_mode_change(mode: str):
    app_state["trading_mode"] = mode
    await manager.broadcast("mode_change", {"mode": mode})


async def broadcast_hard_stop(message: str):
    app_state["hard_stop_message"] = message
    await manager.broadcast("hard_stop", {"message": message, "ts": datetime.now(timezone.utc).isoformat()})


async def broadcast_strategy_review(review: dict):
    app_state["strategy_review"] = review
    await manager.broadcast("strategy_review", review)


async def broadcast_lesson(lesson: dict):
    app_state["lessons"] = [lesson] + app_state["lessons"][:19]  # últimas 20
    await manager.broadcast("trade_lesson", lesson)


async def broadcast_decision_verdict(verdict: str, reason: str = ""):
    """
    P1.8: veredicto final del ciclo (EXECUTED / SKIPPED_THRESHOLD / BLOCKED_RISK / BLOCKED /
    AVOID / HOLD) con su motivo. Se adjunta a la última decisión para que el dashboard muestre
    POR QUÉ un voto no se convirtió en trade.
    """
    if app_state.get("last_decision"):
        app_state["last_decision"]["verdict"] = verdict
        app_state["last_decision"]["verdict_reason"] = reason
    await manager.broadcast("decision_verdict", {
        "verdict": verdict, "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_cooldown(active: bool, loss_streak: int, remaining: str, until: str | None):
    """P1.5: estado del cooldown por racha de SLs para el badge del dashboard."""
    app_state["cooldown"] = {
        "active": active, "loss_streak": loss_streak, "remaining": remaining, "until": until,
    }
    await manager.broadcast("cooldown", app_state["cooldown"])
