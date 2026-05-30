import json
import os
from google import genai
from google.genai import types
from agents.base_agent import BaseAgent, TradingSignal, AgentVote


class GeminiAgent(BaseAgent):
    """
    Agente votante usando Gemini 2.5 Flash vía SDK nativo de Google.
    Thinking mode desactivado para respuestas rápidas y costo controlado.
    Especialidad: análisis técnico multi-timeframe y reconocimiento de patrones.
    Peso en el Decider: 25%
    """

    SYSTEM_PROMPT = (
        "You are a technical analysis expert specializing in crypto chart patterns. "
        "Your strength is multi-timeframe analysis, trend identification, and "
        "support/resistance levels. Prioritize high-probability setups. "
        "Respond ONLY with valid JSON, no extra text."
    )

    def __init__(self):
        super().__init__("gemini-flash", "technical-pattern-analysis")
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.model  = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    async def health_check(self) -> bool:
        try:
            r = self.client.models.generate_content(
                model=self.model,
                contents="ping",
                config=types.GenerateContentConfig(max_output_tokens=5),
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
- Bias: {context.get('news_bias', 'HOLD')}"""

        user_prompt = f"""Analyze and vote for: {market_data.get('symbol')}

Technical data:
- Price: {market_data.get('price')}
- RSI(14): {market_data.get('rsi')}
- MACD: {market_data.get('macd')}
- BB upper: {market_data.get('bb_upper')} | lower: {market_data.get('bb_lower')}
- EMA20: {market_data.get('ema20')} | EMA50: {market_data.get('ema50')}
- Volume 24h: {market_data.get('volume')}
- Closes (last 5): {market_data.get('closes', [])[-5:]}
{news_block}

Recent decisions (MemPalace):
{context.get('recent_decisions', 'No history')}

Respond ONLY with this JSON:
{{"vote": "BUY|SELL|HOLD", "confidence": 0.0, "reasoning": "max 2 sentences with specific data"}}"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.SYSTEM_PROMPT,
                max_output_tokens=300,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),  # sin thinking
            ),
        )

        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        elif "{" in text:
            start = text.index("{")
            end   = text.rindex("}") + 1
            text  = text[start:end]

        data = json.loads(text)
        return TradingSignal(
            pair=market_data.get("symbol"),
            vote=AgentVote[data["vote"]],
            confidence=float(data["confidence"]),
            reasoning=data["reasoning"],
            agent_id=self.agent_id,
        )
