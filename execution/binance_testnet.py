import os
import math
from typing import Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv

load_dotenv()


class BinanceTestnetClient:
    """
    Cliente para Binance Testnet.
    Portado y simplificado desde BinanceService.ts del proyecto Trading-Agent.
    Maneja datos de mercado, portfolio, órdenes y precisión de cantidad por par.
    """

    def __init__(self):
        self.client = Client(
            api_key=os.getenv("BINANCE_TESTNET_API_KEY"),
            api_secret=os.getenv("BINANCE_TESTNET_SECRET"),
            testnet=True,
        )
        self._symbol_info_cache: dict = {}

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def get_portfolio_value(self) -> float:
        """
        Retorna el balance de trabajo en USDT.
        Limitado por DEMO_BUDGET_USDT para operar solo con el presupuesto demo
        aunque el testnet tenga más fondos disponibles.
        """
        account = self.client.get_account()
        real_balance = 0.0
        for asset in account["balances"]:
            if asset["asset"] == "USDT":
                real_balance = float(asset["free"])
                break
        demo_budget = float(os.getenv("DEMO_BUDGET_USDT", "1000.0"))
        return min(real_balance, demo_budget)

    def get_all_balances(self) -> dict:
        """Retorna todos los assets con balance > 0."""
        account = self.client.get_account()
        return {
            b["asset"]: {
                "free":   float(b["free"]),
                "locked": float(b["locked"]),
            }
            for b in account["balances"]
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        }

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> float:
        ticker = self.client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])

    def get_market_data(self, symbol: str, interval: str = "1h", limit: int = 50) -> dict:
        """
        Retorna OHLCV + indicadores técnicos calculados para el símbolo.
        Usado por los agentes como input principal.
        """
        klines = self.client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
        )

        opens   = [float(k[1]) for k in klines]
        closes  = [float(k[4]) for k in klines]
        highs   = [float(k[2]) for k in klines]
        lows    = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        amounts = [float(k[7]) for k in klines]          # quote asset volume
        timestamps = [int(k[0]) for k in klines]          # open time ms (for Kronos)
        price   = closes[-1]

        return {
            "symbol":     symbol,
            "price":      price,
            "opens":      opens,
            "closes":     closes,
            "highs":      highs,
            "lows":       lows,
            "volumes":    volumes,
            "amounts":    amounts,
            "timestamps": timestamps,
            "volume":     sum(volumes[-24:]),  # volumen 24h aprox
            "rsi":        self._calc_rsi(closes),
            "macd":       self._calc_macd(closes),
            "bb_upper":   self._calc_bb(closes)[0],
            "bb_lower":   self._calc_bb(closes)[1],
            "ema20":      self._calc_ema(closes, 20),
            "ema50":      self._calc_ema(closes, 50),
        }

    def get_top_volume_pairs(self, universe: list[str]) -> list[str]:
        """
        Filtra el universo de pares por volumen 24h descendente.
        Usado por el scanner para pre-filtrar candidatos.
        """
        tickers = self.client.get_ticker()
        ticker_map = {t["symbol"]: float(t["quoteVolume"]) for t in tickers}
        ranked = sorted(
            [s for s in universe if s in ticker_map],
            key=lambda s: ticker_map[s],
            reverse=True,
        )
        return ranked

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> dict:
        """
        Ejecuta una orden de mercado en testnet.
        side: 'BUY' | 'SELL'
        """
        quantity = self._adjust_quantity(symbol, quantity)
        if quantity <= 0:
            raise ValueError(f"Quantity after adjustment is 0 for {symbol}")

        order = self.client.order_market(
            symbol=symbol,
            side=side,
            quantity=quantity,
        )
        return {
            "order_id":    order["orderId"],
            "symbol":      order["symbol"],
            "side":        order["side"],
            "quantity":    float(order["executedQty"]),
            "price":       float(order["fills"][0]["price"]) if order["fills"] else 0.0,
            "status":      order["status"],
        }

    def place_stop_loss(self, symbol: str, side: str, quantity: float, stop_price: float) -> dict:
        """Coloca una orden stop-loss."""
        quantity    = self._adjust_quantity(symbol, quantity)
        stop_price  = self._round_price(symbol, stop_price)
        order_side  = "SELL" if side == "BUY" else "BUY"

        order = self.client.create_order(
            symbol=symbol,
            side=order_side,
            type=Client.ORDER_TYPE_STOP_LOSS_LIMIT,
            timeInForce=Client.TIME_IN_FORCE_GTC,
            quantity=quantity,
            stopPrice=stop_price,
            price=stop_price,
        )
        return {"order_id": order["orderId"], "stop_price": stop_price}

    def place_take_profit(self, symbol: str, side: str, quantity: float, tp_price: float) -> dict:
        """Coloca una orden take-profit."""
        quantity = self._adjust_quantity(symbol, quantity)
        tp_price = self._round_price(symbol, tp_price)
        order_side = "SELL" if side == "BUY" else "BUY"

        order = self.client.create_order(
            symbol=symbol,
            side=order_side,
            type=Client.ORDER_TYPE_TAKE_PROFIT_LIMIT,
            timeInForce=Client.TIME_IN_FORCE_GTC,
            quantity=quantity,
            stopPrice=tp_price,
            price=tp_price,
        )
        return {"order_id": order["orderId"], "tp_price": tp_price}

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        try:
            self.client.cancel_order(symbol=symbol, orderId=order_id)
            return True
        except BinanceAPIException:
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        return self.client.get_open_orders(symbol=symbol) if symbol else self.client.get_open_orders()

    def get_recent_filled_orders(self, symbol: str, limit: int = 20) -> list[dict]:
        """
        Retorna órdenes FILLED recientes para el símbolo.
        Usado para detectar si un SL o TP fue ejecutado entre ciclos.
        """
        try:
            orders = self.client.get_all_orders(symbol=symbol, limit=limit)
            return [
                {
                    "order_id":   o["orderId"],
                    "side":       o["side"],
                    "type":       o["type"],
                    "status":     o["status"],
                    "price":      float(o["price"]) or float(o.get("stopPrice", 0)),
                    "qty":        float(o["executedQty"]),
                    "time":       o["time"],
                }
                for o in orders
                if o["status"] == "FILLED"
            ]
        except BinanceAPIException:
            return []

    # ── Precision helpers ─────────────────────────────────────────────────────

    def _get_symbol_info(self, symbol: str) -> dict:
        if symbol not in self._symbol_info_cache:
            info = self.client.get_symbol_info(symbol)
            self._symbol_info_cache[symbol] = info
        return self._symbol_info_cache[symbol]

    def _get_step_size(self, symbol: str) -> float:
        info = self._get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                return float(f["stepSize"])
        return 0.00001

    def _get_tick_size(self, symbol: str) -> float:
        info = self._get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "PRICE_FILTER":
                return float(f["tickSize"])
        return 0.01

    def _adjust_quantity(self, symbol: str, quantity: float) -> float:
        step = self._get_step_size(symbol)
        precision = int(round(-math.log10(step)))
        return round(math.floor(quantity / step) * step, precision)

    def _round_price(self, symbol: str, price: float) -> float:
        tick = self._get_tick_size(symbol)
        precision = int(round(-math.log10(tick)))
        return round(round(price / tick) * tick, precision)

    # ── Technical Indicators ──────────────────────────────────────────────────

    def _calc_rsi(self, closes: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains  = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _calc_ema(self, closes: list, period: int) -> float:
        if len(closes) < period:
            return closes[-1]
        k = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return round(ema, 2)

    def _calc_macd(self, closes: list) -> float:
        if len(closes) < 26:
            return 0.0
        ema12 = self._calc_ema(closes, 12)
        ema26 = self._calc_ema(closes, 26)
        return round(ema12 - ema26, 4)

    def _calc_bb(self, closes: list, period: int = 20, std_dev: float = 2.0) -> tuple:
        if len(closes) < period:
            return closes[-1] * 1.02, closes[-1] * 0.98
        window = closes[-period:]
        mean   = sum(window) / period
        std    = (sum((x - mean) ** 2 for x in window) / period) ** 0.5
        return round(mean + std_dev * std, 2), round(mean - std_dev * std, 2)
