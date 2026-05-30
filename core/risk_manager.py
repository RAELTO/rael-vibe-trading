import os
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderRequest:
    symbol:     str
    side:       str          # "BUY" | "SELL"
    quantity:   float
    price:      float
    confidence: float
    stop_loss_pct:   float = 0.025   # 2.5% stop loss por defecto
    take_profit_pct: float = 0.04    # 4.0% take profit por defecto


@dataclass
class RiskState:
    portfolio_balance:  float = 0.0
    daily_loss:         float = 0.0
    daily_loss_date:    str   = field(default_factory=lambda: date.today().isoformat())
    open_positions:     int   = 0
    total_trades_today: int   = 0


class RiskManager:
    """
    Valida órdenes antes de enviarlas al Executor.
    Referencia: TradingEngine.ts del proyecto Trading-Agent (portado a Python).
    """

    def __init__(self):
        self.max_position_pct  = float(os.getenv("MAX_POSITION_SIZE_PERCENT", "2.0")) / 100
        self.max_daily_loss_pct = float(os.getenv("MAX_DAILY_LOSS_PERCENT", "5.0")) / 100
        self.min_consensus     = float(os.getenv("MIN_CONSENSUS_SCORE", "0.65"))
        self.demo_budget       = float(os.getenv("TRADING_BUDGET_USDT", "1000.0"))  # presupuesto operativo
        self.max_open_positions = 3
        self.state = RiskState(portfolio_balance=self.demo_budget)

    # ── Estado ────────────────────────────────────────────────────────────────

    def update_balance(self, balance: float):
        self.state.portfolio_balance = balance

    def record_pnl(self, pnl: float):
        """Registra P&L realizado de una orden cerrada."""
        today = date.today().isoformat()
        if self.state.daily_loss_date != today:
            self.state.daily_loss = 0.0
            self.state.daily_loss_date = today
        if pnl < 0:
            self.state.daily_loss += abs(pnl)

    def open_position(self):
        self.state.open_positions += 1
        self.state.total_trades_today += 1

    def close_position(self, pnl: float):
        self.state.open_positions = max(0, self.state.open_positions - 1)
        self.record_pnl(pnl)

    # ── Validación ────────────────────────────────────────────────────────────

    def validate_order(self, order: OrderRequest) -> tuple[bool, str]:
        """
        Retorna (aprobado: bool, motivo: str).
        Bloquea la orden si alguna validación falla.
        """
        balance = self.state.portfolio_balance

        # 1. Confianza mínima
        if order.confidence < self.min_consensus:
            return False, f"Confidence {order.confidence:.2f} below minimum {self.min_consensus:.2f}"

        # 2. Pérdida diaria máxima
        max_daily_loss = balance * self.max_daily_loss_pct
        if self.state.daily_loss >= max_daily_loss:
            return False, f"Daily loss limit reached: ${self.state.daily_loss:.2f} >= ${max_daily_loss:.2f}"

        # 3. Tamaño máximo de posición
        order_value = order.quantity * order.price
        max_position_value = balance * self.max_position_pct
        if order_value > max_position_value:
            return False, f"Position size ${order_value:.2f} exceeds max ${max_position_value:.2f} ({self.max_position_pct*100:.1f}% of balance)"

        # 4. Posiciones abiertas máximas
        if self.state.open_positions >= self.max_open_positions:
            return False, f"Max open positions reached: {self.state.open_positions}/{self.max_open_positions}"

        # 5. Balance suficiente
        if order_value > balance * 0.95:
            return False, f"Insufficient balance: order ${order_value:.2f} vs balance ${balance:.2f}"

        # 6. Cantidad mínima
        if order.quantity <= 0:
            return False, "Order quantity must be > 0"

        return True, "OK"

    def calculate_quantity(self, symbol: str, price: float) -> float:
        """
        Calcula la cantidad de la orden basada en el porcentaje máximo de posición.
        """
        position_value = self.state.portfolio_balance * self.max_position_pct
        quantity = position_value / price
        return round(quantity, 6)

    def calculate_stop_loss(self, side: str, price: float, pct: float = 0.025) -> float:
        if side in ("BUY", "LONG"):
            return round(price * (1 - pct), 2)
        return round(price * (1 + pct), 2)

    def calculate_take_profit(self, side: str, price: float, pct: float = 0.04) -> float:
        if side in ("BUY", "LONG"):
            return round(price * (1 + pct), 2)
        return round(price * (1 - pct), 2)

    # ── Futures-specific ──────────────────────────────────────────────────────

    def validate_futures_order(
        self,
        order: "OrderRequest",
        leverage: int,
        liquidation_price: float,
    ) -> tuple[bool, str]:
        """
        Validaciones adicionales para futures:
        - Daily loss limit más estricto (3% vs 5% spot)
        - Max 1 posición abierta en futures
        - Liquidation price debe estar al menos 2× más lejos que el SL
        """
        balance = self.state.portfolio_balance

        # Confianza mínima
        if order.confidence < self.min_consensus:
            return False, f"Confidence {order.confidence:.2f} below minimum {self.min_consensus:.2f}"

        # Pérdida diaria máxima (3% en futures)
        futures_loss_limit = balance * 0.03
        if self.state.daily_loss >= futures_loss_limit:
            return False, f"Futures daily loss limit reached: ${self.state.daily_loss:.2f} >= ${futures_loss_limit:.2f}"

        # Solo 1 posición abierta en futures
        if self.state.open_positions >= 1:
            return False, f"Max 1 futures position allowed (currently {self.state.open_positions} open)"

        # Margen suficiente
        margin_required = (order.quantity * order.price) / leverage
        if margin_required > balance * self.max_position_pct:
            return False, f"Margin ${margin_required:.2f} exceeds max ${balance * self.max_position_pct:.2f}"

        # Liquidation price debe estar más lejos que 2× el SL
        sl_distance = order.price * order.stop_loss_pct   # distancia en $ al stop-loss
        liq_distance = abs(order.price - liquidation_price)
        if liq_distance < sl_distance * 2:
            return False, (
                f"Liquidation too close: liq=${liquidation_price:,.0f} "
                f"({liq_distance:.0f} away) vs SL distance {sl_distance:.0f}×2"
            )

        return True, "OK"

    def calculate_futures_quantity(self, price: float, leverage: int) -> float:
        """Cantidad BTC a abrir basada en el margen disponible × leverage."""
        margin = self.state.portfolio_balance * self.max_position_pct
        position_value = margin * leverage
        return round(position_value / price, 6)

    def get_health(self) -> dict:
        balance = self.state.portfolio_balance
        daily_loss_pct = (self.state.daily_loss / balance * 100) if balance > 0 else 0

        if daily_loss_pct >= self.max_daily_loss_pct * 100:
            status = "CRITICAL"
        elif daily_loss_pct >= self.max_daily_loss_pct * 100 * 0.75:
            status = "HIGH_RISK"
        elif daily_loss_pct >= self.max_daily_loss_pct * 100 * 0.50:
            status = "MODERATE"
        else:
            status = "HEALTHY"

        return {
            "status":           status,
            "balance":          balance,
            "daily_loss":       self.state.daily_loss,
            "daily_loss_pct":   round(daily_loss_pct, 2),
            "open_positions":   self.state.open_positions,
            "trades_today":     self.state.total_trades_today,
        }
