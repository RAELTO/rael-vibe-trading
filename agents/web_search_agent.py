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
        prompt = f"""Eres un analista de riesgo macro, regulatorio y on-chain para un sistema de daytrading de Bitcoin futures (BTCUSDT).

Busca en la web informacion reciente y verificable sobre:
- Bitcoin, BTCUSDT, ETF spot de Bitcoin, flows de BlackRock/Fidelity/IBIT/FBTC.
- Regulacion crypto relevante en Estados Unidos y mercados principales.
- Hacks, insolvencias, depegs de stablecoins, liquidaciones o eventos sistemicos.
- Fed, tasas, inflacion, dolar, riesgo macro y geopolítica con impacto directo en BTC.
- Datos on-chain/noticias de whales, miners, hashrate o exchange reserves solo si vienen de fuentes serias.

Fecha/hora UTC actual: {datetime.now(timezone.utc).isoformat()}
Prioriza hasta {self.max_searches} fuentes recientes y confiables.

Tu tarea principal es detectar CATALIZADORES VERIFICABLES de alto impacto: eventos concretos con evidencia real que historicamente pueden mover BTC de forma significativa.

Ejemplos que califican:
- Un gobierno, regulador o empresa importante anuncia una accion oficial sobre BTC.
- La SEC, CFTC, Fed u otro regulador anuncia algo inesperado.
- Un ETF tiene flujo extraordinario confirmado por fuente seria.
- Un exchange importante sufre hack, insolvencia o interrupcion confirmada.
- Un stablecoin relevante pierde paridad de forma confirmada.

No califican como catalizador:
- Predicciones de precio, posts virales, rumores o analisis tecnico de terceros.
- Noticias repetidas sin novedad concreta.
- Movimiento de precio sin causa verificable.

Responde UNICAMENTE con JSON valido, sin markdown, con esta estructura exacta:
{{
  "overall_sentiment": 0.0,
  "market_impact": "HIGH|MEDIUM|LOW",
  "risk_level": "HIGH|MEDIUM|LOW",
  "geopolitical_summary": "Resumen de 2 oraciones sobre macro relevante para BTC",
  "crypto_summary": "Resumen de 2 oraciones sobre noticias especificas de Bitcoin",
  "key_events": ["evento1", "evento2", "evento3"],
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
  "catalyst_evidence": "Evento concreto y fuentes que lo confirman, o vacio si no hay catalizador",
  "sources": ["https://fuente1", "https://fuente2"]
}}

Reglas:
- Considera SOLO noticias de las ULTIMAS 48 HORAS. Ignora el telon de fondo ya conocido
  (aprobacion historica de ETFs spot, adopcion institucional general, regulacion ya vigente):
  eso es CONTEXTO, no un catalizador. No lo reportes como evento ni infles el impacto por ello.
- market_impact=HIGH SOLO si verified_catalyst=true (evento fresco, fechado, con fuente seria).
  NUNCA pongas market_impact=HIGH con verified_catalyst=false. Ante la duda usa LOW o MEDIUM.
- Si solo hay ruido de fondo, analisis de terceros o noticias repetidas sin novedad concreta:
  market_impact=LOW, overall_sentiment cercano a 0.0, recommended_action_bias=HOLD, avoid_trading=false.
- overall_sentiment refleja el tono direccional NETO de noticias FRESCAS (-1 muy bajista a +1 muy alcista; 0 = neutral o sin novedad).
- avoid_trading=true SOLO ante un evento sistemico adverso CONFIRMADO (hack mayor, depeg, shock regulatorio inesperado). En ningun otro caso.
- verified_catalyst=true solo si hay un evento concreto verificable con fuente identificable.
- catalyst_veracity 0.9+ requiere fuente primaria u oficial; 0.7 requiere multiples medios serios; menos de 0.7 debe dejar verified_catalyst=false.
- Si no hay catalizador claro, usa HOLD, verified_catalyst=false y catalyst_veracity=0.0.
- No inventes fuentes. Incluye solo URLs consultadas o citadas por la busqueda."""

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

        # Guardarraíl: avoid_trading se reserva para EMERGENCIAS SISTÉMICAS reales
        # (hack, exploit, depeg, halt, insolvencia, flash crash). Un sesgo bajista/alcista
        # NO es motivo para frenar todo — el modelo puede operar la dirección (incl. SHORT).
        # Si el motivo no es sistémico, se libera el freno y la noticia queda como contexto direccional.
        if default.get("avoid_trading"):
            reason = (default.get("avoid_reason") or "").lower()
            systemic_kw = (
                "hack", "exploit", "depeg", "desancl", "insolv", "halt", "suspens",
                "flash crash", "colaps", "quiebra", "bancarrota", "ataque", "breach",
                "freeze", "congel", "liquidación masiva", "liquidacion masiva",
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
            "geopolitical_summary": "Sin datos disponibles",
            "crypto_summary": "Sin datos disponibles",
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
