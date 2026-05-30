import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent


class SentimentAgent(BaseAgent):
    """
    Pipeline Phase 1 — Macro & sentiment specialist.
    Analyzes news catalysts, market regime, and positioning extremes.
    Returns structured analysis dict (BULLISH/BEARISH/NEUTRAL), not a vote.
    """

    SYSTEM_PROMPT = (
        "You are a macro and market sentiment specialist for crypto perpetual futures. "
        "Your focus: news catalysts, market regime (risk-on/off), and positioning extremes. "
        "Ignore technical price action — that is handled by another agent. "
        "BULLISH: strong positive catalysts, risk-on regime, favorable macro, or short squeeze setup. "
        "BEARISH: negative catalysts, risk-off regime, regulatory headwinds, or long squeeze setup. "
        "NEUTRAL: no clear catalyst, mixed signals, uncertain regime, or irrelevant news. "
        "Funding rate and L/S ratio are positioning signals — weight them heavily. "
        "No news ≠ NEUTRAL; no catalyst means this dimension is non-determinative. "
        "Respond ONLY with valid JSON."
    )

    def __init__(self):
        super().__init__("sentiment", "macro-sentiment-analysis")
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
        )
        self.model = os.getenv("SENTIMENT_MODEL", "deepseek-v4-flash")

    async def health_check(self) -> bool:
        try:
            self.client.models.list()
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> dict:
        """Returns sentiment analysis per Phase 1 schema."""
        symbol   = market_data.get("symbol", "UNKNOWN")
        funding  = market_data.get("funding_rate", 0.0)
        ls_ratio = market_data.get("long_short_ratio", 1.0)
        oi       = market_data.get("open_interest", 0)

        funding_interp = (
            "longs pay — NEGATIVE carry for longs, slight SHORT bias" if funding > 0.02 else
            "shorts pay — POSITIVE carry for longs, slight LONG bias" if funding < -0.02 else
            "neutral carry"
        )
        crowd_interp = (
            "CROWDED LONGS (>1.5) — long squeeze risk, SHORT bias" if ls_ratio > 1.5 else
            "CROWDED SHORTS (<0.7) — short squeeze risk, LONG bias" if ls_ratio < 0.7 else
            "BALANCED positioning"
        )

        news_block = "No news context available."
        if context.get("news_sentiment") is not None:
            news_block = (
                f"- Sentiment score: {context.get('news_sentiment', 0.0):+.2f}\n"
                f"- Market impact: {context.get('news_impact', 'LOW')}\n"
                f"- Key events: {', '.join(context.get('key_events', [])) or 'none'}\n"
                f"- Recommended bias: {context.get('news_bias', 'HOLD')}"
            )

        user_prompt = f"""Assess macro sentiment and positioning for {symbol} perpetual futures:

News & Macro Context:
{news_block}

Market Positioning (futures-specific):
- Funding rate: {funding:+.4f}%/8h → {funding_interp}
- Long/Short ratio: {ls_ratio:.2f} → {crowd_interp}
- Open interest: {oi:,.0f} USDT

Respond ONLY with this JSON:
{{
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0.0,
  "catalyst_present": false,
  "catalyst_strength": "HIGH|MEDIUM|LOW|NONE",
  "market_regime": "RISK_ON|RISK_OFF|UNCERTAIN",
  "analysis": "max 3 sentences describing catalyst, regime, and positioning signals"
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
