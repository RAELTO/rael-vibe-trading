import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent


class GateAgent(BaseAgent):
    """
    Pipeline Phase 3 — Risk gate.
    Approves or rejects order execution based on synthesis + portfolio risk state.
    Uses gpt-5.4-mini: better nuanced judgment than nano, still negligible cost (~$0.0005/call).
    """

    SYSTEM_PROMPT = (
        "You are a risk management gate for a crypto perpetual futures trading system. "
        "Your ONLY job: approve or reject a proposed trade. Be conservative but not paranoid. "
        "APPROVE when: conviction >= 0.55, daily loss < 4%, open positions < 3, "
        "synthesis reasoning is coherent, and no extreme risk flags. "
        "REJECT when: conviction < 0.55, daily loss >= 4% of balance, "
        "max positions already open, or synthesis shows fundamental signal conflict. "
        "Respond ONLY with valid JSON. No extra text."
    )

    def __init__(self):
        super().__init__("gate", "risk-approval-gate")
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        self.model = os.getenv("GATE_MODEL", "gpt-5.4-nano")

    async def health_check(self) -> bool:
        try:
            self.client.models.list()
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> dict:
        raise NotImplementedError("Use check() in pipeline mode")

    async def check(self, synthesis: dict, risk_state) -> dict:
        """Approve or reject execution based on synthesis + risk state."""
        max_daily_loss_pct = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.04"))
        balance = risk_state.portfolio_balance
        daily_loss_pct = risk_state.daily_loss / balance if balance > 0 else 0

        prompt = f"""Review proposed trade for risk approval:

SYNTHESIS:
- Vote: {synthesis.get('vote')} | Conviction: {synthesis.get('conviction', 0):.2f}
- Dominant dimension: {synthesis.get('dominant_dimension')}
- Confluences: {synthesis.get('confluences')}
- Conflicts: {synthesis.get('conflicts', 'none')}
- Reasoning: {synthesis.get('reasoning')}

PORTFOLIO RISK STATE:
- Daily loss: ${risk_state.daily_loss:.2f} USDT ({daily_loss_pct*100:.1f}% of balance)
- Open positions: {risk_state.open_positions} / 3 max
- Portfolio balance: ${balance:.2f} USDT

Respond ONLY with: {{"approved": true, "reason": "one sentence"}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=80,
            temperature=0.0,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )

        text = response.choices[0].message.content.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()

        return json.loads(text)
