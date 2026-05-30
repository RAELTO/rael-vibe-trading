import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone

from openai import OpenAI

from agents.base_agent import AgentVote, BaseAgent, TradingSignal, fmt_active_position


class DeepSeekDecisionAgent(BaseAgent):
    """
    Single-pass decision agent for the low-cost production test mode.

    It replaces the old Phase 1 + Claude synthesis pipeline by asking DeepSeek
    V4 Pro to evaluate technicals, derivatives positioning, GPT web-search
    context, recent trade outcomes, and portfolio state in one structured call.
    Execution risk remains enforced by RiskManager, not by the model.
    """

    SYSTEM_PROMPT = (
        "You are the primary decision engine for a BTCUSDT USD-M perpetual futures test system. "
        "BUY means open LONG, SELL means open SHORT, HOLD means no new trade. "
        "Analyze price action, trend, indicators, derivatives positioning, recent trade outcomes, "
        "current news context, and portfolio risk. Be conservative: no clear edge means HOLD. "
        "Do not size the position and do not bypass risk rules; only decide direction and conviction. "
        "Futures rules: avoid chasing extended moves, prefer confluence between EMA trend/MACD/RSI, "
        "respect support/resistance room for SL=1.5% and TP=2.5%, and penalize crowded positioning. "
        "Respond only with valid JSON."
    )

    def __init__(self):
        super().__init__("deepseek-decision", "single-pass-futures-decision")
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
        )
        self.model = os.getenv("DEEPSEEK_DECISION_MODEL", "deepseek-v4-pro")

    @staticmethod
    def _extract_json_object(text: str) -> str:
        """Extract the first balanced JSON object from model output."""
        text = (text or "").strip().lstrip("\ufeff")
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        start = text.find("{")
        if start < 0:
            return text

        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start=start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return text[start:]

    @staticmethod
    def _safe_json_loads(text: str) -> dict:
        candidate = DeepSeekDecisionAgent._extract_json_object(text)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", candidate)
            return json.loads(cleaned)

    @staticmethod
    def _salvage_signal(text: str) -> dict | None:
        """Last-resort extraction when JSON is almost valid but malformed."""
        vote_match = re.search(r'"?vote"?\s*:\s*"?\b(BUY|SELL|HOLD)\b"?', text, re.I)
        conf_match = re.search(r'"?confidence"?\s*:\s*([01](?:\.\d+)?)', text, re.I)
        reason_match = re.search(r'"?reasoning"?\s*:\s*"([^"]{1,500})"', text, re.I | re.S)
        if not vote_match:
            return None
        return {
            "vote": vote_match.group(1).upper(),
            "confidence": float(conf_match.group(1)) if conf_match else 0.0,
            "reasoning": (reason_match.group(1).strip() if reason_match else "Recovered from malformed DeepSeek JSON."),
        }

    @staticmethod
    def _log_bad_json(raw: str, error: Exception):
        try:
            root = Path(__file__).resolve().parents[1]
            log_dir = root / "logs"
            log_dir.mkdir(exist_ok=True)
            with (log_dir / "deepseek_bad_json.log").open("a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now(timezone.utc).isoformat()} ---\n")
                f.write(f"ERROR: {error}\n")
                f.write(raw or "<empty>")
                f.write("\n")
        except Exception:
            pass

    async def health_check(self) -> bool:
        try:
            self.client.models.list()
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        symbol = market_data.get("symbol", "BTCUSDT")
        closes = market_data.get("closes", [])
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        volumes = market_data.get("volumes", [])
        price = market_data.get("price", 0)
        ema20 = market_data.get("ema20", 0)
        ema50 = market_data.get("ema50", 0)
        trend = (
            "UPTREND price > EMA20 > EMA50" if price > ema20 > ema50 else
            "DOWNTREND price < EMA20 < EMA50" if price < ema20 < ema50 else
            "CHOPPY or mixed EMA alignment"
        )

        news_block = f"""
GPT web-search market context:
- Sentiment: {context.get('news_sentiment', 0.0):+.2f}
- Impact: {context.get('news_impact', 'LOW')}
- Bias: {context.get('news_bias', 'HOLD')}
- Key events: {', '.join(context.get('key_events', [])) or 'none'}
- Macro summary: {context.get('geopolitical_summary', '')}
- Catalyst evidence: {context.get('catalyst_evidence', '')}
"""

        prompt = f"""Make one final trading decision for {symbol} perpetual futures.

Current market:
- Price: {price}
- Trend: {trend}
- RSI(14): {market_data.get('rsi')}
- MACD: {market_data.get('macd')}
- EMA20: {ema20} | EMA50: {ema50}
- Bollinger upper/lower: {market_data.get('bb_upper')} / {market_data.get('bb_lower')}
- 24h high/low/change: {market_data.get('high_24h')} / {market_data.get('low_24h')} / {market_data.get('change_24h_pct')}%
- Basis vs index: {market_data.get('basis_pct')}%
- Recent closes: {closes[-24:]}
- Recent highs: {highs[-24:]}
- Recent lows: {lows[-24:]}
- Recent volumes: {volumes[-24:]}

Derivatives positioning:
- Funding rate: {market_data.get('funding_rate', 0.0):+.4f}% per 8h
- Funding annualized: {market_data.get('funding_annualized', 0.0)}%
- Open interest: {market_data.get('open_interest', 0):,.0f}
- Long/Short ratio: {market_data.get('long_short_ratio', 1.0):.2f}
- Leverage: {market_data.get('leverage', 3)}x
- Risk template: SL=1.5%, TP=2.5%

{news_block}
Portfolio and memory:
- Balance: {context.get('portfolio_balance', 'unknown')} USDT
- Open positions: {context.get('open_positions', 0)}
- Daily P&L: {context.get('daily_pnl', '+0.00')} USDT
- Recent decisions: {context.get('recent_decisions', 'none')}
- Closed trade history: {context.get('trade_history', 'none')}
- Trade stats: {context.get('trade_stats', 'none')}
- Prior analysis history: {context.get('phase1_history', 'none')}
- System events: {context.get('system_events', 'none')}
{fmt_active_position(context)}

Decision rules:
- BUY only when long setup has directional edge and room to TP before major resistance.
- SELL only when short setup has directional edge and room to TP before major support.
- HOLD when trend, momentum, positioning, and news are mixed.
- Conviction below 0.60 should usually be HOLD.
- If news is HIGH risk or avoid_trading is true, prefer HOLD unless a verified catalyst strongly supports direction.

Respond only with JSON:
{{
  "vote": "BUY|SELL|HOLD",
  "confidence": 0.0,
  "dominant_dimension": "technical|positioning|news|risk|mixed",
  "setup_quality": "STRONG|MODERATE|WEAK|NO_TRADE",
  "key_levels": {{"support": 0.0, "resistance": 0.0}},
  "conflicts": "main contradictory evidence, or empty string",
  "reasoning": "max 3 sentences with exact indicator/positioning/news evidence"
}}"""

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1600,
            temperature=0.0,
            extra_body={"enable_thinking": False},
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )

        message = response.choices[0].message
        raw_text = (message.content or "").strip()
        text = raw_text
        if not text:
            raw_text = (getattr(message, "reasoning_content", "") or "").strip()
            text = raw_text

        try:
            data = self._safe_json_loads(text)
        except Exception as e:
            self._log_bad_json(raw_text, e)
            data = self._salvage_signal(raw_text)
            if not data:
                preview = raw_text[:240].replace("\n", " ") if raw_text else "empty response"
                return TradingSignal(
                    pair=symbol,
                    vote=AgentVote.HOLD,
                    confidence=0.0,
                    reasoning=f"DeepSeek returned non-JSON output; holding for safety. Preview: {preview}",
                    agent_id=f"{self.agent_id}({self.model})",
                )

        vote = str(data.get("vote", "HOLD")).upper()
        if vote not in ("BUY", "SELL", "HOLD"):
            vote = "HOLD"
        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except Exception:
            confidence = 0.0
        reasoning = str(data.get("reasoning", "")).strip() or "No reasoning provided."

        if data.get("recovered") is True:
            reasoning = f"Recovered from malformed JSON. {reasoning}"

        if vote in ("BUY", "SELL") and confidence <= 0:
            # Never execute a recovered directional signal with zero confidence.
            vote = "HOLD"
            reasoning = f"Directional response had invalid confidence; holding for safety. {reasoning}"

        return TradingSignal(
            pair=symbol,
            vote=AgentVote[vote],
            confidence=confidence,
            reasoning=reasoning,
            agent_id=f"{self.agent_id}({self.model})",
        )
