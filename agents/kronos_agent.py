import asyncio
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent, TradingSignal, AgentVote

# Kronos está en un sub-repo local — añadir al path
_KRONOS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Kronos",
)
if _KRONOS_ROOT not in sys.path:
    sys.path.insert(0, _KRONOS_ROOT)


# Parámetros del modelo
_MODEL_ID      = os.getenv("KRONOS_MODEL",     "NeoQuasar/Kronos-mini")
_TOKENIZER_ID  = os.getenv("KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-2k")
_MAX_CONTEXT   = int(os.getenv("KRONOS_MAX_CONTEXT", "2048"))
_PRED_LEN      = 5          # velas futuras a predecir
_BUY_THRESHOLD  = 0.003     # +0.3 % esperado → BUY
_SELL_THRESHOLD = 0.003     # -0.3 % esperado → SELL


def _load_kronos():
    """Carga pesada — solo se ejecuta una vez, en un thread separado."""
    from model.kronos import Kronos, KronosTokenizer, KronosPredictor  # noqa

    tokenizer = KronosTokenizer.from_pretrained(_TOKENIZER_ID)
    model     = Kronos.from_pretrained(_MODEL_ID)
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=_MAX_CONTEXT)
    return predictor


class KronosAgent(BaseAgent):
    """
    Agente votante basado en el modelo de forecasting Kronos-mini.
    Especialidad: predicción cuantitativa de precio mediante series temporales OHLCV.
    Peso en el Decider: 15%

    Kronos es un transformer decoder-only entrenado sobre 12B+ velas OHLCV
    de 45 exchanges (AAAI 2026). Corre en CPU (~150 ms por inferencia).
    """

    def __init__(self):
        super().__init__("kronos-mini", "ohlcv-forecasting")
        self._predictor = None   # carga lazy en health_check

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """
        Health-check ligero: solo verifica que el módulo Kronos sea importable.
        La carga real del modelo ocurre en el primer analyze() para no bloquear
        el startup (descarga de HuggingFace puede tardar varios minutos).
        """
        try:
            import importlib
            spec = importlib.util.find_spec("model.kronos")
            if spec is None:
                self.log("Módulo model.kronos no encontrado en path.", "ERROR")
                return False
            self.is_ready = True
            self.log("Kronos path OK — modelo se cargará en primer análisis.")
            return True
        except Exception as e:
            self.log(f"Health check error: {e}", "ERROR")
            return False

    async def _ensure_loaded(self):
        """Carga el modelo si todavía no está en memoria."""
        if self._predictor is not None:
            return
        self.log("Cargando Kronos-mini por primera vez (puede tardar ~1-2 min)...")
        self._predictor = await asyncio.to_thread(_load_kronos)
        self.log("Kronos-mini cargado y listo.", "INFO")

    # ── Analysis ──────────────────────────────────────────────────────────────

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        symbol = market_data.get("symbol", "UNKNOWN")
        try:
            await self._ensure_loaded()
        except Exception as e:
            self.log(f"No se pudo cargar el modelo: {e}", "ERROR")
            return TradingSignal(
                pair=symbol,
                vote=AgentVote.HOLD,
                confidence=0.0,
                reasoning=f"Kronos model load failed: {e}",
                agent_id=f"{self.agent_id}({_MODEL_ID})",
            )

        pred_df = await asyncio.to_thread(self._run_inference, market_data)
        return self._derive_signal(symbol, market_data["price"], pred_df)

    # ── Private ───────────────────────────────────────────────────────────────

    def _run_inference(self, market_data: dict) -> pd.DataFrame:
        """
        Construye el DataFrame OHLCV, genera timestamps futuros y llama a
        predictor.predict(). Corre en un thread pool (no bloquea el event loop).
        """
        opens      = market_data["opens"]
        highs      = market_data["highs"]
        lows       = market_data["lows"]
        closes     = market_data["closes"]
        volumes    = market_data["volumes"]
        amounts    = market_data["amounts"]
        ts_ms      = market_data["timestamps"]   # enteros ms

        # DataFrame histórico
        df = pd.DataFrame({
            "open":   opens,
            "high":   highs,
            "low":    lows,
            "close":  closes,
            "volume": volumes,
            "amount": amounts,
        })

        # Timestamps históricos como Series de datetime
        x_timestamp = pd.Series(pd.to_datetime(ts_ms, unit="ms"))

        # Estimar intervalo entre velas (ms → timedelta)
        if len(ts_ms) >= 2:
            interval_ms = int(np.median(np.diff(ts_ms[-10:])))
        else:
            interval_ms = 3_600_000   # fallback 1h

        interval = timedelta(milliseconds=interval_ms)
        last_ts  = pd.Timestamp(ts_ms[-1], unit="ms")

        # Timestamps futuros
        y_timestamp = pd.Series([
            last_ts + interval * (i + 1) for i in range(_PRED_LEN)
        ])

        # Usar solo las últimas max_context velas
        max_rows = _MAX_CONTEXT
        if len(df) > max_rows:
            df           = df.iloc[-max_rows:].reset_index(drop=True)
            x_timestamp  = x_timestamp.iloc[-max_rows:].reset_index(drop=True)

        pred_df = self._predictor.predict(
            df=df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=_PRED_LEN,
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
        return pred_df

    def _derive_signal(
        self,
        symbol: str,
        current_price: float,
        pred_df: pd.DataFrame,
    ) -> TradingSignal:
        """
        Convierte el forecast en BUY / SELL / HOLD + confianza.

        Lógica:
          - predicted_close = media de las últimas 2 velas pronosticadas
          - pct_change = (predicted_close - current) / current
          - |pct_change| > threshold → señal direccional
          - confidence = min(1.0, |pct_change| / threshold) * 0.85
        """
        pred_closes = pred_df["close"].values
        # Usar la última vela pronosticada como objetivo de precio
        predicted_close = float(pred_closes[-1])
        pct_change = (predicted_close - current_price) / (current_price + 1e-9)

        abs_pct = abs(pct_change)
        raw_conf = min(1.0, abs_pct / _BUY_THRESHOLD) * 0.85
        confidence = max(0.30, round(raw_conf, 3))

        if pct_change >= _BUY_THRESHOLD:
            vote = AgentVote.BUY
            reasoning = (
                f"Kronos forecasts +{pct_change*100:.2f}% to ${predicted_close:,.2f} "
                f"over next {_PRED_LEN} candles. Bullish momentum confirmed."
            )
        elif pct_change <= -_SELL_THRESHOLD:
            vote = AgentVote.SELL
            reasoning = (
                f"Kronos forecasts {pct_change*100:.2f}% to ${predicted_close:,.2f} "
                f"over next {_PRED_LEN} candles. Bearish pattern detected."
            )
        else:
            vote = AgentVote.HOLD
            confidence = 0.40
            reasoning = (
                f"Kronos forecasts minimal movement ({pct_change*100:+.2f}%) "
                f"to ${predicted_close:,.2f}. Insufficient directional signal."
            )

        return TradingSignal(
            pair=symbol,
            vote=vote,
            confidence=confidence,
            reasoning=reasoning,
            agent_id=f"{self.agent_id}({_MODEL_ID})",
        )
