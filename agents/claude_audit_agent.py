import json
import os

import anthropic


class ClaudeAuditAgent:
    """
    Occasional audit layer for preserving Claude budget.

    It is intentionally not part of every trading cycle. The orchestrator calls
    it only for ambiguous executions or scheduled reviews. It can veto a weak
    trade, but cannot force execution.
    """

    SYSTEM_PROMPT = (
        "You are an occasional risk auditor for a BTCUSDT futures test system. "
        "A cheaper model already made a decision. Your job is to find obvious "
        "reasoning flaws, ignored risk, or incoherent trade justification. "
        "Be concise. APPROVE only if the proposed trade is coherent and risk-aware. "
        "REJECT if evidence is mixed, conviction is weak, or the decision ignores key risk. "
        "Respond only with valid JSON."
    )

    def __init__(self):
        self.agent_id = "claude-auditor"
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = os.getenv("CLAUDE_AUDIT_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"))

    async def audit_decision(self, signal, market_data: dict, context: dict) -> dict:
        prompt = f"""Audit this proposed BTCUSDT futures decision.

Proposed decision:
- Vote: {signal.vote.value}
- Confidence: {signal.confidence:.2f}
- Reasoning: {signal.reasoning}
- Agent: {signal.agent_id}

Market:
- Price: {market_data.get('price')}
- RSI: {market_data.get('rsi')}
- MACD: {market_data.get('macd')}
- EMA20/EMA50: {market_data.get('ema20')} / {market_data.get('ema50')}
- BB upper/lower: {market_data.get('bb_upper')} / {market_data.get('bb_lower')}
- Funding: {market_data.get('funding_rate', 0.0):+.4f}%/8h
- Open interest: {market_data.get('open_interest', 0):,.0f}
- Long/Short ratio: {market_data.get('long_short_ratio', 1.0):.2f}

News and risk:
- News sentiment: {context.get('news_sentiment', 0.0):+.2f}
- News impact: {context.get('news_impact', 'LOW')}
- News bias: {context.get('news_bias', 'HOLD')}
- Key events: {', '.join(context.get('key_events', [])) or 'none'}
- Portfolio balance: {context.get('portfolio_balance', 'unknown')}
- Open positions: {context.get('open_positions', 0)}
- Daily P&L: {context.get('daily_pnl', '+0.00')}
- Trade history: {context.get('trade_history', 'none')}
- Trade stats: {context.get('trade_stats', 'none')}

Respond only with JSON:
{{"approved": true, "risk_level": "LOW|MEDIUM|HIGH", "reason": "one concise sentence"}}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=180,
            temperature=0.0,
            system=[
                {
                    "type": "text",
                    "text": self.SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        elif "{" in text and "}" in text:
            text = text[text.index("{"):text.rindex("}") + 1]
        return json.loads(text)

