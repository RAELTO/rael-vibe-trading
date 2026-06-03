import asyncio
import json
import os

import anthropic


class ClaudeAdvisorAgent:
    """
    Claude learning and review layer.

    Unlike the auditor (which vetoes borderline signals before execution), this
    agent does NOT intervene in execution. It has two continuous-improvement roles:

      1. post_mortem(): after a trade closes, it analyzes why it won or lost and
         extracts an actionable lesson + a pattern tag. Lessons accumulate in the
         DB and are injected into the decider's (DeepSeek) prompt.
      2. daily_review(): once a day it summarizes performance (win-rate, PnL,
         biases) and proposes adjustments. Shown on the dashboard.

    Neither can open/close orders or change risk — they only produce text the
    system uses as context.
    """

    POST_MORTEM_SYSTEM = (
        "You are a trading post-mortem analyst for a BTCUSDT perpetual futures test system. "
        "Given a closed trade (its entry rationale and real outcome), identify the single most "
        "useful, concrete lesson to improve future decisions. Be specific about the technical/"
        "positioning context that mattered. Avoid generic advice. Respond only with valid JSON."
    )

    REVIEW_SYSTEM = (
        "You are a strategy reviewer for a BTCUSDT perpetual futures test system. "
        "Given recent performance stats, closed trades, decisions and accumulated lessons, "
        "produce a concise daily review: an honest summary, a letter grade (A-F) for recent "
        "decision quality, and a short list of concrete, actionable adjustments. "
        "Base everything on the data given; do not invent trades. Respond only with valid JSON."
    )

    def __init__(self):
        self.agent_id = "claude-advisor"
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv(
            "CLAUDE_ADVISOR_MODEL",
            os.getenv("CLAUDE_AUDIT_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")),
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = (text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        elif "{" in text and "}" in text:
            text = text[text.index("{"):text.rindex("}") + 1]
        return json.loads(text)

    @staticmethod
    def _entry_rationale(trade: dict) -> str:
        """Extract the entry rationale stored in agent_votes (if present)."""
        raw = trade.get("agent_votes")
        if not raw:
            return "no entry rationale recorded"
        try:
            votes = json.loads(raw) if isinstance(raw, str) else raw
            parts = [
                f"{v.get('agent_id', '?')}: {str(v.get('reasoning') or v.get('analysis', ''))[:200]}"
                for v in votes
            ]
            return " | ".join(parts) or "no entry rationale recorded"
        except Exception:
            return "no entry rationale recorded"

    async def post_mortem(self, trade: dict, exit_price: float, exit_reason: str, pnl: float) -> dict:
        outcome = "WIN" if pnl > 0 else "LOSS"
        prompt = f"""Analyze this CLOSED BTCUSDT futures trade and extract one actionable lesson.

Trade:
- Side: {trade.get('side')}
- Entry price: {trade.get('entry_price')}
- Exit price: {exit_price}
- Stop-loss: {trade.get('sl_price')} | Take-profit: {trade.get('tp_price')}
- Exit reason: {exit_reason}
- Result: {outcome} ({pnl:+.4f} USDT)
- Entry rationale: {self._entry_rationale(trade)}

Respond only with JSON:
{{
  "tag": "3-6 word pattern label, e.g. 'counter-trend short in oversold'",
  "lesson": "one or two sentences: the concrete, actionable takeaway for future trades",
  "what_worked": "brief, or empty string",
  "what_failed": "brief, or empty string"
}}"""

        def _call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=320,
                temperature=0.0,
                system=[{"type": "text", "text": self.POST_MORTEM_SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )

        response = await asyncio.to_thread(_call)
        return self._parse_json(response.content[0].text)

    async def daily_review(
        self, review_date: str, stats: dict, recent_trades: list[dict],
        recent_decisions: str, lessons: str,
    ) -> dict:
        trades_block = "\n".join(
            f"  - {t.get('side')} @ ${t.get('entry_price'):,.0f} → ${(t.get('exit_price') or 0):,.0f} "
            f"({t.get('exit_reason')}) {(t.get('pnl') or 0):+.2f} USDT"
            for t in recent_trades
        ) or "  (no closed trades)"

        prompt = f"""Produce the daily strategy review for {review_date} (UTC).

Performance stats (last 20 closed trades):
- Total: {stats.get('total', 0)}
- Win rate: {stats.get('win_rate', 0)}%
- Avg profit: {stats.get('avg_profit', 0)} | Avg loss: {stats.get('avg_loss', 0)}
- Current streak: {stats.get('streak', 0)}

Recent closed trades:
{trades_block}

Recent decisions: {recent_decisions or 'none'}

Accumulated lessons from past trades:
{lessons or '  (none yet)'}

Respond only with JSON:
{{
  "grade": "A|B|C|D|F",
  "summary": "2-4 sentences: honest assessment of recent decision quality and what is driving results",
  "adjustments": ["concrete actionable adjustment 1", "adjustment 2", "adjustment 3"]
}}"""

        def _call():
            return self.client.messages.create(
                model=self.model,
                max_tokens=700,
                temperature=0.0,
                system=[{"type": "text", "text": self.REVIEW_SYSTEM,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )

        response = await asyncio.to_thread(_call)
        return self._parse_json(response.content[0].text)
