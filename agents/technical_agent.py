import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent, fmt_active_position


class TechnicalAgent(BaseAgent):
    """
    Pipeline Phase 1 — Price action specialist.
    Analyzes OHLCV, indicators, and market structure.
    Returns structured analysis dict (BULLISH/BEARISH/NEUTRAL), not a vote.
    """

    SYSTEM_PROMPT = (
        "You are a technical analysis specialist for crypto perpetual futures. "
        "Your ONLY input is OHLCV price data and technical indicators — ignore macro/news. "
        "Identify market structure, key levels, and dominant patterns with precision. "
        "BULLISH: price > EMA20 > EMA50, RSI 40-65, MACD positive and rising, clear uptrend. "
        "BEARISH: price < EMA20 < EMA50, RSI 35-60, MACD negative and falling, clear downtrend. "
        "NEUTRAL: mixed signals, consolidation, or ambiguous structure. "
        "Be specific. Weak setups = NEUTRAL, not forced direction. "
        "Respond ONLY with valid JSON."
    )

    def __init__(self):
        super().__init__("technical", "price-action-analysis")
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
        )
        self.model = os.getenv("TECHNICAL_MODEL", "deepseek-v4-flash")

    async def health_check(self) -> bool:
        try:
            self.client.models.list()
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> dict:
        """Returns technical analysis per Phase 1 schema."""
        symbol = market_data.get("symbol", "UNKNOWN")
        price  = market_data.get("price", 0)
        ema20  = market_data.get("ema20", 0)
        ema50  = market_data.get("ema50", 0)

        trend = (
            "UPTREND (price > EMA20 > EMA50)" if price > ema20 > ema50 else
            "DOWNTREND (price < EMA20 < EMA50)" if price < ema20 < ema50 else
            "CHOPPY (mixed EMA alignment)"
        )

        closes = market_data.get("closes", [])
        closes_str = str(closes[-10:]) if closes else "N/A"

        active_pos = fmt_active_position(context)

        user_prompt = f"""Analyze the technical structure of {symbol} perpetual futures:

OHLCV & Indicators:
- Price: {price} | EMA20: {ema20} | EMA50: {ema50}
- RSI(14): {market_data.get('rsi')} | MACD: {market_data.get('macd')}
- BB upper: {market_data.get('bb_upper')} | BB lower: {market_data.get('bb_lower')}
- Volume 24h: {market_data.get('volume')}
- Closes (last 10): {closes_str}
- Trend structure: {trend}
{active_pos}
Respond ONLY with this JSON:
{{
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0.0,
  "pattern": "dominant pattern name",
  "key_levels": {{"support": 0.0, "resistance": 0.0}},
  "trend_structure": "UPTREND|DOWNTREND|CHOPPY",
  "signal_quality": "STRONG|MODERATE|WEAK",
  "analysis": "max 3 sentences describing the technical setup with specific values"
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=3000,  # reasoning interno consume ~300-400 tokens aunque enable_thinking=False
            temperature=0.0,
            extra_body={"enable_thinking": False},  # V4 Flash es reasoning model — deshabilitar para JSON
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
        )

        text = response.choices[0].message.content.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()

        data = json.loads(text)
        data["agent_id"] = f"{self.agent_id}({self.model})"
        return data
