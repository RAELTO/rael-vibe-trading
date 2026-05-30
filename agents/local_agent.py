import json
import os
from openai import OpenAI
from agents.base_agent import BaseAgent, TradingSignal, AgentVote, fmt_active_position


class LocalAgent(BaseAgent):
    """
    Agente votante usando Qwen2.5:14b vía Ollama (GPU local).
    Especialidad: scanner técnico rápido, pre-filtro de assets, gatekeeper final.
    Peso en el Decider: 5% (bajo peso en voto, pero es el gatekeeper antes de ejecutar)
    """

    def __init__(self):
        super().__init__("local-qwen", "technical-scanner-gatekeeper")
        self.client = OpenAI(
            api_key="ollama",  # Ollama no requiere key real
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1",
        )
        self.model = os.getenv("LOCAL_MODEL", "qwen2.5:14b")

    async def health_check(self) -> bool:
        try:
            models = self.client.models.list()
            available = [m.id for m in models.data]
            if self.model in available:
                self.is_ready = True
                return True
            self.log(f"Model {self.model} not found. Available: {available}", "ERROR")
            return False
        except Exception as e:
            self.log(f"Health check failed (Ollama running?): {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        system_prompt = (
            "You are a conservative technical scanner for crypto perpetual futures. "
            "BUY = open LONG position. SELL = open SHORT position. HOLD = stay flat. "
            "You operate with 3x leverage — only vote BUY or SELL when signals are exceptionally clear. "
            "LONG signals: price > EMA20 > EMA50, RSI 40-65, MACD positive and rising, price above midline. "
            "SHORT signals: price < EMA20 < EMA50, RSI 35-60, MACD negative and falling, price below midline. "
            "Use funding rate as tiebreaker: positive funding = slight SHORT bias, negative = slight LONG bias. "
            "Default to HOLD for any ambiguous setup. Your role is to filter noise, not to trade frequently. "
            "Respond ONLY with valid JSON, no text outside the JSON."
        )

        news_block = ""
        if context.get("news_sentiment") is not None:
            news_block = f"""
News context:
- Sentiment: {context.get('news_sentiment', 0.0):+.2f}
- Impact: {context.get('news_impact', 'LOW')}
- Key events: {', '.join(context.get('key_events', [])) or 'none'}"""

        futures_line = ""
        if context.get("is_futures"):
            funding = market_data.get('funding_rate', 0.0)
            futures_line = (
                f"\nFutures: leverage={market_data.get('leverage', 3)}x | "
                f"funding={funding:+.4f}%/8h ({'→ SHORT bias' if funding > 0.02 else '→ LONG bias' if funding < -0.02 else '→ neutral'}) | "
                f"L/S={market_data.get('long_short_ratio', 1.0):.2f}"
            )

        user_prompt = f"""Scan {market_data.get('symbol')} futures — vote LONG (BUY), SHORT (SELL), or HOLD:

Technical data:
- Price: {market_data.get('price')} | EMA20: {market_data.get('ema20')} | EMA50: {market_data.get('ema50')}
- RSI(14): {market_data.get('rsi')} | MACD: {market_data.get('macd')}
- BB upper: {market_data.get('bb_upper')} | lower: {market_data.get('bb_lower')}
- Volume 24h: {market_data.get('volume')}
- Closes (last 5): {market_data.get('closes', [])[-5:]}{futures_line}
{news_block}

Portfolio:
- Balance: {context.get('portfolio_balance', 'unknown')} USDT
- Open positions: {context.get('open_positions', 0)}
- Daily P&L: {context.get('daily_pnl', '+0.00')} USDT
{fmt_active_position(context)}
Respond ONLY with this JSON (BUY=LONG, SELL=SHORT, HOLD=flat):
{{"vote": "BUY|SELL|HOLD", "confidence": 0.0, "reasoning": "max 2 sentences with specific data"}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=200,
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

    async def gate_check(self, decision: str, consensus_score: float) -> bool:
        """
        Gatekeeper final antes de ejecutar una orden.
        Qwen hace una última revisión rápida del market_data antes de que el
        Executor envíe la orden a Binance.
        Retorna True si aprueba la ejecución, False para bloquear.
        """
        if decision == "HOLD":
            return False
        if consensus_score < float(os.getenv("MIN_CONSENSUS_SCORE", "0.65")):
            self.log(f"Gate blocked: consensus {consensus_score:.2f} below threshold", "WARN")
            return False
        return True
