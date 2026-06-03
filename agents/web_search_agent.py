import asyncio
import json
import os
from datetime import datetime, timezone

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class WebSearchAgent:
    """
    Proactive market-intelligence agent.

    Runs independently from the trading loop and keeps latest_context in the
    same JSON shape expected by the orchestrator, but uses OpenAI web search
    instead of DuckDuckGo scraping plus a separate Claude analysis call.
    """

    TRACKED_ASSETS = ["BTCUSDT"]

    def __init__(self, memory_client=None, llm_client: OpenAI = None):
        self.memory = memory_client
        self.client = llm_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("NEWS_SEARCH_MODEL", "gpt-4o-mini-search-preview")
        self.fallback_model = os.getenv("NEWS_SEARCH_FALLBACK_MODEL", "gpt-4o-mini-search-preview")
        self.latest_context = {}
        self.interval_seconds = int(os.getenv("NEWS_INTERVAL_SECONDS", 10800))
        self.max_searches = int(os.getenv("NEWS_SEARCH_MAX_USES", 8))

    def analyze_with_gpt_search(self) -> dict:
        prompt = f"""You are a macro, regulatory and on-chain risk analyst for a Bitcoin futures (BTCUSDT) daytrading system.

Search the web for recent, verifiable information about:
- Bitcoin, BTCUSDT, spot Bitcoin ETFs, flows from BlackRock/Fidelity/IBIT/FBTC.
- Relevant crypto regulation in the United States and major markets.
- Hacks, insolvencies, stablecoin depegs, liquidations or systemic events.
- Fed, rates, inflation, the dollar, macro risk and geopolitics with direct impact on BTC.
- On-chain data / news about whales, miners, hashrate or exchange reserves only if from reputable sources.

Current UTC date/time: {datetime.now(timezone.utc).isoformat()}
Prioritize up to {self.max_searches} recent and trustworthy sources.

Your main task is to detect VERIFIABLE high-impact CATALYSTS: concrete events with real evidence that historically can move BTC significantly.

Examples that qualify:
- A government, regulator or major company announces an official action on BTC.
- The SEC, CFTC, Fed or another regulator announces something unexpected.
- An ETF has extraordinary flow confirmed by a reputable source.
- A major exchange suffers a confirmed hack, insolvency or outage.
- A relevant stablecoin confirmedly loses its peg.

Does NOT qualify as a catalyst:
- Price predictions, viral posts, rumors or third-party technical analysis.
- Repeated news with no concrete novelty.
- Price movement with no verifiable cause.

Respond ONLY with valid JSON, no markdown, with this exact structure:
{{
  "overall_sentiment": 0.0,
  "market_impact": "HIGH|MEDIUM|LOW",
  "risk_level": "HIGH|MEDIUM|LOW",
  "geopolitical_summary": "2-sentence summary of macro relevant to BTC",
  "crypto_summary": "2-sentence summary of Bitcoin-specific news",
  "key_events": ["event1", "event2", "event3"],
  "asset_scores": {{
    "BTCUSDT": 0.0
  }},
  "recommended_asset": "BTCUSDT",
  "recommended_action_bias": "BUY|SELL|HOLD|AVOID",
  "confidence": 0.0,
  "avoid_trading": false,
  "avoid_reason": "",
  "verified_catalyst": false,
  "catalyst_direction": "BULLISH|BEARISH|NEUTRAL",
  "catalyst_veracity": 0.0,
  "catalyst_evidence": "Concrete event and the sources confirming it, or empty if there is no catalyst",
  "sources": ["https://source1", "https://source2"]
}}

Rules:
- Consider ONLY news from the LAST 48 HOURS. Ignore the already-known backdrop
  (historical spot-ETF approval, general institutional adoption, regulation already in force):
  that is CONTEXT, not a catalyst. Do not report it as an event or inflate impact because of it.
- market_impact=HIGH ONLY if verified_catalyst=true (a fresh, dated event with a reputable source).
  NEVER set market_impact=HIGH with verified_catalyst=false. When in doubt use LOW or MEDIUM.
- If there is only background noise, third-party analysis or repeated news with no concrete novelty:
  market_impact=LOW, overall_sentiment close to 0.0, recommended_action_bias=HOLD, avoid_trading=false.
- overall_sentiment reflects the NET directional tone of FRESH news (-1 very bearish to +1 very bullish; 0 = neutral or no novelty).
- avoid_trading=true ONLY for a CONFIRMED adverse systemic event (major hack, depeg, unexpected regulatory shock). In no other case.
- verified_catalyst=true only if there is a concrete, verifiable event with an identifiable source.
- catalyst_veracity 0.9+ requires a primary or official source; 0.7 requires multiple reputable outlets; below 0.7 must leave verified_catalyst=false.
- If there is no clear catalyst, use HOLD, verified_catalyst=false and catalyst_veracity=0.0.
- Do not invent sources. Include only URLs consulted or cited by the search."""

        try:
            if "search-preview" in self.model:
                return self._analyze_with_chat_search(self.model, prompt)

            response = self.client.responses.create(
                model=self.model,
                tools=[{"type": "web_search"}],
                tool_choice="auto",
                include=["web_search_call.action.sources"],
                input=prompt,
            )
            return self._parse_context(response.output_text)
        except Exception as e:
            print(f"[WebSearchAgent] Error en GPT web search ({self.model}): {e}")
            if self.fallback_model and self.fallback_model != self.model:
                try:
                    print(f"[WebSearchAgent] Reintentando con fallback {self.fallback_model}")
                    return self._analyze_with_chat_search(self.fallback_model, prompt)
                except Exception as e2:
                    print(f"[WebSearchAgent] Fallback GPT web search failed: {e2}")
            return self._default_context()

    def _analyze_with_chat_search(self, model: str, prompt: str) -> dict:
        response = self.client.chat.completions.create(
            model=model,
            web_search_options={},
            max_tokens=1200,
            messages=[
                {
                    "role": "system",
                    "content": "Respond only with valid JSON. Do not wrap it in markdown.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return self._parse_context(response.choices[0].message.content)

    def _parse_context(self, text: str) -> dict:
        text = (text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        elif "{" in text and "}" in text:
            text = text[text.index("{"):text.rindex("}") + 1]

        context = json.loads(text)
        default = self._default_context()
        default.update(context)
        default["asset_scores"].setdefault("BTCUSDT", 0.0)
        # Guardarraíl: un "impacto HIGH" sin catalizador verificado es telón de fondo,
        # no un evento accionable. Se degrada para que no frene al decisor por defecto.
        if default.get("market_impact") == "HIGH" and not default.get("verified_catalyst"):
            default["market_impact"] = "LOW"

        # Guardrail: avoid_trading is reserved for real SYSTEMIC EMERGENCIES
        # (hack, exploit, depeg, halt, insolvency, flash crash). A bearish/bullish bias
        # is NOT a reason to halt everything — the model can trade the direction (incl. SHORT).
        # If the reason is not systemic, the brake is released and the news stays as directional context.
        if default.get("avoid_trading"):
            reason = (default.get("avoid_reason") or "").lower()
            systemic_kw = (
                "hack", "exploit", "depeg", "insolv", "halt", "suspend",
                "flash crash", "collapse", "bankrupt", "attack", "breach",
                "freeze", "mass liquidation", "outage", "exploit",
            )
            if not any(k in reason for k in systemic_kw):
                default["avoid_trading"] = False
                default["avoid_reason"] = ""
        return default

    def _default_context(self) -> dict:
        return {
            "overall_sentiment": 0.0,
            "market_impact": "LOW",
            "risk_level": "MEDIUM",
            "geopolitical_summary": "No data available",
            "crypto_summary": "No data available",
            "key_events": [],
            "asset_scores": {"BTCUSDT": 0.0},
            "recommended_asset": "BTCUSDT",
            "recommended_action_bias": "HOLD",
            "confidence": 0.0,
            "avoid_trading": False,
            "avoid_reason": "",
            "verified_catalyst": False,
            "catalyst_direction": "NEUTRAL",
            "catalyst_veracity": 0.0,
            "catalyst_evidence": "",
            "sources": [],
        }

    def save_to_memory(self, context: dict):
        if not self.memory:
            return
        summary = (
            f"NEWS INTEL [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC] | "
            f"Sentimiento: {context['overall_sentiment']:+.2f} | "
            f"Impacto: {context['market_impact']} | "
            f"Riesgo: {context['risk_level']} | "
            f"Asset: {context['recommended_asset']} | "
            f"Sesgo: {context['recommended_action_bias']} | "
            f"Geo: {context['geopolitical_summary']} | "
            f"Crypto: {context['crypto_summary']} | "
            f"Eventos: {'; '.join(context['key_events'])}"
        )
        try:
            self.memory.store(
                wing="news-intel",
                content=summary,
                metadata={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sentiment": context["overall_sentiment"],
                    "impact": context["market_impact"],
                    "avoid_trading": context["avoid_trading"],
                },
            )
        except Exception as e:
            print(f"[WebSearchAgent] Error guardando en MemPalace: {e}")

    def get_latest_context(self) -> dict:
        if not self.latest_context:
            return self._default_context()
        return self.latest_context

    async def run_cycle(self):
        print(f"\n[WebSearchAgent] Ciclo GPT web search -- {datetime.now(timezone.utc).isoformat()}")
        try:
            context = await asyncio.to_thread(self.analyze_with_gpt_search)
            self.latest_context = context
            self.save_to_memory(context)

            print(
                f"[WebSearchAgent] Sentimiento: {context['overall_sentiment']:+.2f} | "
                f"Impacto: {context['market_impact']} | "
                f"Asset: {context['recommended_asset']} | "
                f"Sesgo: {context['recommended_action_bias']}"
            )
            if context.get("avoid_trading"):
                print(f"[WebSearchAgent] AVOID TRADING: {context['avoid_reason']}")

        except Exception as e:
            print(f"[WebSearchAgent] Error en ciclo: {e}")

    async def start(self):
        print(f"[WebSearchAgent] Iniciado. Interval: {self.interval_seconds}s")
        while True:
            await self.run_cycle()
            await asyncio.sleep(self.interval_seconds)
