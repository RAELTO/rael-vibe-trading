import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent, TradingSignal, AgentVote, fmt_active_position


class GPTAgent(BaseAgent):
    """
    Agente votante usando GPT-5.4-nano vía OpenAI API.
    Especialidad: análisis macro, sentimiento de mercado y contexto fundamental.
    Peso en el Decider: 15%
    """

    def __init__(self):
        super().__init__("gpt-5.4-nano", "macro-sentiment-analysis")
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        self.model = os.getenv("GPT_MODEL", "gpt-5.4-nano")

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
            "You are a market sentiment and crowd positioning analyst for crypto perpetual futures. "
            "BUY = open LONG position. SELL = open SHORT position. HOLD = stay flat. "
            "Your edge is reading market psychology, positioning extremes, and narrative catalysts. "
            "Positioning signals: "
            "(1) L/S ratio > 1.5 = euphoric longs, prime SHORT setup — crowd is wrong at extremes. "
            "(2) L/S ratio < 0.7 = panic shorts, prime LONG setup — short squeeze imminent. "
            "(3) High positive funding + bullish news = already priced in, fade the hype → SHORT. "
            "(4) Bearish news + negative funding = capitulation → contrarian LONG opportunity. "
            "(5) News catalyst aligned with technicals = high-conviction directional trade. "
            "(6) Neutral/mixed news + extreme positioning = let positioning drive the trade. "
            "Crowd is usually right in the middle of trends but wrong at extremes. "
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
            positioning = (
                f"CROWDED LONGS — euphoria risk, SHORT bias" if ls_ratio > 1.5 else
                f"CROWDED SHORTS — capitulation risk, LONG bias" if ls_ratio < 0.7 else
                f"BALANCED — follow technicals and news"
            )
            futures_block = f"""
Futures sentiment & positioning (leverage={leverage}x):
- Funding rate: {funding:+.4f}%/8h → {"Market paying premium to be LONG (bearish signal)" if funding > 0.05 else "Market paying premium to be SHORT (bullish signal)" if funding < -0.05 else "Normal carry"}
- Open interest: {market_data.get('open_interest', 0):,.0f} USDT
- Long/Short ratio: {ls_ratio:.2f} → {positioning}"""

        user_prompt = f"""Assess market sentiment and determine LONG (BUY), SHORT (SELL), or HOLD for {market_data.get('symbol')} futures:

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
{{"vote": "BUY|SELL|HOLD", "confidence": 0.0, "reasoning": "max 2 sentences citing positioning data, funding rate, and news catalyst"}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=200,
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
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
