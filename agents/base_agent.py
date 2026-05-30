from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class AgentVote(Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradingSignal:
    pair:       str
    vote:       AgentVote
    confidence: float        # 0.0 - 1.0
    reasoning:  str
    agent_id:   str
    timestamp:  str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def fmt_active_position(context: dict) -> str:
    """Devuelve un bloque de texto con la posición activa para incluir en prompts de agentes.
    Retorna string vacío si no hay posición activa."""
    pos = context.get("active_position")
    if not pos:
        return ""
    side_label = "LONG" if pos["side"] in ("BUY", "LONG") else "SHORT"
    pnl      = pos.get("unrealized_pnl", 0.0)
    pnl_pct  = pos.get("pnl_pct", 0.0)
    mark     = pos.get("mark_price", pos["entry_price"])
    sl_dist  = pos.get("distance_to_sl_pct", 0.0)
    tp_dist  = pos.get("distance_to_tp_pct", 0.0)
    open_since = pos.get("open_since", "")[:19] + "Z" if pos.get("open_since") else "unknown"
    return (
        f"\nACTIVE POSITION — {side_label} {pos['symbol']} ×{pos.get('leverage', 1)} leverage:\n"
        f"- Entry: ${pos['entry_price']:,.2f}  |  Mark: ${mark:,.2f}\n"
        f"- Unrealized P&L: {pnl:+.4f} USDT  ({pnl_pct:+.2f}%)\n"
        f"- SL: ${pos['sl_price']:,.2f} ({sl_dist:.2f}% away)  |  TP: ${pos['tp_price']:,.2f} ({tp_dist:.2f}% away)\n"
        f"- Open since: {open_since}\n"
        f"IMPORTANT: A {side_label} is already open. Vote HOLD to keep it running, "
        f"or consider whether technicals justify an early exit signal."
    )


class BaseAgent(ABC):
    def __init__(self, agent_id: str, role: str):
        self.agent_id = agent_id
        self.role     = role
        self.is_ready = False

    @abstractmethod
    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        """Analiza el mercado y devuelve un voto."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifica que el agente está operativo."""
        pass

    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] [{self.agent_id}] {datetime.now(timezone.utc).isoformat()} — {message}")
