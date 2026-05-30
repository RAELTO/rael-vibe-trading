import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent, TradingSignal, AgentVote, fmt_active_position


# Modelos con free tier activo en DashScope (1M tokens cada uno)
# Orden de preferencia: mejor benchmark primero
FREE_TIER_MODELS = [
    "qwen3-235b-a22b",      # 235B params — mejor razonamiento, ~40 días free
    "qwen-plus",            # fallback confiable — meses de uso free
    "qwen3.6-plus",         # alternativa si los anteriores se agotan
]


class QwenAPIAgent(BaseAgent):
    """
    Agente votante usando Qwen3-235b vía DashScope API (compatible con OpenAI).
    Free tier: 1M tokens por modelo — rota automáticamente al siguiente cuando se agota.
    Especialidad: razonamiento matemático avanzado, análisis cuantitativo.
    Peso en el Decider: 20%
    """

    def __init__(self):
        super().__init__("qwen-api", "advanced-quant-reasoning")
        self.client = OpenAI(
            api_key=os.getenv("QWEN_API_KEY"),
            base_url=os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        )
        self.model         = os.getenv("QWEN_MODEL", FREE_TIER_MODELS[0])
        self.model_fallback = os.getenv("QWEN_MODEL_FALLBACK", FREE_TIER_MODELS[1])
        self._current_model = self.model

    async def health_check(self) -> bool:
        try:
            self.client.chat.completions.create(
                model=self._current_model,
                max_tokens=5,
                extra_body={"enable_thinking": False},
                messages=[{"role": "user", "content": "ping"}],
            )
            self.is_ready = True
            return True
        except Exception as e:
            # Si falla por quota agotada, intenta el fallback
            if "quota" in str(e).lower() or "insufficient" in str(e).lower():
                self.log(f"Free tier exhausted for {self._current_model}, trying fallback", "WARN")
                self._current_model = self.model_fallback
                try:
                    self.client.chat.completions.create(
                        model=self._current_model,
                        max_tokens=5,
                        extra_body={"enable_thinking": False},
                        messages=[{"role": "user", "content": "ping"}],
                    )
                    self.is_ready = True
                    return True
                except Exception as e2:
                    self.log(f"Fallback also failed: {e2}", "ERROR")
                    return False
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        system_prompt = (
            "You are a quantitative derivatives analyst specializing in crypto perpetual futures. "
            "BUY = open LONG position. SELL = open SHORT position. HOLD = stay flat. "
            "Your edge is mathematical precision and systematic signal interpretation. "
            "Futures carry math: funding_rate * leverage * 3 = daily % cost if against your position. "
            "Signal framework: "
            "(1) Funding > +0.05%/8h: carry cost penalizes longs heavily — SHORT edge. "
            "(2) Funding < -0.05%/8h: carry cost penalizes shorts — LONG edge. "
            "(3) OI rising + price rising = trend confirmed, follow it. "
            "(4) OI rising + price falling = bearish accumulation — SHORT. "
            "(5) RSI > 72 + negative MACD momentum = exhaustion SHORT setup. "
            "(6) RSI < 28 + positive MACD = oversold LONG setup. "
            "(7) L/S ratio extremes (>1.5 or <0.7) = positioning imbalance, fade the crowd. "
            "Assign confidence proportional to signal confluence count (1 signal=0.55, 3+=0.80). "
            "Respond ONLY with valid JSON."
        )

        news_block = ""
        if context.get("news_sentiment") is not None:
            news_block = f"""
News context:
- Sentiment: {context.get('news_sentiment', 0.0):+.2f}
- Impact: {context.get('news_impact', 'LOW')}
- Key events: {', '.join(context.get('key_events', [])) or 'none'}
- Bias: {context.get('news_bias', 'HOLD')}"""

        futures_block = ""
        if context.get("is_futures"):
            funding  = market_data.get('funding_rate', 0.0)
            ls_ratio = market_data.get('long_short_ratio', 1.0)
            leverage = market_data.get('leverage', 3)
            daily_carry = abs(funding) * leverage * 3
            futures_block = f"""
Futures quantitative data (leverage={leverage}x):
- Funding rate: {funding:+.4f}%/8h | Daily carry if against position: {daily_carry:.4f}%
  → {"SHORT edge (longs overpaying)" if funding > 0.05 else "LONG edge (shorts overpaying)" if funding < -0.05 else "Neutral carry"}
- Open interest: {market_data.get('open_interest', 0):,.0f} USDT
- Long/Short ratio: {ls_ratio:.2f} → {"Crowded longs, fade SHORT" if ls_ratio > 1.5 else "Crowded shorts, fade LONG" if ls_ratio < 0.7 else "Balanced positioning"}"""

        user_prompt = f"""Determine LONG (BUY), SHORT (SELL), or HOLD for {market_data.get('symbol')} perpetual futures:

Technical data:
- Price: {market_data.get('price')}
- RSI(14): {market_data.get('rsi')}
- MACD: {market_data.get('macd')}
- BB upper: {market_data.get('bb_upper')} | lower: {market_data.get('bb_lower')}
- EMA20: {market_data.get('ema20')} | EMA50: {market_data.get('ema50')}
- Volume 24h: {market_data.get('volume')}
- Closes (last 5): {market_data.get('closes', [])[-5:]}
{futures_block}
{news_block}

Portfolio:
- Balance: {context.get('portfolio_balance', 'unknown')} USDT
- Open positions: {context.get('open_positions', 0)}
- Daily P&L: {context.get('daily_pnl', '+0.00')} USDT

System decisions (memory):
{context.get('recent_decisions', 'No history')}

Previous cycle agent votes:
{context.get('prev_agent_votes', 'No previous votes')}

Trade history (real outcomes):
{context.get('trade_history', 'No closed trades yet')}
{context.get('trade_stats', '')}

{context.get('agent_performance', '')}
{context.get('system_events', '')}
{fmt_active_position(context)}
Respond ONLY with this JSON (BUY=LONG, SELL=SHORT, HOLD=flat):
{{"vote": "BUY|SELL|HOLD", "confidence": 0.0, "reasoning": "max 2 sentences with specific numerical evidence"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self._current_model,
                max_tokens=300,
                temperature=0.0,
                extra_body={"enable_thinking": False},  # desactiva thinking de Qwen3
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
        except Exception as e:
            # Rotación automática de modelo si se agotó el free tier
            if "quota" in str(e).lower() or "insufficient" in str(e).lower():
                self.log(f"Quota exhausted on {self._current_model}, rotating to {self.model_fallback}", "WARN")
                self._current_model = self.model_fallback
                response = self.client.chat.completions.create(
                    model=self._current_model,
                    max_tokens=300,
                    temperature=0.0,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                )
            else:
                raise

        text = response.choices[0].message.content.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        elif "{" in text:
            start = text.index("{")
            end   = text.rindex("}") + 1
            text  = text[start:end]

        data = json.loads(text)
        return TradingSignal(
            pair=market_data.get("symbol"),
            vote=AgentVote[data["vote"]],
            confidence=float(data["confidence"]),
            reasoning=data["reasoning"],
            agent_id=f"{self.agent_id}({self._current_model})",
        )
