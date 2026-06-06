"""
execution/binance_futures.py — Cliente Binance Futures Demo
==============================================================
Modo por defecto del sistema. Soporta LONG y SHORT con leverage configurable.
Endpoint: demo-fapi.binance.com (demo trading con claves de demo.binance.com)

Notas de API (post dic-2025):
  - SL/TP usan POST /fapi/v1/algoOrder con algoType=CONDITIONAL (STOP_MARKET/
    TAKE_PROFIT_MARKET en /fapi/v1/order fueron eliminados, error -4120)
  - El parámetro es triggerPrice (no stopPrice)
  - La respuesta devuelve algoId (no orderId)
  - Funding rate pagado cada 8h
  - Liquidation price calculado antes de aprobar la orden
"""

import hashlib
import hmac
import math
import os
import time
from typing import Optional

import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv

load_dotenv()

DEFAULT_LEVERAGE = int(os.getenv("FUTURES_LEVERAGE", "3"))
DEMO_BUDGET      = float(os.getenv("DEMO_BUDGET_USDT", "1000.0"))
# Maintenance margin rate BTC/USDT perpetual (Binance tier 1)
MAINTENANCE_MARGIN_RATE = 0.004


class BinanceFuturesClient:
    """
    Cliente para Binance Futures Testnet (USDT-M perpetual).
    LONG  = apuesta a que el precio sube
    SHORT = apuesta a que el precio baja
    """

    # URL base del demo de Binance Futures (post-migración dic-2025)
    DEMO_FAPI_URL = "https://demo-fapi.binance.com"

    def __init__(self):
        api_key    = os.getenv("BINANCE_FUTURES_API_KEY", os.getenv("BINANCE_TESTNET_API_KEY"))
        api_secret = os.getenv("BINANCE_FUTURES_SECRET",  os.getenv("BINANCE_TESTNET_SECRET"))
        # python-binance hace ping al endpoint spot durante __init__ por defecto.
        # En algunos VPS ese endpoint esta bloqueado aunque Futures Testnet funcione.
        self.client = Client(api_key=api_key, api_secret=api_secret, testnet=True, ping=False)
        self._api_key    = api_key
        self._api_secret = api_secret
        self._leverage_cache: dict[str, int] = {}
        self._symbol_info_cache: dict = {}

    # ── Balance ───────────────────────────────────────────────────────────────

    def get_futures_balance(self) -> float:
        """Balance USDT real del wallet futures (sin cap artificial)."""
        try:
            balances = self.client.futures_account_balance()
            for b in balances:
                if b["asset"] == "USDT":
                    return float(b["balance"])
        except BinanceAPIException as e:
            print(f"[Futures] Error obteniendo balance: {e}")
        return 0.0

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_market_data(self, symbol: str, interval: str = "1h", limit: int = 50) -> dict:
        """
        OHLCV + indicadores técnicos + datos exclusivos de futures:
        funding_rate, open_interest, long_short_ratio.
        """
        klines = self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)

        opens      = [float(k[1]) for k in klines]
        closes     = [float(k[4]) for k in klines]
        highs      = [float(k[2]) for k in klines]
        lows       = [float(k[3]) for k in klines]
        volumes    = [float(k[5]) for k in klines]
        amounts    = [float(k[7]) for k in klines]
        timestamps = [int(k[0]) for k in klines]
        price      = closes[-1]

        # Datos exclusivos de futures
        funding_rate      = 0.0
        open_interest     = 0.0
        long_short_ratio  = 1.0
        high_24h          = max(highs) if highs else 0.0
        low_24h           = min(lows)  if lows  else 0.0
        change_24h_pct    = 0.0
        basis_pct         = 0.0
        index_price       = price

        try:
            mark = self.client.futures_mark_price(symbol=symbol)
            funding_rate = float(mark["lastFundingRate"])
            index_price  = float(mark.get("indexPrice", price))
            basis_pct    = round((price - index_price) / index_price * 100, 4) if index_price > 0 else 0.0
        except Exception:
            pass

        try:
            ticker = self.client.futures_ticker(symbol=symbol)
            high_24h       = float(ticker.get("highPrice", high_24h))
            low_24h        = float(ticker.get("lowPrice", low_24h))
            change_24h_pct = float(ticker.get("priceChangePercent", 0.0))
        except Exception:
            pass

        try:
            oi = self.client.futures_open_interest(symbol=symbol)
            open_interest = float(oi["openInterest"])
        except Exception:
            pass

        try:
            ratio_data = self.client.futures_global_longshort_ratio(symbol=symbol, period="1h", limit=1)
            if ratio_data:
                long_short_ratio = float(ratio_data[0]["longShortRatio"])
        except Exception:
            pass

        return {
            "symbol":              symbol,
            "price":               price,
            "opens":               opens,
            "closes":              closes,
            "highs":               highs,
            "lows":                lows,
            "volumes":             volumes,
            "amounts":             amounts,
            "timestamps":          timestamps,
            "volume":              sum(volumes[-24:]),
            "rsi":                 self._calc_rsi(closes),
            "macd":                self._calc_macd(closes),
            "bb_upper":            self._calc_bb(closes)[0],
            "bb_lower":            self._calc_bb(closes)[1],
            "ema20":               self._calc_ema(closes, 20),
            "ema50":               self._calc_ema(closes, 50),
            # Futures-specific
            "funding_rate":        round(funding_rate * 100, 4),
            "funding_annualized":  round(funding_rate * 3 * 365 * 100, 1),
            "open_interest":       round(open_interest, 2),
            "long_short_ratio":    round(long_short_ratio, 3),
            "leverage":            self._leverage_cache.get(symbol, DEFAULT_LEVERAGE),
            # 24h stats + basis
            "high_24h":            round(high_24h, 2),
            "low_24h":             round(low_24h, 2),
            "change_24h_pct":      round(change_24h_pct, 3),
            "basis_pct":           basis_pct,
            "index_price":         round(index_price, 2),
        }

    # ── Leverage ──────────────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        if self._leverage_cache.get(symbol) == leverage:
            return True
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            self._leverage_cache[symbol] = leverage
            return True
        except BinanceAPIException as e:
            print(f"[Futures] Error setting leverage: {e}")
            return False

    # ── Órdenes ───────────────────────────────────────────────────────────────

    def open_position(
        self, symbol: str, side: str, quantity: float, leverage: int = DEFAULT_LEVERAGE
    ) -> dict:
        """
        Abre una posición LONG o SHORT a mercado.
        side: 'LONG' | 'SHORT'
        """
        self.set_leverage(symbol, leverage)
        order_side = "BUY" if side == "LONG" else "SELL"
        quantity   = self._adjust_quantity(symbol, quantity)

        if quantity <= 0:
            raise ValueError(f"Quantity after adjustment is 0 for {symbol}")

        order = self.client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type="MARKET",
            quantity=quantity,
        )

        fill_price = float(order.get("avgPrice", 0))
        if fill_price == 0:
            try:
                mark = self.client.futures_mark_price(symbol=symbol)
                fill_price = float(mark["markPrice"])
            except Exception:
                pass

        return {
            "order_id": order["orderId"],
            "symbol":   symbol,
            "side":     side,
            "quantity": float(order["executedQty"]),
            "price":    fill_price,
            "leverage": leverage,
            "status":   order["status"],
        }

    def close_position_market(self, symbol: str, side: str, quantity: float) -> dict:
        """Cierra una posición con orden de mercado (override de SL/TP)."""
        close_side = "SELL" if side == "LONG" else "BUY"
        quantity   = self._adjust_quantity(symbol, quantity)
        order = self.client.futures_create_order(
            symbol=symbol,
            side=close_side,
            type="MARKET",
            quantity=quantity,
            reduceOnly=True,
        )
        return {"order_id": order["orderId"], "status": order["status"]}

    def place_stop_loss(self, symbol: str, position_side: str, stop_price: float) -> dict:
        """Coloca el stop-loss de cierre. Ver _place_protective."""
        side = "SELL" if position_side == "LONG" else "BUY"
        stop_price = self._round_price(symbol, stop_price)
        return self._place_protective(symbol, side, "STOP_MARKET", stop_price, "SL")

    def place_take_profit(self, symbol: str, position_side: str, tp_price: float) -> dict:
        """Coloca el take-profit de cierre. Ver _place_protective."""
        side = "SELL" if position_side == "LONG" else "BUY"
        tp_price = self._round_price(symbol, tp_price)
        return self._place_protective(symbol, side, "TAKE_PROFIT_MARKET", tp_price, "TP")

    def _place_protective(
        self, symbol: str, side: str, order_type: str, trigger_price: float, kind: str,
    ) -> dict:
        """
        Coloca una orden condicional de cierre (SL/TP) en EL MISMO entorno donde vive la
        posición — el cliente testnet firmado (testnet.binancefuture.com) — y NO en
        demo-fapi.binance.com, que está geo-bloqueado desde el VPS:
            "Service unavailable from a restricted location according to 'b. Eligibility'".

        Cascada; devuelve el primer método que Binance acepte (con su `order_id`):
          1. STOP_MARKET / TAKE_PROFIT_MARKET con closePosition=true por el cliente testnet.
             Es la forma canónica en modo one-way (open_position no usa positionSide) y va
             por un host que NO aplica el chequeo de elegibilidad → es la ruta preferida.
          2. Algo condicional en demo-fapi como último recurso (funciona desde ubicaciones
             no restringidas; desde un VPS bloqueado fallará y se cae al return {}).

        Devuelve {} solo si TODO falla. En ese caso la única protección es la red del
        PositionMonitor (_enforce_tp_sl) y el orquestador lo avisa al dashboard.
        """
        # Método 1 — orden condicional nativa por el cliente testnet (no geo-bloqueado).
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type=order_type,
                stopPrice=trigger_price,
                closePosition=True,
                workingType="MARK_PRICE",
            )
            oid = order.get("orderId")
            if not oid:
                # CONFIRMADO en prod: la orden de cierre con closePosition SÍ se coloca en el
                # exchange (Open Orders la muestra) pero la respuesta a veces vuelve sin
                # orderId. Lo recuperamos consultando las órdenes abiertas para (a) no caer al
                # fallback geo-bloqueado y (b) no dejar el order_id en None (rompe el trailing).
                print(f"[Futures] {kind} {order_type} (cliente testnet) sin orderId en respuesta: {order!r} — recuperando del exchange", flush=True)
                oid = self._find_protective_order_id(symbol, side, order_type)
            if oid:
                return {"order_id": oid, "trigger_price": trigger_price, "kind": "order"}
        except Exception as e:
            print(f"[Futures] {kind} {order_type} (cliente testnet) rechazado: {type(e).__name__}: {e}", flush=True)

        # Método 2 — Algo condicional en demo-fapi (fallback; geo-bloqueado en este VPS).
        try:
            data = self._place_algo_order(symbol, side, order_type, trigger_price)
            algo_id = data.get("algoId") or (data.get("data") or {}).get("algoId")
            if algo_id:
                return {"order_id": algo_id, "trigger_price": trigger_price, "kind": "algo"}
        except Exception as e:
            print(f"[Futures] {kind} algo (demo-fapi) rechazado: {e}", flush=True)

        return {}

    def get_open_orders(self, symbol: str) -> list:
        """
        Órdenes abiertas del símbolo — incluye las condicionales de cierre
        (STOP_MARKET / TAKE_PROFIT_MARKET). Fuente de verdad para verificar si el
        SL/TP quedó realmente colocado, independientemente del valor de retorno de
        _place_protective.
        """
        try:
            return self.client.futures_get_open_orders(symbol=symbol) or []
        except Exception as e:
            print(f"[Futures] get_open_orders error: {e}", flush=True)
            return []

    def _find_protective_order_id(self, symbol: str, side: str, order_type: str):
        """
        Recupera el orderId de una condicional de cierre recién colocada cuando
        futures_create_order no lo devolvió. STOP_MARKET vs TAKE_PROFIT_MARKET
        distingue SL de TP; el lado (BUY para short, SELL para long) coincide en ambos.
        """
        for o in self.get_open_orders(symbol):
            if o.get("type") == order_type and o.get("side") == side:
                return o.get("orderId")
        return None

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """
        Cancela una orden de cierre (SL/TP) por id — usado por el trailing stop.
        Soporta ambas vías de _place_protective: primero intenta como orden condicional
        regular (futures_cancel_order) y, si no, como orden algo (futures_cancel_algo_order).
        """
        if order_id is None:
            return False
        try:
            self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
            return True
        except Exception:
            pass
        try:
            self.client.futures_cancel_algo_order(algoId=order_id)
            return True
        except Exception as e:
            print(f"[Futures] cancel_order error: {e}")
            return False

    def cancel_all_orders(self, symbol: str):
        """Cancela todas las órdenes abiertas (regulares + algo) del símbolo."""
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
        except BinanceAPIException:
            pass
        try:
            self.client.futures_cancel_all_algo_open_orders(symbol=symbol)
        except BinanceAPIException:
            pass

    def _place_algo_order(
        self, symbol: str, side: str, order_type: str, trigger_price: float,
        close_position: bool = True,
    ) -> dict:
        """
        Firma y envía POST /fapi/v1/algoOrder directamente a demo-fapi.binance.com.
        Usado para SL y TP (algoType=CONDITIONAL) desde dic-2025.
        triggerPrice reemplaza stopPrice de la API anterior.
        """
        params: dict = {
            "symbol":        symbol,
            "side":          side,
            "algoType":      "CONDITIONAL",
            "type":          order_type,
            "triggerPrice":  str(trigger_price),
            "closePosition": "true" if close_position else "false",
            "timestamp":     str(int(time.time() * 1000)),
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature

        resp = requests.post(
            f"{self.DEMO_FAPI_URL}/fapi/v1/algoOrder",
            data=params,
            headers={"X-MBX-APIKEY": self._api_key},
            timeout=10,
        )
        data = resp.json()
        if resp.status_code != 200 or data.get("code", 200) not in (200, 0):
            raise Exception(f"Algo order rejected: {data}")
        return data

    # ── Posición activa ───────────────────────────────────────────────────────

    def get_position(self, symbol: str) -> Optional[dict]:
        """
        Retorna la posición abierta actual para el símbolo, o None si no hay.
        Incluye precio de liquidación calculado por Binance.
        """
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for p in positions:
                qty = float(p["positionAmt"])
                if abs(qty) > 0:
                    leverage = self._leverage_cache.get(symbol, DEFAULT_LEVERAGE)
                    side = "LONG" if qty > 0 else "SHORT"
                    # Liquidación real de Binance (refleja el modo de margen activo:
                    # en cross usa todo el balance, así que queda muy lejos). Si Binance
                    # devuelve 0, caemos a la estimación isolated como respaldo.
                    liq_real = float(p.get("liquidationPrice", 0) or 0)
                    liq = liq_real if liq_real > 0 else self.calculate_liquidation_price(
                        side, float(p["entryPrice"]), leverage
                    )
                    return {
                        "symbol":            p["symbol"],
                        "side":              side,
                        "quantity":          abs(qty),
                        "entry_price":       float(p["entryPrice"]),
                        "unrealized_pnl":    float(p["unRealizedProfit"]),
                        "liquidation_price": liq,
                        "leverage":          leverage,
                        "mark_price":        float(p.get("markPrice", 0)),
                    }
        except BinanceAPIException:
            pass
        return None

    def get_mark_price(self, symbol: str) -> float:
        """Mark price actual del símbolo (0.0 si la consulta falla)."""
        try:
            data = self.client.futures_mark_price(symbol=symbol)
            return float(data["markPrice"])
        except Exception:
            return 0.0

    def get_recent_filled_orders(self, symbol: str, limit: int = 30) -> list[dict]:
        """Órdenes FILLED recientes — para detectar SL/TP ejecutados entre ciclos."""
        try:
            orders = self.client.futures_get_all_orders(symbol=symbol, limit=limit)
            return [
                {
                    "order_id": o["orderId"],
                    "side":     o["side"],
                    "type":     o["type"],
                    "status":   o["status"],
                    "price":    float(o["avgPrice"]) or float(o.get("stopPrice", 0)),
                    "qty":      float(o["executedQty"]),
                    "time":     o["time"],
                }
                for o in orders
                if o["status"] == "FILLED"
            ]
        except BinanceAPIException:
            return []

    # ── Cálculos de riesgo ────────────────────────────────────────────────────

    def calculate_liquidation_price(
        self, side: str, entry_price: float, leverage: int
    ) -> float:
        """
        Estimación de liquidación para margen AISLADO (isolated) al leverage dado.
        Es una cota conservadora (más cercana que la liquidación real en cross, donde
        todo el balance respalda la posición). Se usa para la validación de riesgo y
        como respaldo si Binance no devuelve liquidationPrice.
        LONG:  entry × (1 - 1/leverage + MMR)
        SHORT: entry × (1 + 1/leverage - MMR)
        """
        if side == "LONG":
            return round(entry_price * (1 - 1 / leverage + MAINTENANCE_MARGIN_RATE), 2)
        return round(entry_price * (1 + 1 / leverage - MAINTENANCE_MARGIN_RATE), 2)

    def calculate_margin(self, price: float, quantity: float, leverage: int) -> float:
        """Margen requerido para abrir la posición."""
        return round((price * quantity) / leverage, 4)

    def calculate_quantity_from_margin(
        self, margin_usdt: float, price: float, leverage: int
    ) -> float:
        """Calcula cuánto BTC abrir dado un margen en USDT."""
        position_value = margin_usdt * leverage
        return round(position_value / price, 6)

    def calculate_sl(self, side: str, price: float, pct: float = 0.015) -> float:
        """SL más ajustado para futures (default 1.5% vs 2.5% en spot)."""
        if side == "LONG":
            return self._round_price("BTCUSDT", price * (1 - pct))
        return self._round_price("BTCUSDT", price * (1 + pct))

    def calculate_tp(self, side: str, price: float, pct: float = 0.025) -> float:
        """TP ajustado para futures (default 2.5% vs 4% en spot)."""
        if side == "LONG":
            return self._round_price("BTCUSDT", price * (1 + pct))
        return self._round_price("BTCUSDT", price * (1 - pct))

    def calculate_adaptive_tp(
        self, side: str, price: float, market_data: dict,
        min_pct: float = 0.015, max_pct: float = 0.04, fixed_pct: float = 0.025,
    ) -> float:
        """
        TP adaptativo: en vez de un 2.5% ciego, apunta al soporte/resistencia más cercano
        (banda de Bollinger) acotando el recorrido a [min_pct, max_pct].
          - LONG  -> objetivo = banda superior (resistencia)
          - SHORT -> objetivo = banda inferior (soporte)
        Si entras pegado a la banda, el recorrido real es ínfimo: se acota al piso (min_pct)
        y el gate de reward:risk del RiskManager bloquea el trade por falta de espacio.
        Si no hay banda válida, cae al fixed_pct (2.5%).
        """
        band = market_data.get("bb_upper") if side == "LONG" else market_data.get("bb_lower")
        if not band or band <= 0:
            return self.calculate_tp(side, price, fixed_pct)

        # Recorrido implícito hasta la banda en la dirección del beneficio.
        reward_pct = (band - price) / price if side == "LONG" else (price - band) / price
        if reward_pct <= 0:            # banda del lado equivocado (precio ya la cruzó) -> usar fijo
            reward_pct = fixed_pct
        reward_pct = max(min_pct, min(max_pct, reward_pct))

        if side == "LONG":
            return self._round_price("BTCUSDT", price * (1 + reward_pct))
        return self._round_price("BTCUSDT", price * (1 - reward_pct))

    # ── Precision helpers ─────────────────────────────────────────────────────

    def _get_symbol_info(self, symbol: str) -> dict:
        if symbol not in self._symbol_info_cache:
            exchange = self.client.futures_exchange_info()
            for s in exchange.get("symbols", []):
                if s["symbol"] == symbol:
                    self._symbol_info_cache[symbol] = s
                    break
        return self._symbol_info_cache.get(symbol, {})

    def _get_step_size(self, symbol: str) -> float:
        try:
            info = self._get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    return float(f["stepSize"])
        except Exception:
            pass
        return 0.001  # BTC default

    def _adjust_quantity(self, symbol: str, quantity: float) -> float:
        step = self._get_step_size(symbol)
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(quantity / step) * step, precision)

    def _round_price(self, symbol: str, price: float) -> float:
        # BTC futures tick size = 0.1 USDT
        return round(round(price / 0.1) * 0.1, 1)

    # ── Indicadores técnicos (idénticos al spot) ──────────────────────────────

    def _calc_rsi(self, closes: list, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains  = [max(d, 0)   for d in deltas[-period:]]
        losses = [abs(min(d, 0)) for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

    def _calc_ema(self, closes: list, period: int) -> float:
        if len(closes) < period:
            return closes[-1] if closes else 0.0
        k   = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = price * k + ema * (1 - k)
        return round(ema, 2)

    def _calc_macd(self, closes: list) -> float:
        if len(closes) < 26:
            return 0.0
        return round(self._calc_ema(closes, 12) - self._calc_ema(closes, 26), 4)

    def _calc_bb(self, closes: list, period: int = 20, std_dev: float = 2.0) -> tuple:
        if len(closes) < period:
            p = closes[-1] if closes else 0
            return p * 1.02, p * 0.98
        window   = closes[-period:]
        mean     = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        std      = variance ** 0.5
        return round(mean + std_dev * std, 2), round(mean - std_dev * std, 2)
