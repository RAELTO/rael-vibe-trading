import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent, fmt_active_position

FREE_TIER_MODELS = [
    "qwen3-235b-a22b",   # flagship — mejor math/quant, free tier activo
    "qwen-plus",         # fallback confiable, free
]


class QuantAgent(BaseAgent):
    """
    Pipeline Phase 1 — Quant / derivatives specialist.
    Analyzes funding carry, open interest dynamics, crowd positioning and squeeze risk.
    Uses Qwen3-235b-a22b (free tier) for mathematical precision.
    Returns structured dict (not TradingSignal).
    """

    SYSTEM_PROMPT = (
        "You are a quantitative derivatives analyst specializing in crypto perpetual futures mechanics. "
        "Your ONLY focus: funding rate carry, open interest dynamics, crowd positioning, and squeeze risk. "
        "Ignore price action and news — those are handled by other specialists. "
        "BULLISH signals: funding < -0.02%/8h (shorts overpaying → LONG edge), "
        "OI expanding with price rising (trend confirmation), L/S < 0.7 (short squeeze risk). "
        "BEARISH signals: funding > +0.02%/8h (longs overpaying → SHORT edge), "
        "OI expanding with price falling (bearish accumulation), L/S > 1.5 (long squeeze risk). "
        "NEUTRAL: funding near zero, OI flat, balanced positioning. "
        "Carry math: daily_cost = abs(funding_rate) * leverage * 3. "
        "Be quantitatively precise — cite exact rates and ratios. "
        "Respond ONLY with valid JSON."
    )

    def __init__(self):
        super().__init__("quant", "derivatives-quant-analysis")
        self.client = OpenAI(
            api_key=os.getenv("QWEN_API_KEY"),
            base_url=os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        )
        self.model          = os.getenv("QUANT_MODEL", FREE_TIER_MODELS[0])
        self.model_fallback = os.getenv("QUANT_MODEL_FALLBACK", FREE_TIER_MODELS[1])
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
            if "quota" in str(e).lower() or "insufficient" in str(e).lower():
                self.log(f"Free tier exhausted on {self._current_model}, trying fallback", "WARN")
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

    async def analyze(self, market_data: dict, context: dict) -> dict:
        """Returns quant analysis per Phase 1 schema."""
        symbol   = market_data.get("symbol", "UNKNOWN")
        funding  = market_data.get("funding_rate", 0.0)
        ls_ratio = market_data.get("long_short_ratio", 1.0)
        oi       = market_data.get("open_interest", 0)
        leverage = market_data.get("leverage", 3)

        daily_carry = abs(funding) * leverage * 3
        funding_interp = (
            f"longs pay {funding:+.4f}%/8h ({daily_carry:.3f}%/day carry cost) → SHORT carry edge"
            if funding > 0.02 else
            f"shorts pay {abs(funding):.4f}%/8h ({daily_carry:.3f}%/day carry cost) → LONG carry edge"
            if funding < -0.02 else
            f"neutral carry ({funding:+.4f}%/8h, {daily_carry:.4f}%/day)"
        )
        crowd_interp = (
            f"CROWDED LONGS (L/S={ls_ratio:.2f}) — long squeeze risk" if ls_ratio > 1.5 else
            f"CROWDED SHORTS (L/S={ls_ratio:.2f}) — short squeeze risk" if ls_ratio < 0.7 else
            f"BALANCED (L/S={ls_ratio:.2f})"
        )

        active_pos = fmt_active_position(context)

        user_prompt = f"""Analyze derivatives positioning and carry for {symbol} perpetual futures:

Quantitative inputs:
- Funding rate: {funding_interp}
- Open interest: {oi:,.0f} USDT
- Long/Short ratio: {crowd_interp}
- Leverage context: {leverage}x (daily carry at {leverage}x if funding against you: {daily_carry:.3f}%/day)
- Price: {market_data.get('price')} | 24h change: {market_data.get('change_24h', 'N/A')}
{active_pos}
Respond ONLY with this JSON:
{{
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0.0,
  "funding_signal": "CARRY_LONG|CARRY_SHORT|NEUTRAL",
  "oi_signal": "EXPANDING_LONGS|EXPANDING_SHORTS|FLAT",
  "crowd_signal": "CROWDED_LONG|CROWDED_SHORT|BALANCED",
  "squeeze_risk": "HIGH|MEDIUM|LOW",
  "analysis": "max 3 sentences with exact rates and ratios"
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self._current_model,
                max_tokens=400,
                temperature=0.0,
                extra_body={"enable_thinking": False},
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
            )
        except Exception as e:
            if "quota" in str(e).lower() or "insufficient" in str(e).lower():
                self.log(f"Quota exhausted on {self._current_model}, rotating to {self.model_fallback}", "WARN")
                self._current_model = self.model_fallback
                response = self.client.chat.completions.create(
                    model=self._current_model,
                    max_tokens=400,
                    temperature=0.0,
                    extra_body={"enable_thinking": False},
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                )
            else:
                raise

        text = response.choices[0].message.content.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        elif "{" in text:
            text = text[text.index("{"):text.rindex("}") + 1]

        data = json.loads(text)
        data["agent_id"] = f"{self.agent_id}({self._current_model})"
        return data
