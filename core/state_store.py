"""
core/state_store.py — Persistencia SQLite
==========================================
Guarda y restaura el estado del sistema entre reinicios.

Tablas activas (pipeline multi-agent):
  - decisions:        síntesis final por ciclo (vote + conviction + dominant_dimension)
  - phase1_analyses:  análisis de cada especialista Phase 1 (technical/sentiment/quant)
  - gate_results:     resultado del gate Phase 3 por ciclo
  - trades:           posiciones abiertas y cerradas con SL/TP
  - risk_state:       snapshot del RiskManager (daily_loss, open_positions)
  - portfolio_snapshots: balance + PnL por ciclo
  - system_events:    eventos críticos (EPOCH_RESET, LIQUIDATION, HARD_STOP...)

Tablas conservadas pero sin escritura en pipeline:
  - votes:            votación por agente (era ensemble) — vacía en pipeline
  - agent_performance: rendimiento histórico por agente — vacía en pipeline
"""

import sqlite3
import json
import os
from datetime import datetime, date, timezone
from pathlib import Path


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "vibe_trading.db",
)


def _conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _add_column_if_missing(con: sqlite3.Connection, table: str, col: str, col_def: str):
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if col not in existing:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate(con: sqlite3.Connection):
    """Migración incremental — agrega columnas faltantes sin destruir datos existentes."""
    # Futures columns (legacy migration)
    futures_cols = {
        "mode":               "TEXT    NOT NULL DEFAULT 'FUTURES'",
        "leverage":           "INTEGER NOT NULL DEFAULT 1",
        "liquidation_price":  "REAL",
        "margin_used":        "REAL",
        "funding_fees":       "REAL    NOT NULL DEFAULT 0.0",
        "sl_order_id":        "INTEGER",
    }
    for col, col_def in futures_cols.items():
        _add_column_if_missing(con, "trades", col, col_def)

    # Pipeline columns in decisions table
    pipeline_cols = {
        "conviction":          "REAL",
        "dominant_dimension":  "TEXT",
        "confluences":         "TEXT",
        "conflicts":           "TEXT",
    }
    for col, col_def in pipeline_cols.items():
        _add_column_if_missing(con, "decisions", col, col_def)


def init_db():
    """Crea las tablas si no existen. Idempotente."""
    with _conn() as con:
        con.executescript("""
            -- Decisiones finales por ciclo (pipeline: conviction-based; ensemble: score-based)
            CREATE TABLE IF NOT EXISTS decisions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                ts                 TEXT    NOT NULL,
                cycle              INTEGER NOT NULL,
                symbol             TEXT    NOT NULL,
                decision           TEXT    NOT NULL,   -- BUY | SELL | HOLD
                score              REAL    NOT NULL,   -- conviction (pipeline) o consensus_score (ensemble)
                raw_score          REAL,               -- legacy ensemble
                multiplier         REAL,               -- legacy ensemble news multiplier
                agents             TEXT,               -- JSON list of agent ids
                reasoning          TEXT,               -- JSON list of reasoning strings
                -- Pipeline-specific (NULL en modo ensemble)
                conviction         REAL,
                dominant_dimension TEXT,
                confluences        TEXT,               -- JSON list
                conflicts          TEXT
            );

            -- Análisis Phase 1 por especialista (pipeline only)
            CREATE TABLE IF NOT EXISTS phase1_analyses (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            TEXT    NOT NULL,
                cycle         INTEGER NOT NULL,
                symbol        TEXT    NOT NULL,
                agent_id      TEXT    NOT NULL,        -- e.g. "technical(deepseek-v4-flash)"
                direction     TEXT    NOT NULL,        -- BULLISH | BEARISH | NEUTRAL
                confidence    REAL    NOT NULL,
                signal_quality TEXT,                   -- STRONG | MODERATE | WEAK (technical only)
                pattern       TEXT,                    -- detected pattern (technical only)
                extra_fields  TEXT,                    -- JSON for agent-specific fields
                analysis      TEXT                     -- narrative max 3 sentences
            );

            -- Resultado del gate Phase 3 (pipeline only)
            CREATE TABLE IF NOT EXISTS gate_results (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT    NOT NULL,
                cycle     INTEGER NOT NULL,
                symbol    TEXT    NOT NULL,
                approved  INTEGER NOT NULL,            -- 0 | 1
                reason    TEXT
            );

            -- Votos individuales por agente (ensemble legacy — vacío en pipeline)
            CREATE TABLE IF NOT EXISTS votes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                cycle       INTEGER NOT NULL,
                symbol      TEXT    NOT NULL,
                agent_id    TEXT    NOT NULL,
                vote        TEXT    NOT NULL,
                confidence  REAL    NOT NULL,
                reasoning   TEXT
            );

            -- Estado del RiskManager
            CREATE TABLE IF NOT EXISTS risk_state (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ts              TEXT    NOT NULL,
                trade_date      TEXT    NOT NULL,
                daily_loss      REAL    NOT NULL DEFAULT 0.0,
                open_positions  INTEGER NOT NULL DEFAULT 0,
                portfolio_balance REAL  NOT NULL DEFAULT 0.0
            );

            -- Snapshots de portfolio por ciclo
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                cycle       INTEGER NOT NULL,
                balance     REAL    NOT NULL,
                pnl         REAL    NOT NULL DEFAULT 0.0,
                pnl_pct     REAL    NOT NULL DEFAULT 0.0
            );

            -- Trades ejecutados (spot y futures)
            CREATE TABLE IF NOT EXISTS trades (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_open       TEXT    NOT NULL,
                ts_close      TEXT,
                cycle_open    INTEGER NOT NULL,
                cycle_close   INTEGER,
                symbol        TEXT    NOT NULL,
                side          TEXT    NOT NULL,
                entry_price   REAL    NOT NULL,
                exit_price    REAL,
                quantity      REAL    NOT NULL,
                pnl           REAL,
                pnl_pct       REAL,
                exit_reason   TEXT,
                sl_price      REAL,
                tp_price      REAL,
                status        TEXT    NOT NULL DEFAULT 'OPEN',
                agent_votes   TEXT,                   -- JSON: pipeline analyses or ensemble votes
                mode              TEXT    NOT NULL DEFAULT 'FUTURES',
                leverage          INTEGER NOT NULL DEFAULT 1,
                liquidation_price REAL,
                margin_used       REAL,
                funding_fees      REAL    NOT NULL DEFAULT 0.0,
                sl_order_id       INTEGER
            );

            -- Rendimiento por agente (ensemble legacy — vacío en pipeline)
            CREATE TABLE IF NOT EXISTS agent_performance (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            TEXT    NOT NULL,
                trade_id      INTEGER NOT NULL,
                agent_id      TEXT    NOT NULL,
                vote          TEXT    NOT NULL,
                confidence    REAL    NOT NULL,
                reasoning     TEXT,
                trade_side    TEXT    NOT NULL,
                trade_outcome TEXT,
                trade_pnl     REAL,
                mode          TEXT    NOT NULL DEFAULT 'FUTURES'
            );

            -- Eventos críticos del sistema
            CREATE TABLE IF NOT EXISTS system_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                event_type  TEXT    NOT NULL,
                mode        TEXT,
                balance_at  REAL,
                detail      TEXT
            );

            -- Resets del presupuesto operativo (Binance testnet reset detectado)
            CREATE TABLE IF NOT EXISTS budget_resets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT    NOT NULL,
                balance_at   REAL    NOT NULL,
                prev_balance REAL
            );

            -- Lecciones de post-mortem por trade cerrado (bucle de aprendizaje con Claude)
            CREATE TABLE IF NOT EXISTS trade_lessons (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT    NOT NULL,
                trade_id     INTEGER NOT NULL,
                side         TEXT    NOT NULL,
                exit_reason  TEXT,
                pnl          REAL,
                outcome      TEXT,                 -- WIN | LOSS
                tag          TEXT,                 -- etiqueta corta del patrón
                lesson       TEXT                  -- lección accionable (1-2 oraciones)
            );

            -- Revisiones estratégicas diarias generadas por Claude
            CREATE TABLE IF NOT EXISTS strategy_reviews (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT    NOT NULL,
                review_date  TEXT    NOT NULL,      -- YYYY-MM-DD (UTC)
                grade        TEXT,                  -- A-F o etiqueta de salud
                win_rate     REAL,
                total_trades INTEGER,
                net_pnl      REAL,
                summary      TEXT,                  -- 2-4 oraciones
                adjustments  TEXT                   -- JSON list de ajustes sugeridos
            );

            -- Shadow signals (harness contrafactual, P0.2): TODA señal direccional
            -- (ejecutada o no) con el SL/TP que se habría usado, para medir la tasa real
            -- de TP-first por bucket de confianza. HOLD se guarda con status='HOLD' (no se resuelve).
            CREATE TABLE IF NOT EXISTS shadow_signals (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ts             TEXT    NOT NULL,          -- UTC ISO con +00:00
                cycle          INTEGER,
                symbol         TEXT    NOT NULL DEFAULT 'BTCUSDT',
                vote           TEXT    NOT NULL,          -- BUY | SELL | HOLD
                confidence     REAL    NOT NULL,
                executed       INTEGER NOT NULL DEFAULT 0,-- 1 si se convirtió en trade real
                blocked_reason TEXT,                      -- below_threshold | avoid_trading | blocked | NULL
                entry_price    REAL    NOT NULL,
                sl_price       REAL,
                tp_price       REAL,
                status         TEXT    NOT NULL DEFAULT 'PENDING', -- PENDING | TP_FIRST | SL_FIRST | EXPIRED | HOLD
                resolved_ts    TEXT,
                horizon_hours  INTEGER NOT NULL DEFAULT 48
            );

            -- Estado de riesgo runtime (P1.5): racha de SLs + cooldown, persiste entre reinicios.
            CREATE TABLE IF NOT EXISTS risk_runtime (
                id             INTEGER PRIMARY KEY CHECK (id = 1),
                loss_streak    INTEGER NOT NULL DEFAULT 0,
                cooldown_until TEXT,
                updated_ts     TEXT
            );
        """)
        _migrate(con)


class StateStore:
    """Interfaz principal para leer/escribir estado persistente."""

    def __init__(self):
        init_db()

    # ── Decisions ─────────────────────────────────────────────────────────────

    def save_decision(self, cycle: int, result: dict):
        """
        Persiste el resultado de un ciclo de decisión.
        Soporta formato pipeline (conviction + dominant_dimension) y ensemble legacy.
        """
        # Pipeline format: viene de synthesis o del decision_result armado en orchestrator
        conviction         = result.get("conviction") or result.get("consensus_score", 0.0)
        dominant_dimension = result.get("dominant_dimension")
        confluences        = json.dumps(result.get("confluences", []))
        conflicts          = result.get("conflicts", "")

        with _conn() as con:
            con.execute(
                """INSERT INTO decisions
                   (ts, cycle, symbol, decision, score, raw_score, multiplier,
                    agents, reasoning, conviction, dominant_dimension, confluences, conflicts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    cycle,
                    result.get("symbol", ""),
                    result.get("decision") or result.get("vote", "HOLD"),
                    conviction,
                    result.get("raw_score", conviction),
                    result.get("news_multiplier", 1.0),
                    json.dumps(result.get("agents_voted", [])),
                    json.dumps(result.get("reasoning", [])),
                    conviction,
                    dominant_dimension,
                    confluences,
                    conflicts,
                ),
            )

    def get_recent_decisions(self, limit: int = 20) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Shadow signals (harness contrafactual, P0.2) ──────────────────────────

    def save_shadow_signal(
        self, cycle: int, symbol: str, vote: str, confidence: float, entry_price: float,
        sl_price: float | None = None, tp_price: float | None = None,
        executed: int = 0, blocked_reason: str | None = None,
        status: str = "PENDING", horizon_hours: int = 48,
    ):
        with _conn() as con:
            con.execute(
                """INSERT INTO shadow_signals
                   (ts, cycle, symbol, vote, confidence, executed, blocked_reason,
                    entry_price, sl_price, tp_price, status, horizon_hours)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(), cycle, symbol, vote,
                    float(confidence), int(executed), blocked_reason,
                    entry_price, sl_price, tp_price, status, horizon_hours,
                ),
            )

    def get_pending_shadow_signals(self, limit: int = 200) -> list[dict]:
        """Señales direccionales aún sin resolver (para el loop de resolución)."""
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM shadow_signals WHERE status='PENDING' "
                "AND vote IN ('BUY','SELL') ORDER BY id ASC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_shadow_signal(self, signal_id: int, status: str, resolved_ts: str | None = None):
        with _conn() as con:
            con.execute(
                "UPDATE shadow_signals SET status=?, resolved_ts=? WHERE id=?",
                (status, resolved_ts or datetime.now(timezone.utc).isoformat(), signal_id),
            )

    def get_shadow_calibration(self) -> list[dict]:
        """Tasa de TP-first por bucket de confianza (ancho 0.05) sobre señales resueltas."""
        with _conn() as con:
            rows = con.execute(
                "SELECT confidence, status FROM shadow_signals "
                "WHERE vote IN ('BUY','SELL') AND status IN ('TP_FIRST','SL_FIRST','EXPIRED')"
            ).fetchall()
        buckets: dict[str, dict] = {}
        for r in rows:
            lo = int(r["confidence"] * 20) / 20.0
            key = f"{lo:.2f}-{lo + 0.05:.2f}"
            d = buckets.setdefault(key, {"bucket": key, "n": 0, "tp_first": 0, "sl_first": 0, "expired": 0})
            d["n"] += 1
            if r["status"] == "TP_FIRST":
                d["tp_first"] += 1
            elif r["status"] == "SL_FIRST":
                d["sl_first"] += 1
            else:
                d["expired"] += 1
        out = []
        for key in sorted(buckets):
            d = buckets[key]
            resolved = d["tp_first"] + d["sl_first"]
            d["tp_first_rate"] = round(d["tp_first"] / resolved, 3) if resolved else None
            out.append(d)
        return out

    def get_shadow_summary(self) -> dict:
        with _conn() as con:
            total       = con.execute("SELECT COUNT(*) FROM shadow_signals").fetchone()[0]
            directional = con.execute("SELECT COUNT(*) FROM shadow_signals WHERE vote IN ('BUY','SELL')").fetchone()[0]
            resolved    = con.execute("SELECT COUNT(*) FROM shadow_signals WHERE status IN ('TP_FIRST','SL_FIRST','EXPIRED')").fetchone()[0]
            pending     = con.execute("SELECT COUNT(*) FROM shadow_signals WHERE status='PENDING'").fetchone()[0]
            executed    = con.execute("SELECT COUNT(*) FROM shadow_signals WHERE executed=1").fetchone()[0]
            by_dir      = con.execute("SELECT vote, COUNT(*) c FROM shadow_signals WHERE vote IN ('BUY','SELL') GROUP BY vote").fetchall()
        return {
            "total": total, "directional": directional, "resolved": resolved,
            "pending": pending, "executed": executed,
            "by_direction": {r["vote"]: r["c"] for r in by_dir},
        }

    # ── Cooldown / racha de SLs (P1.5) ────────────────────────────────────────

    def save_cooldown_state(self, loss_streak: int, cooldown_until: str | None):
        with _conn() as con:
            con.execute(
                """INSERT INTO risk_runtime (id, loss_streak, cooldown_until, updated_ts)
                   VALUES (1, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       loss_streak=excluded.loss_streak,
                       cooldown_until=excluded.cooldown_until,
                       updated_ts=excluded.updated_ts""",
                (int(loss_streak), cooldown_until, datetime.now(timezone.utc).isoformat()),
            )

    def get_cooldown_state(self) -> dict:
        with _conn() as con:
            row = con.execute(
                "SELECT loss_streak, cooldown_until FROM risk_runtime WHERE id = 1"
            ).fetchone()
        if not row:
            return {"loss_streak": 0, "cooldown_until": None}
        return {"loss_streak": row["loss_streak"], "cooldown_until": row["cooldown_until"]}

    # ── Phase 1 Analyses (pipeline) ───────────────────────────────────────────

    def save_phase1_analyses(self, cycle: int, symbol: str, analyses: list[dict]):
        """Persiste los análisis de los especialistas Phase 1 del ciclo actual."""
        ts = datetime.now(timezone.utc).isoformat()
        with _conn() as con:
            for a in analyses:
                agent_id = a.get("agent_id", "unknown")
                # Extra fields: everything beyond the common schema
                extra = {
                    k: v for k, v in a.items()
                    if k not in ("agent_id", "direction", "confidence",
                                 "signal_quality", "pattern", "analysis")
                }
                con.execute(
                    """INSERT INTO phase1_analyses
                       (ts, cycle, symbol, agent_id, direction, confidence,
                        signal_quality, pattern, extra_fields, analysis)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ts, cycle, symbol, agent_id,
                        a.get("direction", "NEUTRAL"),
                        a.get("confidence", 0.0),
                        a.get("signal_quality"),
                        a.get("pattern"),
                        json.dumps(extra) if extra else None,
                        a.get("analysis", ""),
                    ),
                )

    def get_recent_phase1(self, limit: int = 30) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM phase1_analyses ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_phase1_summary(self, cycles: int = 5) -> str:
        """Resumen de Phase 1 de los últimos N ciclos para incluir en contexto."""
        with _conn() as con:
            rows = con.execute(
                """SELECT agent_id, direction, confidence, analysis
                   FROM phase1_analyses
                   WHERE cycle IN (
                       SELECT DISTINCT cycle FROM phase1_analyses
                       ORDER BY cycle DESC LIMIT ?
                   )
                   ORDER BY cycle DESC, id DESC""",
                (cycles,),
            ).fetchall()
        if not rows:
            return ""
        lines = [
            f"  [{r['agent_id']}] {r['direction']} ({r['confidence']:.2f}): {(r['analysis'] or '')[:80]}"
            for r in rows
        ]
        return f"Recent Phase 1 analyses ({len(rows)} entries):\n" + "\n".join(lines)

    # ── Gate Results (pipeline) ───────────────────────────────────────────────

    def save_gate_result(self, cycle: int, symbol: str, approved: bool, reason: str):
        with _conn() as con:
            con.execute(
                """INSERT INTO gate_results (ts, cycle, symbol, approved, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    cycle, symbol, 1 if approved else 0, reason,
                ),
            )

    def get_recent_gate_rejections(self, limit: int = 5) -> list[dict]:
        """Vetos recientes del auditor (approved=0), más reciente primero."""
        with _conn() as con:
            rows = con.execute(
                "SELECT ts, symbol, reason FROM gate_results WHERE approved=0 ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_gate_rejections_summary(self, limit: int = 5) -> str:
        """Resumen de los vetos recientes del auditor para retroalimentar al decisor."""
        rows = self.get_recent_gate_rejections(limit)
        if not rows:
            return ""
        return "\n".join(f"  - {r['symbol']}: {r['reason']}" for r in rows)

    # ── Risk State ────────────────────────────────────────────────────────────

    def save_risk_state(self, daily_loss: float, open_positions: int, balance: float):
        with _conn() as con:
            con.execute(
                """INSERT INTO risk_state (ts, trade_date, daily_loss, open_positions, portfolio_balance)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    date.today().isoformat(),
                    daily_loss,
                    open_positions,
                    balance,
                ),
            )

    def restore_risk_state(self, risk_manager) -> bool:
        today = date.today().isoformat()
        with _conn() as con:
            row = con.execute(
                """SELECT * FROM risk_state
                   WHERE trade_date = ?
                   ORDER BY id DESC LIMIT 1""",
                (today,),
            ).fetchone()

        if row:
            risk_manager.state.daily_loss        = row["daily_loss"]
            risk_manager.state.open_positions    = row["open_positions"]
            risk_manager.state.portfolio_balance = row["portfolio_balance"]
            return True
        return False

    # ── Portfolio Snapshots ───────────────────────────────────────────────────

    def save_portfolio(self, cycle: int, balance: float, pnl: float, pnl_pct: float):
        with _conn() as con:
            con.execute(
                """INSERT INTO portfolio_snapshots (ts, cycle, balance, pnl, pnl_pct)
                   VALUES (?, ?, ?, ?, ?)""",
                (datetime.now(timezone.utc).isoformat(), cycle, balance, pnl, pnl_pct),
            )

    def get_portfolio_history(self, limit: int = 100) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Trades ────────────────────────────────────────────────────────────────

    def open_trade(
        self,
        cycle: int,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        sl_price: float,
        tp_price: float,
        signals: list,
        mode: str = "FUTURES",
        leverage: int = 1,
        liquidation_price: float = 0.0,
        margin_used: float = 0.0,
        sl_order_id: int | None = None,
    ) -> int:
        """Registra una orden ejecutada. signals puede ser lista de TradingSignal o de dicts (pipeline)."""
        agent_votes = json.dumps([
            _serialize_signal(s) for s in signals
        ])
        with _conn() as con:
            cur = con.execute(
                """INSERT INTO trades
                   (ts_open, cycle_open, symbol, side, entry_price, quantity,
                    sl_price, tp_price, status, agent_votes,
                    mode, leverage, liquidation_price, margin_used, sl_order_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    cycle, symbol, side, entry_price, quantity,
                    sl_price, tp_price, agent_votes,
                    mode, leverage, liquidation_price, margin_used, sl_order_id,
                ),
            )
            return cur.lastrowid

    def close_trade(
        self,
        trade_id: int,
        cycle: int,
        exit_price: float,
        exit_reason: str,
        realized_pnl: float | None = None,
    ) -> float:
        """
        Cierra un trade. Retorna el PnL en USDT.

        Si se pasa `realized_pnl` (el PnL real reportado por Binance), se almacena tal cual
        — es la fuente de verdad y garantiza que el PnL nunca contradiga el `exit_reason`
        (p.ej. un cierre marcado TP no puede mostrar pérdida por un exit_price mal elegido).
        Si es None (cierre offline sin datos de Binance, o SPOT), se recalcula por
        diferencia de precios como fallback conservador.
        """
        with _conn() as con:
            row = con.execute(
                "SELECT entry_price, quantity, side FROM trades WHERE id = ?", (trade_id,)
            ).fetchone()
            if not row:
                return 0.0
            entry = row["entry_price"]
            qty   = row["quantity"]
            side  = row["side"]

            # pnl_pct = movimiento de precio % (signo según dirección), siempre derivable.
            if side in ("BUY", "LONG"):
                pnl_pct   = (exit_price - entry) / entry * 100 if entry else 0.0
                price_pnl = (exit_price - entry) * qty
            else:
                pnl_pct   = (entry - exit_price) / entry * 100 if entry else 0.0
                price_pnl = (entry - exit_price) * qty

            # PnL en USDT: el realizado de Binance manda; el de precio es solo fallback.
            pnl     = round(float(realized_pnl) if realized_pnl is not None else price_pnl, 4)
            pnl_pct = round(pnl_pct, 4)

            con.execute(
                """UPDATE trades
                   SET ts_close=?, cycle_close=?, exit_price=?, pnl=?,
                       pnl_pct=?, exit_reason=?, status='CLOSED'
                   WHERE id=?""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    cycle, exit_price, pnl, pnl_pct, exit_reason, trade_id,
                ),
            )
        return pnl

    def get_open_trades(self) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_trades(self, limit: int = 10) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_trade_stats(self) -> dict:
        with _conn() as con:
            rows = con.execute(
                "SELECT pnl FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT 20"
            ).fetchall()
        if not rows:
            return {"total": 0, "win_rate": 0.0, "avg_profit": 0.0, "avg_loss": 0.0, "streak": 0}
        pnls   = [r["pnl"] for r in rows]
        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        streak = 0
        sign   = 1 if pnls[0] > 0 else -1
        for p in pnls:
            if (p > 0) == (sign > 0):
                streak += sign
            else:
                break
        return {
            "total":      len(pnls),
            "win_rate":   round(len(wins) / len(pnls) * 100, 1),
            "avg_profit": round(sum(wins)   / len(wins),   2) if wins   else 0.0,
            "avg_loss":   round(sum(losses) / len(losses), 2) if losses else 0.0,
            "streak":     streak,
        }

    def update_trade_futures_info(
        self, trade_id: int, liquidation_price: float, margin_used: float,
        leverage: int, mode: str = "FUTURES"
    ):
        with _conn() as con:
            con.execute(
                """UPDATE trades SET liquidation_price=?, margin_used=?, leverage=?, mode=?
                   WHERE id=?""",
                (liquidation_price, margin_used, leverage, mode, trade_id),
            )

    def get_total_pnl(self) -> float:
        """Suma PnL de trades cerrados después del último reset de presupuesto."""
        with _conn() as con:
            reset_row = con.execute(
                "SELECT ts FROM budget_resets ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if reset_row:
                row = con.execute(
                    "SELECT COALESCE(SUM(pnl), 0.0) AS total FROM trades "
                    "WHERE status='CLOSED' AND ts_close > ?",
                    (reset_row["ts"],),
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT COALESCE(SUM(pnl), 0.0) AS total FROM trades WHERE status='CLOSED'"
                ).fetchone()
        return float(row["total"])

    def reset_trading_budget(self, current_balance: float, prev_balance: float | None = None):
        """Registra un reset del presupuesto operativo (detectado por salto de balance Binance)."""
        with _conn() as con:
            con.execute(
                "INSERT INTO budget_resets (ts, balance_at, prev_balance) VALUES (?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), current_balance, prev_balance),
            )

    def get_last_reset_ts(self) -> str | None:
        """Retorna el timestamp del último reset, o None si nunca hubo uno."""
        with _conn() as con:
            row = con.execute(
                "SELECT ts FROM budget_resets ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row["ts"] if row else None

    def update_trade_sl(self, trade_id: int, new_sl_price: float, new_sl_order_id: int | None = None):
        with _conn() as con:
            con.execute(
                "UPDATE trades SET sl_price=?, sl_order_id=? WHERE id=?",
                (new_sl_price, new_sl_order_id, trade_id),
            )

    def add_funding_fee(self, trade_id: int, fee: float):
        with _conn() as con:
            con.execute(
                "UPDATE trades SET funding_fees = funding_fees + ? WHERE id=?",
                (fee, trade_id),
            )

    def get_last_trade_context(self) -> str:
        """Contexto del último trade ejecutado para incluir en el prompt de agentes."""
        with _conn() as con:
            row = con.execute(
                "SELECT agent_votes, side, entry_price, exit_price, status, pnl FROM trades "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row or not row["agent_votes"]:
            return "No executed trades yet"
        try:
            votes = json.loads(row["agent_votes"])
            outcome = ""
            if row["status"] == "CLOSED" and row["pnl"] is not None:
                outcome = f" → {'WIN' if row['pnl'] > 0 else 'LOSS'} {row['pnl']:+.2f} USDT"
            header = f"Last trade: {row['side']} @ ${row['entry_price']:,.0f}{outcome}"
            lines  = [
                f"  [{v.get('agent_id', '?')}] {v.get('vote') or v.get('direction', '?')} "
                f"({v.get('confidence', 0):.2f}): {str(v.get('reasoning') or v.get('analysis', ''))[:100]}"
                for v in votes
            ]
            return header + "\n" + "\n".join(lines) if lines else header
        except Exception:
            return "No executed trades yet"

    # kept for backwards compatibility — delegates to get_last_trade_context
    def get_last_trade_votes(self) -> str:
        return self.get_last_trade_context()

    # ── Agent Performance (ensemble legacy — stubs kept for compat) ───────────

    def record_agent_performance(self, trade_id: int, signals: list, trade_side: str, mode: str = "FUTURES"):
        """No-op in pipeline mode. Kept so ensemble path still works if activated."""
        if not signals:
            return
        ts = datetime.now(timezone.utc).isoformat()
        with _conn() as con:
            for s in signals:
                sig = _serialize_signal(s)
                con.execute(
                    """INSERT INTO agent_performance
                       (ts, trade_id, agent_id, vote, confidence, reasoning, trade_side, trade_outcome, mode)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
                    (ts, trade_id, sig["agent_id"], sig["vote"],
                     sig["confidence"], sig.get("reasoning", ""), trade_side, mode),
                )

    def resolve_agent_performance(self, trade_id: int, outcome: str, pnl: float):
        with _conn() as con:
            con.execute(
                """UPDATE agent_performance SET trade_outcome=?, trade_pnl=? WHERE trade_id=?""",
                (outcome, pnl, trade_id),
            )

    def get_agent_performance_summary(self, mode: str = "FUTURES") -> str:
        with _conn() as con:
            rows = con.execute(
                """SELECT agent_id, vote, trade_outcome, COUNT(*) as n
                   FROM agent_performance
                   WHERE mode=? AND trade_outcome != 'OPEN'
                   GROUP BY agent_id, vote, trade_outcome
                   ORDER BY agent_id""",
                (mode,),
            ).fetchall()
        if not rows:
            return ""
        stats: dict[str, dict] = {}
        for r in rows:
            aid = r["agent_id"]
            if aid not in stats:
                stats[aid] = {"total": 0, "wins": 0, "losses": 0, "liquidated": 0}
            stats[aid]["total"] += r["n"]
            if r["trade_outcome"] == "WIN":
                stats[aid]["wins"] += r["n"]
            elif r["trade_outcome"] == "LOSS":
                stats[aid]["losses"] += r["n"]
            elif r["trade_outcome"] == "LIQUIDATED":
                stats[aid]["liquidated"] += r["n"]
        lines = []
        for aid, s in stats.items():
            if s["total"] == 0:
                continue
            wr  = round(s["wins"] / s["total"] * 100, 1)
            liq = f" | {s['liquidated']} liquidated" if s["liquidated"] else ""
            lines.append(f"  {aid}: {wr}% win rate ({s['wins']}W/{s['losses']}L{liq} of {s['total']} trades)")
        return "Agent historical accuracy ({}):\n".format(mode) + "\n".join(lines)

    # ── System Events ─────────────────────────────────────────────────────────

    def log_system_event(self, event_type: str, mode: str, balance: float, detail: dict):
        with _conn() as con:
            con.execute(
                """INSERT INTO system_events (ts, event_type, mode, balance_at, detail)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    event_type, mode, balance,
                    json.dumps(detail),
                ),
            )

    def get_system_events_summary(self, limit: int = 5) -> str:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM system_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in rows:
            detail = json.loads(r["detail"] or "{}")
            desc = detail.get("reason", detail.get("postmortem", ""))[:80]
            lines.append(f"  [{r['ts'][:10]}] {r['event_type']} ({r['mode']}) @ ${r['balance_at']:.0f}: {desc}")
        return "System events (recent):\n" + "\n".join(lines)

    # ── Trade lessons (learning loop) ─────────────────────────────────────────

    def save_trade_lesson(
        self, trade_id: int, side: str, exit_reason: str, pnl: float,
        outcome: str, tag: str, lesson: str,
    ):
        with _conn() as con:
            con.execute(
                """INSERT INTO trade_lessons
                   (ts, trade_id, side, exit_reason, pnl, outcome, tag, lesson)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    trade_id, side, exit_reason, pnl, outcome, tag, lesson,
                ),
            )

    def get_recent_lessons(self, limit: int = 8) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM trade_lessons ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_lessons_summary(self, limit: int = 8) -> str:
        """Resumen de lecciones recientes para inyectar en el prompt del decisor."""
        rows = self.get_recent_lessons(limit)
        if not rows:
            return ""
        lines = [
            f"  - [{r['outcome']} {r['pnl']:+.2f} | {r['tag'] or r['exit_reason'] or '?'}] {r['lesson']}"
            for r in rows if r.get("lesson")
        ]
        return "\n".join(lines)

    # ── Strategy reviews (daily) ──────────────────────────────────────────────

    def save_strategy_review(
        self, review_date: str, grade: str, win_rate: float,
        total_trades: int, net_pnl: float, summary: str, adjustments: list,
    ):
        with _conn() as con:
            con.execute(
                """INSERT INTO strategy_reviews
                   (ts, review_date, grade, win_rate, total_trades, net_pnl, summary, adjustments)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    review_date, grade, win_rate, total_trades, net_pnl,
                    summary, json.dumps(adjustments or []),
                ),
            )

    def has_review_for_date(self, review_date: str) -> bool:
        with _conn() as con:
            row = con.execute(
                "SELECT 1 FROM strategy_reviews WHERE review_date = ? LIMIT 1",
                (review_date,),
            ).fetchone()
        return row is not None

    def _review_row_to_dict(self, r) -> dict:
        d = dict(r)
        try:
            d["adjustments"] = json.loads(d.get("adjustments") or "[]")
        except Exception:
            d["adjustments"] = []
        return d

    def get_latest_review(self) -> dict | None:
        with _conn() as con:
            row = con.execute(
                "SELECT * FROM strategy_reviews ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._review_row_to_dict(row) if row else None

    def get_recent_reviews(self, limit: int = 7) -> list[dict]:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM strategy_reviews ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._review_row_to_dict(r) for r in rows]

    # ── Utilities ─────────────────────────────────────────────────────────────

    def clear_ensemble_data(self):
        """
        Borra datos de tablas de la era ensemble (votes, agent_performance, decisions con multiplier).
        Mantiene trades, risk_state, portfolio_snapshots, system_events y phase1_analyses.
        Usar solo al migrar a pipeline por primera vez.
        """
        with _conn() as con:
            con.execute("DELETE FROM votes")
            con.execute("DELETE FROM agent_performance")
            con.execute("DELETE FROM decisions")
            con.execute("DELETE FROM phase1_analyses")
            con.execute("DELETE FROM gate_results")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_signal(s) -> dict:
    """
    Serializa un TradingSignal (objeto) o un dict de análisis pipeline a formato JSON uniforme.
    Pipeline analyses tienen 'direction' (BULLISH/BEARISH/NEUTRAL); ensemble tiene 'vote' (BUY/SELL/HOLD).
    """
    if hasattr(s, "agent_id"):
        # TradingSignal object (ensemble)
        return {
            "agent_id":   s.agent_id,
            "vote":       s.vote.value if hasattr(s.vote, "value") else s.vote,
            "confidence": s.confidence,
            "reasoning":  s.reasoning or "",
        }
    # Plain dict — pipeline analysis or compat dict
    direction_to_vote = {"BULLISH": "BUY", "BEARISH": "SELL", "NEUTRAL": "HOLD"}
    vote = s.get("vote") or direction_to_vote.get(s.get("direction", "NEUTRAL"), "HOLD")
    return {
        "agent_id":   s.get("agent_id", "unknown"),
        "vote":       vote,
        "confidence": s.get("confidence", 0.0),
        "reasoning":  s.get("reasoning") or s.get("analysis", ""),
        "direction":  s.get("direction"),
    }
