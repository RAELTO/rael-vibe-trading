import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent, TradingSignal, AgentVote, fmt_active_position


class DeepSeekAgent(BaseAgent):
    """
    Agente votante usando DeepSeek V3 vía API compatible con OpenAI.
    Especialidad: análisis cuantitativo, matemático y de patrones técnicos.
    Peso en el Decider: 15%
    """

    def __init__(self):
        super().__init__("deepseek-v3", "quant-math-analysis")
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
        )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    async def health_check(self) -> bool:
        try:
            self.client.models.list()
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        system_prompt = (
            "You are a technical analyst specializing in futures market structure and price action. "
            "BUY = open LONG position. SELL = open SHORT position. HOLD = no trade. "
            "You analyze both LONG and SHORT setups with equal weight — bearish signals are SHORT opportunities, not just 'avoid buying'. "
            "Technical framework for futures: "
            "(1) Price < EMA20 < EMA50 with declining MACD = active SHORT setup, not just bearish. "
            "(2) Price > EMA20 > EMA50 with rising MACD = active LONG setup. "
            "(3) RSI divergence (price makes new high/low but RSI doesn't) = reversal signal — trade the fade. "
            "(4) Price at BB upper with RSI > 70 = SHORT entry. Price at BB lower with RSI < 30 = LONG entry. "
            "(5) MACD histogram turning negative from positive = SHORT trigger. Opposite = LONG trigger. "
            "(6) With 3x leverage: SL=1.5%, TP=2.5% — only trade setups where price has clear room to move. "
            "Be decisive: clear directional signals = commit BUY or SELL. Ambiguous = HOLD. "
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
            price    = market_data.get('price', 0)
            ema20    = market_data.get('ema20', 0)
            ema50    = market_data.get('ema50', 0)
            leverage = market_data.get('leverage', 3)
            trend = (
                "UPTREND (price > EMA20 > EMA50)" if price > ema20 > ema50 else
                "DOWNTREND (price < EMA20 < EMA50)" if price < ema20 < ema50 else
                "CHOPPY (mixed EMA alignment)"
            )
            futures_block = f"""
Futures technical context (leverage={leverage}x):
- Trend structure: {trend}
- Funding rate: {funding:+.4f}%/8h ({"longs pay — slight SHORT bias" if funding > 0 else "shorts pay — slight LONG bias"})
- Open interest: {market_data.get('open_interest', 0):,.0f} USDT
- Long/Short ratio: {market_data.get('long_short_ratio', 1.0):.2f}"""

        user_prompt = f"""Identify the technical setup (LONG/SHORT/HOLD) for {market_data.get('symbol')} futures (BUY=LONG, SELL=SHORT):

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
Respond ONLY with this JSON (BUY=LONG, SELL=SHORT, HOLD=no trade):
{{"vote": "BUY|SELL|HOLD", "confidence": 0.0, "reasoning": "max 2 sentences naming the specific technical pattern and key levels"}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=200,
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        text = response.choices[0].message.content.strip()
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
