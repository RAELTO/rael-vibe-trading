import json
import os
import anthropic
from agents.base_agent import BaseAgent, TradingSignal, AgentVote, fmt_active_position


class ClaudeAgent(BaseAgent):
    """
    Agente votante usando Claude Sonnet vía Anthropic API con prompt caching.
    Especialidad: decisión final con contexto macro, memoria histórica y razonamiento complejo.
    Peso en el Decider: 40% (mayor peso — integra todos los contextos)
    """

    SYSTEM_PROMPT = (
        "You are a senior derivatives trader and chief risk officer for a USD-M perpetual futures system. "
        "BUY = open LONG position. SELL = open SHORT position. HOLD = stay flat. "
        "You operate with 3x leverage — both directions are valid trading opportunities. "
        "Futures-specific rules: "
        "(1) Funding rate > +0.05%/8h means longs bleed carry — SHORT is more favorable. "
        "(2) Funding rate < -0.05%/8h means shorts bleed carry — LONG is more favorable. "
        "(3) OI rising + price rising = trend confirmation. OI rising + price falling = building short pressure. "
        "(4) L/S ratio > 1.5 = crowded longs, squeeze risk — lean SHORT. "
        "(5) L/S ratio < 0.7 = crowded shorts, squeeze risk — lean LONG. "
        "(6) Never chase: require price + MACD + volume alignment before committing. "
        "(7) Weight recent trade outcomes heavily — if recent trades are losses, raise your threshold. "
        "HOLD only when signals genuinely conflict, not as a default. "
        "Respond ONLY with valid JSON."
    )

    def __init__(self):
        super().__init__("claude-sonnet", "final-decision-macro-context")
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
        self.model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    async def health_check(self) -> bool:
        try:
            # Minimal test call
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

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        news_block = ""
        if context.get("news_sentiment") is not None:
            news_block = f"""
News context:
- Sentiment: {context.get('news_sentiment', 0.0):+.2f}
- Impact: {context.get('news_impact', 'LOW')}
- Key events: {', '.join(context.get('key_events', [])) or 'none'}
- Recommended bias: {context.get('news_bias', 'HOLD')}"""

        futures_block = ""
        if context.get("is_futures"):
            funding   = market_data.get('funding_rate', 0.0)
            ls_ratio  = market_data.get('long_short_ratio', 1.0)
            leverage  = market_data.get('leverage', 3)
            sl_pct    = float(os.getenv("FUTURES_SL_PCT", "0.015")) * 100
            tp_pct    = float(os.getenv("FUTURES_TP_PCT", "0.025")) * 100
            funding_signal = (
                "HIGH POSITIVE — longs bleeding carry, SHORT favored" if funding > 0.05 else
                "MODERATE POSITIVE — slight short bias" if funding > 0.01 else
                "HIGH NEGATIVE — shorts bleeding carry, LONG favored" if funding < -0.05 else
                "MODERATE NEGATIVE — slight long bias" if funding < -0.01 else
                "NEUTRAL"
            )
            crowd_signal = (
                "CROWDED LONGS (>1.5) — long squeeze risk, SHORT bias" if ls_ratio > 1.5 else
                "CROWDED SHORTS (<0.7) — short squeeze risk, LONG bias" if ls_ratio < 0.7 else
                "BALANCED"
            )
            futures_block = f"""
Futures positioning (leverage={leverage}x | SL={sl_pct:.1f}% TP={tp_pct:.1f}% | R:R={tp_pct/sl_pct:.1f}:1):
- Funding rate: {funding:+.4f}%/8h → {funding_signal}
  (Carry cost at {leverage}x if against you: {abs(funding)*leverage*3:.3f}%/day)
- Open interest: {market_data.get('open_interest', 0):,.0f} USDT
- Long/Short ratio: {ls_ratio:.2f} → {crowd_signal}"""

        user_prompt = f"""Determine direction for {market_data.get('symbol')} perpetual futures (BUY=LONG, SELL=SHORT, HOLD=flat):

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

System decisions (memory):
{context.get('recent_decisions', 'No history yet')}

Previous cycle agent votes:
{context.get('prev_agent_votes', 'No previous votes')}

Trade history (real outcomes):
{context.get('trade_history', 'No closed trades yet')}
{context.get('trade_stats', '')}

{context.get('agent_performance', '')}
{context.get('system_events', '')}

Portfolio:
- Balance: {context.get('portfolio_balance', 'unknown')} USDT
- Open positions: {context.get('open_positions', 0)}
- Daily P&L: {context.get('daily_pnl', 'unknown')}
{f"Previous epoch: {context['epoch_postmortem']}" if context.get('epoch_postmortem') else ""}
{fmt_active_position(context)}
Respond ONLY with this JSON (BUY=LONG, SELL=SHORT, HOLD=flat):
{{"vote": "BUY|SELL|HOLD", "confidence": 0.0, "reasoning": "max 2 sentences citing specific indicator values and futures signals"}}"""

        # Prompt caching: system prompt is cached (saves ~90% on fixed tokens)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=250,
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
        return TradingSignal(
            pair=market_data.get("symbol"),
            vote=AgentVote[data["vote"]],
            confidence=float(data["confidence"]),
            reasoning=data["reasoning"],
            agent_id=f"{self.agent_id}({self.model})",
        )
