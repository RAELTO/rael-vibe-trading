import json
import os
import anthropic
from agents.base_agent import BaseAgent, fmt_active_position


class SynthesisAgent(BaseAgent):
    """
    Pipeline Phase 2 — Reads all Phase 1 analyses and makes the final trading decision.
    Uses Claude Sonnet with prompt caching for the stable system prompt.

    Conviction rules (Plan A — 2 Phase 1 agents):
      Both agree               → conviction 0.65–0.85 (higher if signal_quality STRONG)
      One directional + NEUTRAL → use directional only if signal_quality STRONG (0.55–0.65)
      Both disagree            → HOLD (0.0)
    """

    SYSTEM_PROMPT = (
        "You are a senior derivatives trader synthesizing specialist analyses into a final decision "
        "for crypto perpetual futures. BUY = open LONG. SELL = open SHORT. HOLD = stay flat. "
        "You receive 2 or 3 structured analyses from specialist agents (technical, sentiment, quant). "
        "Conviction rules for BUY/SELL — 3 agents: "
        "(1) 3/3 agree directional → conviction 0.78–0.92 depending on signal quality. "
        "(2) 2/3 agree directional, 1 NEUTRAL → conviction 0.62–0.78. "
        "(3) 2/3 agree directional, 1 opposite → conviction 0.55–0.65 (flag the conflict). "
        "(4) 1/3 directional, 2 NEUTRAL → HOLD. "
        "(5) Split (all different) → HOLD. "
        "Conviction rules for BUY/SELL — 2 agents (when quant unavailable): "
        "(6) Both agree → conviction 0.68–0.88. "
        "(7) One directional + one NEUTRAL + STRONG quality → directional 0.58–0.68. "
        "(8) One directional + one NEUTRAL + MODERATE/WEAK → HOLD. "
        "(9) One BULLISH + one BEARISH → HOLD. "
        "Conviction rules for HOLD (never return 0.0 — always express certainty of inaction): "
        "(A) Full conflict (BULLISH vs BEARISH) → conviction 0.75–0.88. "
        "(B) Directional + NEUTRAL + MODERATE → conviction 0.55–0.70. "
        "(C) Directional + NEUTRAL + WEAK → conviction 0.45–0.55. "
        "(D) All NEUTRAL → conviction 0.62–0.75. "
        "Dominant dimension: 'technical' | 'sentiment' | 'quant' — whichever drove the decision. "
        "Active positions: HOLD to keep, opposite direction only if ≥2 specialists confirm reversal. "
        "Respond ONLY with valid JSON. No text outside the JSON."
    )

    def __init__(self):
        super().__init__("synthesis", "final-decision-synthesis")
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
        self.model = os.getenv("SYNTHESIS_MODEL", "claude-sonnet-4-6")

    async def health_check(self) -> bool:
        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> dict:
        raise NotImplementedError("Use synthesize() in pipeline mode")

    async def synthesize(
        self,
        analyses: list[dict],
        market_data: dict,
        context: dict,
    ) -> dict:
        """Read all Phase 1 analyses and produce final vote + conviction."""
        symbol = market_data.get("symbol", "UNKNOWN")
        price  = market_data.get("price", 0)

        # Format each Phase 1 analysis block
        analyses_block = ""
        for a in analyses:
            agent_id = a.get("agent_id", "unknown")
            if "technical" in agent_id:
                levels = a.get("key_levels", {})
                analyses_block += (
                    f"\nTECHNICAL [{agent_id}]:\n"
                    f"  Direction: {a.get('direction')} | Confidence: {a.get('confidence', 0):.2f} "
                    f"| Quality: {a.get('signal_quality')}\n"
                    f"  Pattern: {a.get('pattern')} | Trend: {a.get('trend_structure')}\n"
                    f"  Levels: support=${levels.get('support', 0):,.0f}, "
                    f"resistance=${levels.get('resistance', 0):,.0f}\n"
                    f"  Analysis: {a.get('analysis')}\n"
                )
            elif "sentiment" in agent_id:
                analyses_block += (
                    f"\nSENTIMENT [{agent_id}]:\n"
                    f"  Direction: {a.get('direction')} | Confidence: {a.get('confidence', 0):.2f} "
                    f"| Regime: {a.get('market_regime')}\n"
                    f"  Catalyst: {a.get('catalyst_strength')} (present={a.get('catalyst_present')})\n"
                    f"  Analysis: {a.get('analysis')}\n"
                )
            elif "quant" in agent_id:
                analyses_block += (
                    f"\nQUANT [{agent_id}]:\n"
                    f"  Direction: {a.get('direction')} | Confidence: {a.get('confidence', 0):.2f}\n"
                    f"  Funding signal: {a.get('funding_signal')} | OI signal: {a.get('oi_signal')}\n"
                    f"  Crowd: {a.get('crowd_signal')} | Squeeze risk: {a.get('squeeze_risk')}\n"
                    f"  Analysis: {a.get('analysis')}\n"
                )
            else:
                analyses_block += (
                    f"\nANALYSIS [{agent_id}]:\n"
                    f"  Direction: {a.get('direction')} | Confidence: {a.get('confidence', 0):.2f}\n"
                    f"  Analysis: {a.get('analysis', str(a))}\n"
                )

        active_pos = fmt_active_position(context)

        user_prompt = f"""Synthesize the specialist analyses below into one final decision for {symbol} futures.

Current price: ${price:,.2f}
{analyses_block}
Portfolio context:
- Balance: {context.get('portfolio_balance', 'unknown')} USDT
- Open positions: {context.get('open_positions', 0)}
- Daily P&L: {context.get('daily_pnl', '0.00')} USDT
{active_pos}
Respond ONLY with this JSON:
{{
  "vote": "BUY|SELL|HOLD",
  "conviction": 0.0,
  "dominant_dimension": "technical|sentiment",
  "confluences": ["signal A confirmed by agent X and agent Y", "..."],
  "conflicts": "description of disagreements and why you chose one over the other (empty string if none)",
  "reasoning": "max 3 sentences: final synthesis rationale and the key evidence"
}}"""

        # Prompt caching on the stable system prompt
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0.0,
            system=[
                {
                    "type": "text",
                    "text": self.SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()

        data = json.loads(text)
        data["agent_id"] = f"{self.agent_id}({self.model})"
        return data
