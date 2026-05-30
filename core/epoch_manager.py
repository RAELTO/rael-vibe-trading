"""
core/epoch_manager.py — Sistema de recuperación por drawdown
=============================================================
Monitorea el balance en cada ciclo. Si cae por debajo del umbral mínimo
(MIN_BALANCE_PCT del inicial), genera un post-mortem, resetea el estado
y activa modo conservador temporal.

Configuración via .env:
  MIN_BALANCE_PCT=20        → trigger cuando balance < 20% del inicial ($200 de $1000)
  EPOCH_CONSERVATIVE_CYCLES=5  → ciclos en modo conservador post-reset
  MAX_CONSECUTIVE_RESETS=3  → pausa automática si hay 3 resets sin ciclos positivos
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "vibe_trading.db",
)

MIN_BALANCE_PCT       = float(os.getenv("MIN_BALANCE_PCT", "20"))
CONSERVATIVE_CYCLES   = int(os.getenv("EPOCH_CONSERVATIVE_CYCLES", "5"))
MAX_CONSECUTIVE_RESETS = int(os.getenv("MAX_CONSECUTIVE_RESETS", "3"))
NORMAL_CONSENSUS      = float(os.getenv("MIN_CONSENSUS_SCORE", "0.62"))
CONSERVATIVE_CONSENSUS = 0.75


def _conn():
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _init_epoch_table():
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS epochs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                start_ts            TEXT NOT NULL,
                end_ts              TEXT,
                start_balance       REAL NOT NULL,
                end_balance         REAL,
                total_cycles        INTEGER DEFAULT 0,
                trigger_reason      TEXT,
                postmortem          TEXT    -- JSON con análisis del fallo
            );
        """)


class EpochManager:
    """
    Gestiona épocas de trading y activa recuperación cuando el balance
    cae por debajo del umbral configurado.
    """

    def __init__(self, initial_balance: float):
        _init_epoch_table()
        self.initial_balance      = initial_balance
        self.min_balance          = initial_balance * (MIN_BALANCE_PCT / 100)
        self._current_epoch       = self._get_or_create_epoch(initial_balance)
        self._conservative_cycles = 0   # ciclos restantes en modo conservador
        self._consecutive_resets  = 0
        self._paused              = False

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def consensus_threshold(self) -> float:
        """Retorna el umbral de consenso activo (normal o conservador)."""
        if self._conservative_cycles > 0:
            return CONSERVATIVE_CONSENSUS
        return NORMAL_CONSENSUS

    @property
    def in_conservative_mode(self) -> bool:
        return self._conservative_cycles > 0

    def tick(self, balance: float, cycle: int, store) -> dict:
        """
        Llamar al final de cada ciclo con el balance actual.
        Retorna dict con estado: {"reset": bool, "paused": bool, "conservative": bool}
        """
        if self._paused:
            return {"reset": False, "paused": True, "conservative": False}

        # Decrementar ciclos conservadores
        if self._conservative_cycles > 0:
            self._conservative_cycles -= 1

        # Verificar drawdown
        if balance <= self.min_balance:
            return self._trigger_recovery(balance, cycle, store)

        # Ciclo positivo → resetear contador de resets consecutivos
        if balance > self.initial_balance:
            self._consecutive_resets = 0

        return {
            "reset": False,
            "paused": False,
            "conservative": self._conservative_cycles > 0,
            "threshold": self.consensus_threshold,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _trigger_recovery(self, balance: float, cycle: int, store) -> dict:
        import json

        self._consecutive_resets += 1
        postmortem = self._generate_postmortem(store, cycle)

        # Cerrar época actual
        with _conn() as con:
            con.execute(
                """UPDATE epochs SET end_ts=?, end_balance=?, total_cycles=?,
                   trigger_reason=?, postmortem=? WHERE id=?""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    balance,
                    cycle,
                    f"drawdown: balance ${balance:.2f} below threshold ${self.min_balance:.2f}",
                    json.dumps(postmortem),
                    self._current_epoch,
                ),
            )

        print(f"\n[EpochManager] ⚠ DRAWDOWN TRIGGER — Balance ${balance:.2f} < ${self.min_balance:.2f}")
        print(f"[EpochManager] Post-mortem: {postmortem.get('summary', '')}")

        try:
            store.log_system_event(
                "EPOCH_RESET", "FUTURES", balance,
                {
                    "trigger": f"balance ${balance:.2f} below threshold ${self.min_balance:.2f}",
                    "consecutive_resets": self._consecutive_resets,
                    "postmortem": postmortem.get("summary", ""),
                },
            )
        except Exception:
            pass

        # Verificar límite de resets consecutivos
        if self._consecutive_resets >= MAX_CONSECUTIVE_RESETS:
            self._paused = True
            print(f"[EpochManager] 🛑 SISTEMA PAUSADO — {MAX_CONSECUTIVE_RESETS} resets consecutivos sin recuperación.")
            print(f"[EpochManager] Revisar configuración antes de continuar.")
            return {"reset": True, "paused": True, "conservative": False, "postmortem": postmortem}

        # Iniciar nueva época
        self._current_epoch = self._get_or_create_epoch(self.initial_balance)
        self._conservative_cycles = CONSERVATIVE_CYCLES
        print(f"[EpochManager] Nueva época iniciada. Modo conservador por {CONSERVATIVE_CYCLES} ciclos (threshold={CONSERVATIVE_CONSENSUS})")

        return {
            "reset": True,
            "paused": False,
            "conservative": True,
            "threshold": CONSERVATIVE_CONSENSUS,
            "postmortem": postmortem,
        }

    def _generate_postmortem(self, store, cycle: int) -> dict:
        """Analiza las últimas decisiones para identificar patrones de fallo."""
        try:
            decisions = store.get_recent_decisions(limit=20)
            if not decisions:
                return {"summary": "Sin datos suficientes para análisis."}

            # Contar decisiones por tipo
            counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
            for d in decisions:
                counts[d["decision"]] = counts.get(d["decision"], 0) + 1

            # Agente más activo en decisiones (parsear JSON de agents)
            import json
            agent_counts: dict = {}
            for d in decisions:
                try:
                    agents = json.loads(d.get("agents", "[]"))
                    for a in agents:
                        agent_counts[a] = agent_counts.get(a, 0) + 1
                except Exception:
                    pass

            top_agent = max(agent_counts, key=agent_counts.get) if agent_counts else "unknown"

            return {
                "summary": (
                    f"Drawdown tras {len(decisions)} ciclos. "
                    f"Distribución: {counts}. "
                    f"Agente más frecuente: {top_agent}."
                ),
                "decision_counts": counts,
                "top_agent": top_agent,
                "total_cycles_analyzed": len(decisions),
            }
        except Exception as e:
            return {"summary": f"Error generando post-mortem: {e}"}

    def get_postmortem_context(self, store) -> str:
        """
        Retorna el post-mortem de la época anterior como string
        para pasar como contexto a los agentes en la nueva época.
        """
        try:
            import json
            with _conn() as con:
                row = con.execute(
                    "SELECT * FROM epochs WHERE end_ts IS NOT NULL ORDER BY id DESC LIMIT 1"
                ).fetchone()
            if not row or not row["postmortem"]:
                return ""
            pm = json.loads(row["postmortem"])
            return (
                f"PREVIOUS EPOCH POSTMORTEM: {pm.get('summary', '')} "
                f"Loss triggered at end_balance=${row['end_balance']:.2f}."
            )
        except Exception:
            return ""

    def _get_or_create_epoch(self, balance: float) -> int:
        with _conn() as con:
            row = con.execute(
                "SELECT id FROM epochs WHERE end_ts IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                return row["id"]
            cur = con.execute(
                "INSERT INTO epochs (start_ts, start_balance) VALUES (?, ?)",
                (datetime.now(timezone.utc).isoformat(), balance),
            )
            return cur.lastrowid
