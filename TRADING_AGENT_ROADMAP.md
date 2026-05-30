# 🤖 Multi-Agent Trading System — Hoja de Ruta de Implementación

> **Para Claude Code:** Este documento es la guía maestra del proyecto. Léelo completo antes de ejecutar cualquier paso. Cada fase debe completarse y verificarse antes de pasar a la siguiente. Ante errores, diagnostica primero y reporta antes de continuar.

---

## 📋 Resumen del Proyecto

Sistema multi-agente de trading que combina un modelo de lenguaje local (AMD GPU vía Vulkan) con APIs cloud (Claude Code CLI, Gemini, GPT-5.4 Mini) para ejecutar estrategias de daytrading básico en la **Binance Testnet**. Los agentes comparten memoria persistente vía **MemPalace** y usan las skills financieras de **Vibe-Trading** para análisis cuantitativo.

**Hardware del sistema:**
- CPU: AMD Ryzen 7 5700X (8c/16t)
- GPU: AMD RX 9060 XT 16GB VRAM (RDNA4 / gfx1201)
- RAM: 32GB DDR4 3200MHz
- SSD libre: ~350GB (NVMe 5000 MT/s)
- OS: Windows 11

**✅ MODELO LOCAL — INSTALADO Y VERIFICADO (13 abril 2026):**
- Ollama instalado en Windows
- `OLLAMA_VULKAN=1` configurado como variable de sistema
- ROCm intentó iniciar → filtrado correctamente (esperado para gfx1201 en Windows)
- **Vulkan tomó el control: `library=Vulkan` · `AMD Radeon RX 9060 XT` · `total=15.9 GiB`**
- Modelo `qwen2.5:14b` descargado y corriendo
- **37/37 capas offloadeadas a GPU · 9.0 GiB en VRAM · Flash Attention activado**
- Tiempo de respuesta verificado: ~7.5s por análisis de trading completo
- Respuesta JSON válida confirmada en prueba real de trading

---

## 🗂️ Stack Tecnológico

| Capa | Tecnología | Rol | Costo |
|------|-----------|-----|-------|
| **Modelo local** | Ollama + Qwen2.5:14b ✅ | Monitoreo, routing, ejecución, tareas repetitivas | $0 (GPU local) |
| **Modelo cloud análisis** | Claude Code CLI (Pro $20) | Análisis profundo cada ~35min vía subprocess | $20/mes (ya tienes) |
| **Modelo cloud validación** | Gemini 2.5 Flash-Lite (API free) | Validación cruzada, segunda opinión | **$0** (1000 req/día) |
| **Modelo cloud auxiliar** | GPT-5.4 Mini (API $40 budget) | Análisis sentimiento, noticias, decisiones | ~$0.20/mes |
| **Skills financieras** | Vibe-Trading (HKUDS) | Backtesting, análisis técnico, quant tools | $0 (open source) |
| **Memoria persistente** | MemPalace | Vector store ChromaDB + SQLite knowledge graph | $0 (local) |
| **Orquestación** | Python + LangGraph | DAG multi-agente, routing, coordinación | $0 |
| **Mensajería agentes** | Redis / Memurai | Cola de mensajes inter-agente | $0 |
| **Ejecución** | python-binance (ccxt) | Binance Testnet API | $0 (testnet) |
| **Backend API** | FastAPI | Servidor central del sistema | $0 |
| **Frontend monitor** | React + Vite | Dashboard en tiempo real | $0 |

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    CAPA DE MEMORIA                          │
│              MemPalace (MCP Server)                         │
│    ChromaDB (vector) + SQLite (knowledge graph temporal)    │
└──────────────────────┬──────────────────────────────────────┘
                       │ MCP tools (19 disponibles)
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  ORCHESTRATOR CENTRAL                        │
│              FastAPI + LangGraph DAG                        │
│                                                             │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │   ROUTER    │   │   DECIDER    │   │   RISK MANAGER  │  │
│  │ (clasifica  │   │ (vota y      │   │ (validación     │  │
│  │  la tarea)  │   │  consensua)  │   │  pre-ejecución) │  │
│  └──────┬──────┘   └──────┬───────┘   └────────┬────────┘  │
└─────────┼────────────────┼───────────────────────┼──────────┘
          │                │                       │
    ┌─────▼──────┐   ┌─────▼────────────┐   ┌─────▼──────┐
    │ LOCAL AGENT│   │  CLOUD AGENTS    │   │  EXECUTOR  │
    │            │   │                  │   │            │
    │ Ollama     │   │ ┌──────────────┐ │   │ Binance    │
    │ Qwen2.5-14B│   │ │Claude Sonnet │ │   │ Testnet    │
    │            │   │ ├──────────────┤ │   │ API        │
    │ Tareas:    │   │ │Gemini 1.5Pro │ │   │            │
    │ - Routing  │   │ ├──────────────┤ │   │ Tareas:    │
    │ - Resumen  │   │ │GPT-4o API    │ │   │ - Buy/Sell │
    │ - Monitoreo│   │ └──────────────┘ │   │ - Balance  │
    │ - Memoria  │   │                  │   │ - Orders   │
    └─────┬──────┘   │ Tareas:          │   └─────┬──────┘
          │          │ - Análisis quant │         │
          │          │ - Estrategias    │         │
          │          │ - Sentimiento    │         │
          │          └─────┬────────────┘         │
          │                │                      │
    ┌─────▼────────────────▼──────────────────────▼──────┐
    │              VIBE-TRADING SKILLS LAYER               │
    │  backtest | technical_analysis | options | factor   │
    │  pattern_recognition | market_data | web_search*   │
    └─────────────────────────────────────────────────────┘
     (* web_search de VT = reactivo por skill, no proactivo)
                       │
    ┌──────────────────▼──────────────────────────────────────┐
    │          WEB SEARCH AGENT (proactivo, autónomo)         │
    │  DuckDuckGo + RSS feeds + Tavily (opt) cada 30min       │
    │  Geopolítica | Macro | Crypto news | On-chain           │
    │  Output: news_context{score, impact, affected_assets}   │
    │  Persiste en MemPalace wing: news-intel                 │
    └──────────────────────────┬──────────────────────────────┘
                               │ inyectado en cada ciclo
    ┌──────────────────────────▼──────────────────────────────┐
    │              REACT DASHBOARD (Monitor)                   │
    │  WebSocket real-time | trades | agent logs | P&L | News │
    └─────────────────────────────────────────────────────────┘
```

### Protocolo de comunicación inter-agente

```
MENSAJE ESTÁNDAR (JSON via Redis)
{
  "msg_id": "uuid4",
  "from": "orchestrator | local_agent | cloud_agent_X | executor",
  "to": "orchestrator | local_agent | cloud_agent_X | executor | broadcast",
  "type": "TASK | RESULT | VOTE | DECISION | ERROR | MEMORY_QUERY",
  "priority": 1-5,
  "payload": { ... },
  "context_id": "session-uuid",
  "timestamp": "ISO8601"
}
```

### Sistema de toma de decisiones (Voting)

```
WebSearchAgent (loop 30min) →
  └─ Recopila noticias geopolíticas + crypto + on-chain
      └─ LLM extrae sentimiento + impacto + asset recomendado
          └─ Guarda en MemPalace wing: news-intel
              └─ [Cada 5min] Orchestrator consulta news_context
                  └─ Si avoid_trading=true → ciclo cancelado
                  └─ Si no → Vibe-Trading genera análisis técnico
                      └─ Cloud agents votan: BUY | SELL | HOLD (con confianza 0-1)
                      └─ news_context pondera y ajusta scores
                          └─ Local agent + Decider consolida
                              └─ Risk Manager valida
                                  └─ Si consenso ≥ 0.65 → Executor envía orden
                                      └─ MemPalace registra decisión + outcome
```

---

## 📁 Estructura de Carpetas del Proyecto

```
trading-agent/
├── TRADING_AGENT_ROADMAP.md     ← Este archivo
├── .env                          ← Keys (NO COMMITEAR)
├── .env.example                  ← Template sin valores reales
├── .gitignore
├── requirements.txt
├── docker-compose.yml            ← Redis + servicios opcionales
│
├── core/
│   ├── orchestrator.py           ← LangGraph DAG central
│   ├── router.py                 ← Clasificador de tareas
│   ├── decider.py                ← Motor de votación/consenso
│   ├── risk_manager.py           ← Validación pre-ejecución
│   └── message_bus.py            ← Wrapper Redis pub/sub
│
├── agents/
│   ├── local_agent.py            ← Wrapper Ollama (Qwen2.5-14B)
│   ├── claude_agent.py           ← Wrapper Anthropic API
│   ├── gemini_agent.py           ← Wrapper Google Generative AI
│   ├── gpt_agent.py              ← Wrapper OpenAI API
│   ├── web_search_agent.py       ← Agente de búsqueda proactiva de noticias
│   └── base_agent.py             ← Clase base abstracta
│
├── memory/
│   ├── mempalace_client.py       ← Cliente MCP de MemPalace
│   ├── session_manager.py        ← Gestión de sesiones de trading
│   └── hooks.py                  ← Auto-save de decisiones/trades
│
├── skills/
│   ├── vibe_trading_client.py    ← Wrapper de skills financieras
│   ├── technical_analysis.py     ← Wrappers específicos de skills
│   └── market_data.py            ← Acceso a datos de mercado
│
├── execution/
│   ├── binance_testnet.py        ← Cliente Binance Testnet
│   ├── order_manager.py          ← Gestión de órdenes activas
│   └── portfolio_tracker.py      ← Estado del portafolio
│
├── api/
│   ├── main.py                   ← FastAPI server
│   ├── routes/
│   │   ├── agents.py             ← Endpoints de agentes
│   │   ├── trades.py             ← Endpoints de trading
│   │   └── memory.py             ← Endpoints de memoria
│   └── websocket.py              ← Conexión tiempo real
│
└── dashboard/
    ├── src/
    │   ├── App.tsx
    │   ├── components/
    │   │   ├── AgentLog.tsx      ← Log de decisiones de agentes
    │   │   ├── PortfolioView.tsx ← Estado del portafolio
    │   │   ├── TradeHistory.tsx  ← Historial de trades
    │   │   └── MarketChart.tsx   ← Gráfico en tiempo real
    │   └── hooks/
    │       └── useWebSocket.ts
    └── package.json
```

---

## ⚙️ FASE 0 — Preparación del entorno Windows

### 0.1 Verificar Python

```powershell
python --version   # Necesario: 3.11+
```

Si no está instalado, descargar de python.org (versión 3.11.x). Asegurarse de marcar "Add to PATH" durante instalación.

### 0.2 Verificar Node.js (para dashboard)

```powershell
node --version   # Necesario: 18+
```

### 0.3 Instalar Redis para Windows

Usar la distribución de Memurai (compatible con Redis) o WSL2:

**Opción A — Memurai (recomendado para Windows nativo):**
```
https://www.memurai.com/get-memurai
```
Instalar y verificar:
```powershell
memurai --version
```

**Opción B — Docker Desktop:**
```powershell
docker run -d -p 6379:6379 redis:alpine
```

### 0.4 Crear entorno virtual del proyecto

```powershell
mkdir trading-agent
cd trading-agent
python -m venv venv
.\venv\Scripts\activate
```

---

## ✅ FASE 1 — Setup del Modelo Local — COMPLETADA (13 abril 2026)

> **Esta fase está 100% completada y verificada. No ejecutar de nuevo.**

### Resultados verificados

| Check | Estado | Detalle |
|---|---|---|
| Ollama instalado | ✅ | Windows, servicio activo |
| Variables Vulkan | ✅ | `OLLAMA_VULKAN=1`, `OLLAMA_FLASH_ATTENTION=1` en variables de sistema |
| GPU detectada | ✅ | `AMD Radeon RX 9060 XT` · `library=Vulkan` · `15.9 GiB total` |
| ROCm (esperado fallo) | ✅ | `filtering device which didn't fully initialize` — comportamiento correcto |
| Modelo descargado | ✅ | `qwen2.5:14b` — 8.5GB en disco |
| GPU offload | ✅ | **37/37 capas en GPU** · `9.0 GiB VRAM` · Flash Attention ON |
| Respuesta JSON | ✅ | `{"vote":"SELL","confidence":0.8,"reasoning":"..."}` — formato correcto |
| Tiempo respuesta | ✅ | ~7.5 segundos por análisis completo |
| VRAM libre | ✅ | 6.9 GiB disponibles para KV cache y contexto largo |

### Variables de entorno configuradas (ya activas)

```
OLLAMA_VULKAN=1
OLLAMA_FLASH_ATTENTION=1
OLLAMA_DEBUG=1         ← Opcional, se puede quitar en producción
```

### Comando de verificación rápida

Si en algún momento necesitas verificar que el modelo sigue activo:

```powershell
ollama list
# Debe mostrar: qwen2.5:14b
```

```powershell
# En PowerShell (no CMD — evita problemas con comillas)
ollama run qwen2.5:14b "Di SISTEMA_OK si puedes responder"
# Debe responder: SISTEMA_OK
```

---

## ⚙️ FASE 2 — MemPalace (Memoria Persistente)

### 2.1 Instalar MemPalace

```powershell
pip install chromadb pyyaml
git clone https://github.com/milla-jovovich/mempalace.git
cd mempalace
pip install -e .
```

### 2.2 Inicializar la estructura de memoria

```powershell
mempalace init
```

Esto crea la estructura en `~/.mempalace/`. Configurar el archivo `identity.txt`:

```
# ~/.mempalace/identity.txt
Soy el sistema de trading multi-agente corriendo en Windows.
Proyecto: daytrading en Binance Testnet con BTC/USDT y ETH/USDT.
Estrategia base: análisis técnico + consenso multi-agente.
Risk tolerance: conservador (máx 2% por operación).
```

### 2.3 Crear estructura de wings para trading

```powershell
mempalace create-wing trading-decisions
mempalace create-wing market-analysis
mempalace create-wing agent-logs
mempalace create-wing portfolio-state
```

### 2.4 Configurar el servidor MCP de MemPalace

Crear archivo `mempalace_mcp_config.json`:

```json
{
  "mcpServers": {
    "mempalace": {
      "command": "python",
      "args": ["-m", "mempalace.mcp_server"],
      "env": {
        "MEMPALACE_WING": "trading-decisions"
      }
    }
  }
}
```

### 2.5 Verificar funcionamiento

```python
# test_memory.py
from mempalace import MemPalaceClient

client = MemPalaceClient()

# Guardar una decisión de trading de prueba
client.store(
    wing="trading-decisions",
    content="TEST: BTC comprado a $85,000 basado en RSI=28 + MACD cruce alcista. Agentes votaron 3/3 BUY.",
    metadata={"pair": "BTCUSDT", "action": "BUY", "confidence": 0.87}
)

# Recuperar
results = client.search("decisiones BTC", wing="trading-decisions")
print(results)
```

---

## ⚙️ FASE 3 — Vibe-Trading (Skills Financieras)

### 3.1 Instalar Vibe-Trading

```powershell
pip install vibe-trading-ai
```

### 3.2 Configurar providers LLM

```powershell
vibe-trading init
```

Durante el proceso interactivo configurar:

```
LLM Provider: anthropic
API Key: [tu Claude API key]
Default model: claude-sonnet-4-20250514
Market data: akshare (gratis, crypto+acciones)
```

También crear/editar `.env` en la carpeta de vibe-trading:

```env
# LLM Principal (análisis pesado)
ANTHROPIC_API_KEY=sk-ant-...

# LLM Secundario
GOOGLE_API_KEY=...
OPENAI_API_KEY=sk-...

# Mercados
DEFAULT_MARKET=crypto
DEFAULT_SYMBOLS=BTCUSDT,ETHUSDT
```

### 3.3 Verificar skills disponibles

```powershell
vibe-trading --list-skills
vibe-trading --swarm-presets
```

### 3.4 Testear un skill de análisis técnico

```powershell
vibe-trading run-skill technical-basic --symbol BTCUSDT --interval 1h
```

### 3.5 Testear backtesting

```powershell
vibe-trading backtest --symbol BTCUSDT --strategy rsi-momentum --period 30d
```

---

## ⚙️ FASE 3.5 — Web Search Agent (Inteligencia de Mercado Proactiva)

> **Por qué no alcanza el `web_search` de Vibe-Trading:** La herramienta `web_search` incluida en Vibe-Trading v0.1.4 es **reactiva** — solo se ejecuta cuando un skill la llama explícitamente durante un análisis. No corre de forma autónoma, no monitorea noticias en un loop, y no alimenta el contexto de votación de los otros agentes. Se necesita un agente dedicado e independiente para esto.

### 3.5.1 ¿Qué hace este agente?

El `WebSearchAgent` corre en su propio loop (cada 30 minutos por defecto), recopila noticias de múltiples fuentes, las procesa con un LLM para extraer señales de mercado, y almacena el resultado en MemPalace bajo el wing `news-intel`. Cada vez que el Orchestrator lanza un ciclo de análisis, consulta MemPalace y obtiene el `news_context` más reciente para inyectarlo en el prompt de todos los agentes votantes.

### 3.5.2 Fuentes de información y queries

```
CATEGORÍA: GEOPOLÍTICA (impacto indirecto en crypto vía risk-off/risk-on)
  Queries programadas:
  - "Iran Israel conflict latest 2026"
  - "Trump executive orders economy sanctions"
  - "USA China trade war tariffs"
  - "Middle East tensions oil price"
  - "Fed interest rates decision"
  - "US dollar index DXY"

CATEGORÍA: CRYPTO MARKET (impacto directo)
  Queries programadas:
  - "Bitcoin BTC price news today"
  - "Ethereum ETH major update"
  - "crypto regulation SEC CFTC"
  - "crypto exchange hack exploit"
  - "bitcoin ETF institutional buy"
  - "stablecoin USDT USDC news"

CATEGORÍA: ON-CHAIN / MACRO CRYPTO
  Fuentes RSS directas:
  - CoinDesk RSS: https://www.coindesk.com/arc/outboundfeeds/rss/
  - CoinTelegraph RSS: https://cointelegraph.com/rss
  - The Block RSS: https://www.theblock.co/rss.xml
  - CryptoSlate RSS: https://cryptoslate.com/feed/

CATEGORÍA: ASSET SELECTION (multi-asset dinámico)
  El agente evalúa qué par operar en el siguiente ciclo:
  - Busca noticias positivas/negativas para BTC, ETH, BNB, SOL
  - Asigna "opportunity score" por asset
  - Recomienda el par con mayor potencial al Orchestrator
```

### 3.5.3 Instalar dependencias

```powershell
pip install duckduckgo-search feedparser httpx beautifulsoup4 lxml
```

Opcional (Tavily API — free tier 1000 req/mes):
```powershell
pip install tavily-python
```
Registro gratuito en `https://tavily.com`

### 3.5.4 Implementación del WebSearchAgent

Crear `agents/web_search_agent.py`:

```python
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import List
from duckduckgo_search import DDGS
import feedparser
import httpx
from anthropic import Anthropic

class NewsItem:
    def __init__(self, title: str, body: str, url: str, source: str, published: str = None):
        self.title = title
        self.body = body
        self.url = url
        self.source = source
        self.published = published or datetime.utcnow().isoformat()

class WebSearchAgent:
    """
    Agente proactivo de búsqueda de noticias.
    Corre en loop independiente. No vota directamente — provee contexto.
    """

    # Queries agrupadas por categoría
    QUERIES = {
        "geopolitics": [
            "Iran Israel conflict latest",
            "Trump executive order economy 2026",
            "USA China tariffs sanctions",
            "Federal Reserve interest rates",
            "global recession risk",
        ],
        "crypto_market": [
            "Bitcoin BTC price news",
            "Ethereum ETH major news",
            "crypto regulation 2026",
            "crypto exchange hack",
            "bitcoin institutional adoption",
        ],
        "on_chain": [
            "Bitcoin whale movement exchange",
            "crypto stablecoin depeg",
            "DeFi exploit hack today",
            "Bitcoin ETF flow BlackRock",
        ],
    }

    # Feeds RSS confiables
    RSS_FEEDS = [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ]

    # Assets que el agente puede recomendar al orchestrator
    TRACKED_ASSETS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]

    def __init__(self, memory_client, llm_client: Anthropic = None):
        self.memory = memory_client
        self.llm = llm_client or Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.latest_context = {}      # Cache en memoria entre búsquedas
        self.interval_seconds = int(os.getenv("NEWS_INTERVAL_SECONDS", 1800))  # 30min

    # ─────────────────────────────────────────────────────────────
    # RECOLECCIÓN DE NOTICIAS
    # ─────────────────────────────────────────────────────────────

    def search_duckduckgo(self, query: str, max_results: int = 5) -> List[NewsItem]:
        """Búsqueda web gratuita sin API key."""
        items = []
        try:
            with DDGS() as ddgs:
                results = ddgs.news(query, max_results=max_results, timelimit="d")
                for r in results:
                    items.append(NewsItem(
                        title=r.get("title", ""),
                        body=r.get("body", ""),
                        url=r.get("url", ""),
                        source=r.get("source", "web"),
                        published=r.get("date", ""),
                    ))
        except Exception as e:
            print(f"[WebSearchAgent] DuckDuckGo error para '{query}': {e}")
        return items

    def fetch_rss(self, feed_url: str, max_items: int = 8) -> List[NewsItem]:
        """Lee RSS sin API key."""
        items = []
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_items]:
                items.append(NewsItem(
                    title=entry.get("title", ""),
                    body=entry.get("summary", ""),
                    url=entry.get("link", ""),
                    source=feed.feed.get("title", feed_url),
                    published=entry.get("published", ""),
                ))
        except Exception as e:
            print(f"[WebSearchAgent] RSS error para {feed_url}: {e}")
        return items

    def collect_all_news(self) -> List[NewsItem]:
        """Recopila noticias de todas las fuentes."""
        all_items = []

        # DuckDuckGo por categoría
        for category, queries in self.QUERIES.items():
            for query in queries:
                items = self.search_duckduckgo(query, max_results=3)
                all_items.extend(items)

        # RSS feeds
        for feed_url in self.RSS_FEEDS:
            items = self.fetch_rss(feed_url)
            all_items.extend(items)

        print(f"[WebSearchAgent] {len(all_items)} noticias recopiladas")
        return all_items

    # ─────────────────────────────────────────────────────────────
    # ANÁLISIS Y SCORING CON LLM
    # ─────────────────────────────────────────────────────────────

    def analyze_with_llm(self, news_items: List[NewsItem]) -> dict:
        """
        Usa Claude para extraer señales de trading del conjunto de noticias.
        Devuelve un dict estructurado con sentimiento, impacto y asset recomendado.
        """
        # Preparar resumen de noticias para el prompt
        news_text = "\n\n".join([
            f"[{item.source}] {item.title}\n{item.body[:200]}"
            for item in news_items[:30]  # Limitar para no exceder tokens
        ])

        prompt = f"""Eres un analista de riesgo geopolítico y macro para un sistema de trading de crypto.

Analiza las siguientes noticias recientes y extrae señales de mercado para trading de crypto (BTC, ETH, BNB, SOL).

NOTICIAS:
{news_text}

Responde ÚNICAMENTE con un JSON válido con esta estructura exacta:
{{
  "overall_sentiment": -1.0,          // -1.0 (muy bearish) a +1.0 (muy bullish) para crypto
  "market_impact": "HIGH|MEDIUM|LOW", // Impacto estimado en el mercado
  "risk_level": "HIGH|MEDIUM|LOW",    // Nivel de riesgo geopolítico/macro actual
  "geopolitical_summary": "Resumen de 2 oraciones sobre la situación geopolítica y su efecto en crypto",
  "crypto_summary": "Resumen de 2 oraciones sobre noticias específicas de crypto",
  "key_events": ["evento1", "evento2", "evento3"],  // Máximo 3 eventos más relevantes
  "asset_scores": {{                  // Score por asset de -1.0 a +1.0
    "BTCUSDT": 0.0,
    "ETHUSDT": 0.0,
    "BNBUSDT": 0.0,
    "SOLUSDT": 0.0
  }},
  "recommended_asset": "BTCUSDT",    // Asset con mejor oportunidad ahora
  "recommended_action_bias": "BUY|SELL|HOLD|AVOID",  // Sesgo general recomendado
  "confidence": 0.0,                 // Confianza en el análisis 0.0-1.0
  "avoid_trading": false,            // true si el contexto es demasiado incierto/riesgoso
  "avoid_reason": ""                 // Si avoid_trading=true, explicar por qué
}}"""

        try:
            response = self.llm.messages.create(
                model="claude-haiku-4-5-20251001",  # Haiku: más barato para esta tarea
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            return json.loads(response.content[0].text)
        except Exception as e:
            print(f"[WebSearchAgent] Error en análisis LLM: {e}")
            return self._default_context()

    def _default_context(self) -> dict:
        """Contexto neutro en caso de error."""
        return {
            "overall_sentiment": 0.0,
            "market_impact": "LOW",
            "risk_level": "MEDIUM",
            "geopolitical_summary": "Sin datos disponibles",
            "crypto_summary": "Sin datos disponibles",
            "key_events": [],
            "asset_scores": {a: 0.0 for a in self.TRACKED_ASSETS},
            "recommended_asset": "BTCUSDT",
            "recommended_action_bias": "HOLD",
            "confidence": 0.0,
            "avoid_trading": False,
            "avoid_reason": "",
        }

    # ─────────────────────────────────────────────────────────────
    # PERSISTENCIA EN MEMPALACE
    # ─────────────────────────────────────────────────────────────

    def save_to_memory(self, context: dict):
        """Guarda el análisis en MemPalace wing: news-intel."""
        summary = (
            f"NEWS INTEL [{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC] | "
            f"Sentimiento: {context['overall_sentiment']:+.2f} | "
            f"Impacto: {context['market_impact']} | "
            f"Riesgo geopolítico: {context['risk_level']} | "
            f"Asset recomendado: {context['recommended_asset']} | "
            f"Sesgo: {context['recommended_action_bias']} | "
            f"Geopolítica: {context['geopolitical_summary']} | "
            f"Crypto: {context['crypto_summary']} | "
            f"Eventos clave: {'; '.join(context['key_events'])}"
        )
        try:
            self.memory.store(
                wing="news-intel",
                content=summary,
                metadata={
                    "timestamp": datetime.utcnow().isoformat(),
                    "sentiment": context["overall_sentiment"],
                    "impact": context["market_impact"],
                    "avoid_trading": context["avoid_trading"],
                }
            )
        except Exception as e:
            print(f"[WebSearchAgent] Error al guardar en MemPalace: {e}")

    # ─────────────────────────────────────────────────────────────
    # INTERFAZ PÚBLICA PARA EL ORCHESTRATOR
    # ─────────────────────────────────────────────────────────────

    def get_latest_context(self) -> dict:
        """
        El Orchestrator llama esto antes de cada ciclo de análisis.
        Devuelve el último contexto de noticias disponible (desde cache).
        """
        if not self.latest_context:
            return self._default_context()
        return self.latest_context

    # ─────────────────────────────────────────────────────────────
    # LOOP AUTÓNOMO
    # ─────────────────────────────────────────────────────────────

    async def run_cycle(self):
        """Un ciclo completo: recopilar → analizar → guardar → actualizar cache."""
        print(f"\n[WebSearchAgent] Iniciando ciclo de búsqueda — {datetime.utcnow().isoformat()}")
        try:
            news_items = self.collect_all_news()
            if not news_items:
                print("[WebSearchAgent] Sin noticias recopiladas, usando contexto anterior")
                return

            context = self.analyze_with_llm(news_items)
            self.latest_context = context
            self.save_to_memory(context)

            print(f"[WebSearchAgent] Sentimiento: {context['overall_sentiment']:+.2f} | "
                  f"Impacto: {context['market_impact']} | "
                  f"Asset recomendado: {context['recommended_asset']}")

            if context.get("avoid_trading"):
                print(f"[WebSearchAgent] ⚠️  AVOID TRADING: {context['avoid_reason']}")

        except Exception as e:
            print(f"[WebSearchAgent] Error en ciclo: {e}")

    async def start(self):
        """Loop principal del agente de noticias."""
        print(f"[WebSearchAgent] Iniciado. Interval: {self.interval_seconds}s")
        while True:
            await self.run_cycle()
            await asyncio.sleep(self.interval_seconds)
```

### 3.5.5 Integrar el contexto de noticias en el Orchestrator

En `core/orchestrator.py`, agregar el WebSearchAgent al `__init__` y modificar `run_analysis_cycle`:

```python
# En __init__:
from agents.web_search_agent import WebSearchAgent
from anthropic import Anthropic

self.web_search_agent = WebSearchAgent(
    memory_client=self.memory,
    llm_client=Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
)

# En start(), arrancar el agente de noticias en paralelo:
async def start(self):
    print("Sistema de trading iniciado.")
    # Lanzar WebSearchAgent en paralelo al loop principal
    await asyncio.gather(
        self.web_search_agent.start(),    # Loop de noticias cada 30min
        self._trading_loop()             # Loop de trading cada 5min
    )

async def _trading_loop(self):
    while True:
        for symbol in TRADING_PAIRS:
            await self.run_analysis_cycle(symbol)
        await asyncio.sleep(ANALYSIS_INTERVAL_SECONDS)
```

En `run_analysis_cycle`, enriquecer el contexto con noticias:

```python
async def run_analysis_cycle(self, symbol: str):
    market_data = self.binance.get_market_data(symbol)

    # Recuperar contexto de noticias del WebSearchAgent
    news_context = self.web_search_agent.get_latest_context()

    # Si el agente de noticias dice AVOID — saltar este ciclo
    if news_context.get("avoid_trading"):
        print(f"CICLO CANCELADO por WebSearchAgent: {news_context['avoid_reason']}")
        return

    # Si el asset recomendado es diferente al actual, notificar
    recommended = news_context.get("recommended_asset", symbol)
    if recommended != symbol:
        print(f"[WebSearchAgent] Recomienda operar {recommended} en vez de {symbol}")

    context = {
        "recent_decisions": self.memory.search(
            f"decisiones {symbol}", wing="trading-decisions", top_k=3
        ),
        # NUEVO: contexto de noticias inyectado
        "news_sentiment": news_context.get("overall_sentiment", 0.0),
        "news_impact": news_context.get("market_impact", "LOW"),
        "geopolitical_summary": news_context.get("geopolitical_summary", ""),
        "crypto_news": news_context.get("crypto_summary", ""),
        "key_events": news_context.get("key_events", []),
        "news_bias": news_context.get("recommended_action_bias", "HOLD"),
        "asset_score": news_context.get("asset_scores", {}).get(symbol, 0.0),
    }
    # ... resto del ciclo sin cambios
```

### 3.5.6 Cómo el contexto de noticias afecta los votos

El `news_context` se inyecta en el prompt de **todos** los agentes votantes. Cada agente lo pondera junto con el análisis técnico. Además, el Decider aplica un **multiplicador de confianza** basado en el impacto:

```python
# En core/decider.py — agregar ajuste por news_impact
NEWS_IMPACT_MULTIPLIER = {
    "HIGH":   0.85,   # Alta incertidumbre → reducir confianza general
    "MEDIUM": 0.95,   # Incertidumbre moderada
    "LOW":    1.00,   # Sin ruido externo → confianza intacta
}

def decide(self, signals: List[TradingSignal], news_context: dict = None) -> dict:
    # ... lógica existente ...

    # Ajustar por impacto de noticias
    multiplier = 1.0
    if news_context:
        impact = news_context.get("market_impact", "LOW")
        multiplier = NEWS_IMPACT_MULTIPLIER.get(impact, 1.0)

        # Si el sesgo de noticias contradice la decisión → reducir confianza
        news_bias = news_context.get("recommended_action_bias", "HOLD")
        if news_bias == "AVOID":
            winning_score *= 0.70  # Penalización fuerte si noticias dicen evitar

    winning_score_adjusted = winning_score * multiplier

    return {
        "decision": winning_vote.value if winning_score_adjusted >= MIN_CONSENSUS else "HOLD",
        "consensus_score": winning_score_adjusted,
        "news_sentiment": news_context.get("overall_sentiment", 0.0) if news_context else 0.0,
        # ... resto del return
    }
```

### 3.5.7 Costo estimado del WebSearchAgent

| Componente | Costo | Detalle |
|---|---|---|
| DuckDuckGo Search | **Gratis** | Sin API key, sin límites oficiales |
| RSS Feeds | **Gratis** | CoinDesk, CoinTelegraph, etc. |
| Claude Haiku (análisis) | ~$0.003/ciclo | 1000 tokens × $0.003/1K |
| 48 ciclos/día | **~$0.14/día** | ~$4.2/mes adicional |
| Tavily API (opcional) | Gratis 1000 req/mes | Para búsquedas más precisas |

> El modelo `claude-haiku-4-5-20251001` se usa deliberadamente aquí (en lugar de Sonnet) para mantener el costo bajo. Es suficiente para clasificar noticias y no se necesita el análisis profundo que sí aporta Sonnet en las decisiones de trading.

### 3.5.8 Variables de entorno adicionales

Agregar al `.env`:

```env
# ===== WEB SEARCH AGENT =====
NEWS_INTERVAL_SECONDS=1800        # Cada 30 minutos (ajustable)
NEWS_MAX_RESULTS_PER_QUERY=3      # Resultados por query DuckDuckGo
TAVILY_API_KEY=tvly-...           # Opcional — registro gratis en tavily.com
NEWS_AVOID_THRESHOLD=-0.70        # Si sentimiento < -0.70 → avoid_trading automático
```

### 3.5.9 Checklist — WebSearchAgent

- [ ] `duckduckgo-search`, `feedparser`, `beautifulsoup4` instalados sin errores
- [ ] `search_duckduckgo("Bitcoin news")` retorna al menos 1 resultado
- [ ] `fetch_rss(COINDESK_URL)` retorna artículos
- [ ] `analyze_with_llm(items)` retorna JSON válido con todos los campos
- [ ] `save_to_memory()` guarda en MemPalace wing `news-intel` sin errores
- [ ] `get_latest_context()` retorna datos desde cache después del primer ciclo
- [ ] En el Orchestrator: `asyncio.gather()` corre ambos loops en paralelo sin bloquear
- [ ] El contexto de noticias aparece en los prompts de Claude y Gemini
- [ ] El Decider aplica el multiplicador correctamente (verificar con `market_impact="HIGH"`)
- [ ] En el Dashboard: el panel de noticias recibe actualizaciones vía WebSocket

---

## ⚙️ FASE 4 — Binance Testnet

### 4.1 Crear cuenta en Binance Testnet

1. Ir a `https://testnet.binance.vision/`
2. Login con GitHub
3. Generar API Key y Secret Key
4. Copiar ambas (solo se muestran una vez)

### 4.2 Configurar credenciales

En el archivo `.env` del proyecto:

```env
# BINANCE TESTNET (no usar keys de producción aquí)
BINANCE_TESTNET_API_KEY=tu_api_key_testnet
BINANCE_TESTNET_SECRET=tu_secret_testnet
BINANCE_TESTNET_BASE_URL=https://testnet.binance.vision
BINANCE_TESTNET=true

# PARES A OPERAR
TRADING_PAIRS=BTCUSDT,ETHUSDT

# GESTIÓN DE RIESGO
MAX_POSITION_SIZE_PERCENT=2.0    # Máx 2% del portafolio por operación
MAX_DAILY_LOSS_PERCENT=5.0       # Stop total del día si pérdida > 5%
MIN_CONSENSUS_SCORE=0.65         # Mínimo acuerdo entre agentes para ejecutar
```

### 4.3 Instalar cliente Binance

```powershell
pip install python-binance ccxt
```

### 4.4 Verificar conexión testnet

```python
# test_binance.py
from binance.client import Client
import os
from dotenv import load_dotenv

load_dotenv()

client = Client(
    os.getenv('BINANCE_TESTNET_API_KEY'),
    os.getenv('BINANCE_TESTNET_SECRET'),
    testnet=True
)

# Verificar balance
account = client.get_account()
balances = [b for b in account['balances'] if float(b['free']) > 0]
print("Balances testnet:", balances)

# Verificar precio actual
price = client.get_symbol_ticker(symbol='BTCUSDT')
print("BTC precio actual:", price['price'])
```

---

## ⚙️ FASE 5 — Capa de Orquestación Multi-Agente

### 5.1 Instalar dependencias de orquestación

```powershell
pip install langgraph langchain anthropic google-generativeai openai redis fastapi uvicorn websockets pydantic
```

### 5.2 Implementar clase base de agente

Crear `agents/base_agent.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import uuid
from datetime import datetime

class AgentVote(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass
class TradingSignal:
    pair: str
    vote: AgentVote
    confidence: float        # 0.0 - 1.0
    reasoning: str
    agent_id: str
    timestamp: str = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

class BaseAgent(ABC):
    def __init__(self, agent_id: str, role: str):
        self.agent_id = agent_id
        self.role = role
        self.is_ready = False

    @abstractmethod
    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        """Analiza el mercado y devuelve un voto."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifica que el agente está operativo."""
        pass

    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] [{self.agent_id}] {datetime.utcnow().isoformat()} — {message}")
```

### 5.3 Implementar agente local (Ollama)

Crear `agents/local_agent.py`:

```python
import ollama
from .base_agent import BaseAgent, TradingSignal, AgentVote
import json

class LocalAgent(BaseAgent):
    def __init__(self, model: str = "qwen2.5:14b", host: str = "http://localhost:11434"):
        super().__init__("local-qwen", "orchestration-router")
        self.model = model
        self.client = ollama.Client(host=host)

    async def health_check(self) -> bool:
        try:
            self.client.list()
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        prompt = f"""
Eres un agente de trading conservador. Analiza estos datos y vota.

Par: {market_data.get('symbol')}
Precio actual: {market_data.get('price')}
RSI (14): {market_data.get('rsi')}
MACD: {market_data.get('macd')}
Volumen 24h: {market_data.get('volume')}
Tendencia: {market_data.get('trend')}
Contexto histórico: {context.get('recent_decisions', 'Sin historial')}

Responde SOLO con un JSON válido:
{{
  "vote": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "explicación breve"
}}
"""
        response = self.client.chat(
            model=self.model,
            messages=[{'role': 'user', 'content': prompt}],
            format='json'
        )

        data = json.loads(response['message']['content'])
        return TradingSignal(
            pair=market_data.get('symbol'),
            vote=AgentVote[data['vote']],
            confidence=float(data['confidence']),
            reasoning=data['reasoning'],
            agent_id=self.agent_id
        )
```

### 5.4 Implementar agente Claude

Crear `agents/claude_agent.py`:

```python
import anthropic
import json
import os
from .base_agent import BaseAgent, TradingSignal, AgentVote

class ClaudeAgent(BaseAgent):
    def __init__(self):
        super().__init__("claude-sonnet", "heavy-analysis")
        self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.model = "claude-sonnet-4-20250514"

    async def health_check(self) -> bool:
        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}]
            )
            self.is_ready = True
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False

    async def analyze(self, market_data: dict, context: dict) -> TradingSignal:
        system_prompt = """Eres un analista quant senior especializado en crypto daytrading.
Tu tarea es analizar datos de mercado y votar BUY, SELL o HOLD.
Prioriza la preservación del capital sobre las ganancias.
Responde SOLO con JSON válido."""

        user_prompt = f"""
Analiza y vota para: {market_data.get('symbol')}

Datos técnicos:
- Precio: {market_data.get('price')}
- RSI(14): {market_data.get('rsi')}
- MACD: {market_data.get('macd')}
- BB superior: {market_data.get('bb_upper')} | inferior: {market_data.get('bb_lower')}
- EMA20: {market_data.get('ema20')} | EMA50: {market_data.get('ema50')}
- Volumen: {market_data.get('volume')}

Análisis Vibe-Trading:
{context.get('vibe_analysis', 'No disponible')}

Historial reciente (MemPalace):
{context.get('recent_decisions', 'Sin historial')}

Responde con:
{{"vote": "BUY|SELL|HOLD", "confidence": 0.0-1.0, "reasoning": "análisis detallado"}}
"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        data = json.loads(response.content[0].text)
        return TradingSignal(
            pair=market_data.get('symbol'),
            vote=AgentVote[data['vote']],
            confidence=float(data['confidence']),
            reasoning=data['reasoning'],
            agent_id=self.agent_id
        )
```

### 5.5 Implementar el motor de decisiones (Voting)

Crear `core/decider.py`:

```python
from typing import List
from agents.base_agent import TradingSignal, AgentVote
import os

MIN_CONSENSUS = float(os.getenv('MIN_CONSENSUS_SCORE', 0.65))

class Decider:
    """Motor de votación ponderada entre agentes."""

    AGENT_WEIGHTS = {
        "claude-sonnet":   0.40,   # Mayor peso — análisis más profundo
        "gemini-pro":      0.30,   # Peso medio
        "gpt-4o":          0.20,   # Peso medio-bajo (limitado por presupuesto)
        "local-qwen":      0.10,   # Menor peso — modelo local básico
    }

    def decide(self, signals: List[TradingSignal]) -> dict:
        scores = {AgentVote.BUY: 0.0, AgentVote.SELL: 0.0, AgentVote.HOLD: 0.0}
        total_weight = 0.0

        for signal in signals:
            weight = self.AGENT_WEIGHTS.get(signal.agent_id, 0.1)
            weighted_confidence = weight * signal.confidence
            scores[signal.vote] += weighted_confidence
            total_weight += weight

        # Normalizar
        if total_weight > 0:
            for key in scores:
                scores[key] /= total_weight

        winning_vote = max(scores, key=scores.get)
        winning_score = scores[winning_vote]

        return {
            "decision": winning_vote.value if winning_score >= MIN_CONSENSUS else "HOLD",
            "consensus_score": winning_score,
            "reached_consensus": winning_score >= MIN_CONSENSUS,
            "votes": {v.value: round(s, 3) for v, s in scores.items()},
            "signals_count": len(signals),
            "reasoning": [s.reasoning for s in signals]
        }
```

### 5.6 Implementar Risk Manager

Crear `core/risk_manager.py`:

```python
import os
from execution.binance_testnet import BinanceTestnetClient

MAX_POSITION_PCT = float(os.getenv('MAX_POSITION_SIZE_PERCENT', 2.0)) / 100
MAX_DAILY_LOSS_PCT = float(os.getenv('MAX_DAILY_LOSS_PERCENT', 5.0)) / 100

class RiskManager:
    def __init__(self, binance_client: BinanceTestnetClient):
        self.binance = binance_client
        self.daily_loss_tracker = {}

    def validate_order(self, pair: str, action: str, portfolio_value: float) -> dict:
        """Valida si una orden puede ejecutarse según reglas de riesgo."""
        
        checks = {
            "position_size_ok": True,
            "daily_loss_ok": True,
            "market_hours_ok": True,    # crypto = siempre abierto
            "min_balance_ok": True,
        }

        # Calcular tamaño máximo permitido
        max_order_value = portfolio_value * MAX_POSITION_PCT
        
        # Verificar pérdida diaria acumulada
        today_loss = self.daily_loss_tracker.get(pair, 0.0)
        if abs(today_loss) / portfolio_value > MAX_DAILY_LOSS_PCT:
            checks["daily_loss_ok"] = False

        all_passed = all(checks.values())
        
        return {
            "approved": all_passed,
            "max_order_value_usdt": max_order_value,
            "checks": checks,
            "reason": "OK" if all_passed else f"Bloqueado por: {[k for k,v in checks.items() if not v]}"
        }
```

---

## ⚙️ FASE 6 — Cliente Binance Testnet

Crear `execution/binance_testnet.py`:

```python
from binance.client import Client
import os
from dotenv import load_dotenv
import math

load_dotenv()

class BinanceTestnetClient:
    def __init__(self):
        self.client = Client(
            api_key=os.getenv('BINANCE_TESTNET_API_KEY'),
            api_secret=os.getenv('BINANCE_TESTNET_SECRET'),
            testnet=True
        )

    def get_portfolio_value(self) -> float:
        """Retorna valor total del portafolio en USDT."""
        account = self.client.get_account()
        total = 0.0
        for b in account['balances']:
            free = float(b['free'])
            if free > 0:
                if b['asset'] == 'USDT':
                    total += free
                else:
                    try:
                        price = float(self.client.get_symbol_ticker(
                            symbol=f"{b['asset']}USDT"
                        )['price'])
                        total += free * price
                    except:
                        pass
        return total

    def get_market_data(self, symbol: str) -> dict:
        """Obtiene datos básicos de mercado para análisis."""
        ticker = self.client.get_symbol_ticker(symbol=symbol)
        klines = self.client.get_klines(symbol=symbol, interval='1h', limit=50)
        
        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        
        return {
            "symbol": symbol,
            "price": float(ticker['price']),
            "closes": closes,
            "volumes": volumes,
            "volume": sum(volumes[-24:]),   # Volumen 24h
        }

    def place_market_order(self, symbol: str, side: str, usdt_amount: float) -> dict:
        """Ejecuta orden de mercado. side = 'BUY' | 'SELL'."""
        price = float(self.client.get_symbol_ticker(symbol=symbol)['price'])
        quantity = usdt_amount / price
        
        # Ajustar precisión según el par
        info = self.client.get_symbol_info(symbol)
        step_size = float([f for f in info['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])
        precision = int(round(-math.log(step_size, 10), 0))
        quantity = round(quantity, precision)

        order = self.client.create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity
        )
        return order
```

---

## ⚙️ FASE 7 — FastAPI Server

Crear `api/main.py`:

```python
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json

app = FastAPI(title="Trading Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

connected_clients = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await asyncio.sleep(1)
    except:
        connected_clients.remove(websocket)

async def broadcast(message: dict):
    """Enviar update a todos los clientes del dashboard."""
    for client in connected_clients:
        try:
            await client.send_text(json.dumps(message))
        except:
            pass

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/portfolio")
async def get_portfolio():
    # Importar y usar BinanceTestnetClient
    pass

@app.post("/trigger-analysis/{symbol}")
async def trigger_analysis(symbol: str):
    """Disparar un ciclo manual de análisis."""
    pass
```

---

## ⚙️ FASE 8 — Dashboard React

### 8.1 Crear proyecto React

```powershell
cd dashboard
npm create vite@latest . -- --template react-ts
npm install
npm install recharts lucide-react @tanstack/react-query
```

### 8.2 Estructura principal del dashboard

El dashboard mostrará en tiempo real via WebSocket:
- **Panel izquierdo:** Log de decisiones de agentes (quién votó qué y por qué)
- **Panel central:** Gráfico de precio del par activo + indicadores
- **Panel derecho:** Estado del portafolio + P&L
- **Barra inferior:** Últimas órdenes ejecutadas + consenso de la última votación

### 8.3 Iniciar dashboard en desarrollo

```powershell
npm run dev
```

Disponible en `http://localhost:5173`

---

## ⚙️ FASE 9 — Integración Final y Loop Principal

Crear `core/orchestrator.py`:

```python
import asyncio
from agents.local_agent import LocalAgent
from agents.claude_agent import ClaudeAgent
from core.decider import Decider
from core.risk_manager import RiskManager
from execution.binance_testnet import BinanceTestnetClient
from memory.mempalace_client import MemPalaceClient
import os

TRADING_PAIRS = os.getenv('TRADING_PAIRS', 'BTCUSDT').split(',')
ANALYSIS_INTERVAL_SECONDS = 300   # Analizar cada 5 minutos

class TradingOrchestrator:
    def __init__(self):
        self.binance = BinanceTestnetClient()
        self.memory = MemPalaceClient()
        self.decider = Decider()
        self.risk_manager = RiskManager(self.binance)
        
        # Inicializar agentes
        self.agents = [
            LocalAgent(),
            ClaudeAgent(),
            # GeminiAgent(),  # Agregar en siguiente fase
            # GPTAgent(),     # Agregar en siguiente fase
        ]

    async def run_analysis_cycle(self, symbol: str):
        """Un ciclo completo de análisis → votación → decisión → ejecución."""
        
        print(f"\n{'='*50}")
        print(f"CICLO DE ANÁLISIS: {symbol}")
        print(f"{'='*50}")

        # 1. Obtener datos de mercado
        market_data = self.binance.get_market_data(symbol)
        
        # 2. Recuperar contexto de memoria
        context = {
            "recent_decisions": self.memory.search(
                f"decisiones {symbol}",
                wing="trading-decisions",
                top_k=3
            )
        }

        # 3. Recopilar votos de todos los agentes
        signals = []
        for agent in self.agents:
            if await agent.health_check():
                signal = await agent.analyze(market_data, context)
                signals.append(signal)
                print(f"  [{agent.agent_id}] {signal.vote.value} (confianza: {signal.confidence:.2f})")

        # 4. Tomar decisión por consenso
        decision = self.decider.decide(signals)
        print(f"\nDECISIÓN: {decision['decision']} (consenso: {decision['consensus_score']:.2f})")

        # 5. Validar con Risk Manager
        if decision['decision'] != 'HOLD' and decision['reached_consensus']:
            portfolio_value = self.binance.get_portfolio_value()
            risk_check = self.risk_manager.validate_order(
                symbol, decision['decision'], portfolio_value
            )
            
            if risk_check['approved']:
                # 6. Ejecutar orden
                order = self.binance.place_market_order(
                    symbol,
                    decision['decision'],
                    risk_check['max_order_value_usdt']
                )
                print(f"ORDEN EJECUTADA: {order['orderId']}")
                
                # 7. Guardar en memoria
                self.memory.store(
                    wing="trading-decisions",
                    content=f"EJECUTADO: {decision['decision']} {symbol} — {decision['reasoning']}",
                    metadata={"order_id": order['orderId'], "consensus": decision['consensus_score']}
                )
            else:
                print(f"ORDEN BLOQUEADA por Risk Manager: {risk_check['reason']}")

    async def start(self):
        """Loop principal del sistema."""
        print("Sistema de trading iniciado. Ctrl+C para detener.")
        
        while True:
            for symbol in TRADING_PAIRS:
                await self.run_analysis_cycle(symbol)
            
            print(f"\nPróximo análisis en {ANALYSIS_INTERVAL_SECONDS}s...")
            await asyncio.sleep(ANALYSIS_INTERVAL_SECONDS)


if __name__ == "__main__":
    orchestrator = TradingOrchestrator()
    asyncio.run(orchestrator.start())
```

---

---

## 🧠 FASE 10 — CLAUDE.md: Skills de Especialización en Trading

Esta fase define los archivos que instruyen a Claude Code a comportarse como un agente de trading especializado. Son el "cerebro" que Claude carga automáticamente en cada sesión.

### Estructura de archivos

```
vibe-trading/
├── CLAUDE.md               ← Instrucciones globales del proyecto
├── .mcp.json               ← Configuración MCP (MemPalace + herramientas)
└── skills/
    ├── trading-analyst.md  ← Skill: análisis técnico
    ├── risk-manager.md     ← Skill: gestión de riesgo
    ├── news-interpreter.md ← Skill: interpretación de noticias
    └── executor.md         ← Skill: ejecución de órdenes
```

---

### 10.1 CLAUDE.md — Archivo principal

Crear `CLAUDE.md` en la raíz del proyecto:

```markdown
# 🤖 Agente de Trading — Sistema Multi-Agente

Eres el agente central de un sistema de daytrading en Binance Testnet.
Tu rol es analizar mercados, coordinar agentes y ejecutar decisiones conservadoras.

## 🎯 Identidad y Rol

- Eres un **analista cuantitativo conservador** especializado en crypto daytrading
- Tu prioridad #1 es **preservar el capital** — nunca arriesgar más del 2% por operación
- Operas exclusivamente en **Binance Testnet** — sin dinero real involucrado
- Formas parte de un equipo de agentes: Gemini y GPT también votan contigo
- Tu voto tiene peso 40% en las decisiones finales

## 🧠 Sistema de Memoria — MemPalace (OBLIGATORIO)

**Al iniciar CADA sesión, ejecutar en este orden:**

1. `mempalace_status` — Carga el palace y aprende el protocolo AAAK
2. `mempalace_search "estado portafolio actual"` — Recupera posiciones abiertas
3. `mempalace_search "últimas decisiones BTCUSDT"` — Contexto reciente del par
4. `mempalace_kg_query "portafolio"` — Estado del knowledge graph

**Después de CADA decisión de trading, guardar:**

```
mempalace_diary_write con formato:
FECHA | PAR | ACCIÓN | PRECIO | CONFIANZA | REASONING | CONSENSO_FINAL
```

**Reglas de memoria:**
- Nunca inventes datos que no estén en MemPalace o en el prompt actual
- Si MemPalace no tiene contexto → proceder con análisis limpio, indicarlo
- Siempre usar --wing trading-decisions para decisiones
- Siempre usar --wing news-intel para consultar noticias recientes

## 📊 Skills de Análisis — Cómo Analizar

### Skill: Análisis Técnico
Cuando recibas datos de mercado, evaluar SIEMPRE en este orden:
1. **Tendencia macro** (EMA20 vs EMA50 — ¿alcista o bajista?)
2. **Momentum** (RSI: <30 oversold, >70 overbought)
3. **Confirmación** (MACD: cruce alcista/bajista)
4. **Volumen** (¿valida o contradice el movimiento?)
5. **Contexto de noticias** (del wing news-intel de MemPalace)

### Skill: Detección de Régimen de Mercado
Antes de votar, identificar el régimen actual:
- **TRENDING**: EMA20 > EMA50 + volumen creciente → estrategia de seguimiento
- **RANGING**: EMA20 ≈ EMA50 + volumen bajo → estrategia de reversión
- **VOLATILE**: RSI extremo + volumen explosivo → reducir exposición, HOLD preferible
- **RISK-OFF**: Noticias geopolíticas negativas + BTC cayendo → evitar BUY

### Skill: Gestión de Riesgo (no negociable)
Antes de votar BUY o SELL, verificar:
- [ ] ¿La pérdida máxima posible es ≤ 2% del portafolio?
- [ ] ¿El ratio riesgo/beneficio es ≥ 1:2?
- [ ] ¿Las noticias recientes no contraindican la operación?
- [ ] ¿El consenso de los otros agentes es ≥ 0.65?
- Si algún check falla → votar HOLD con explicación

### Skill: Interpretación de Noticias
Cuando el contexto incluya noticias (del WebSearchAgent):
- **Conflictos geopolíticos activos** (Iran/Israel/USA) → sesgo HOLD o SELL
- **Decisiones Fed / tasas de interés** → alta volatilidad esperada, reducir size
- **Noticias positivas de crypto** (ETF, adopción) → sesgo moderado BUY
- **Hacks o exploits** → SELL inmediato del asset afectado
- **Trump / ejecutivos económicos** → evaluar impacto en USD → impacto en BTC

## 📤 Formato de Respuesta (SIEMPRE JSON)

Cuando el sistema te pida un análisis de trading, responder ÚNICAMENTE con:

```json
{
  "vote": "BUY|SELL|HOLD",
  "confidence": 0.0,
  "reasoning": "Explicación en máximo 2 oraciones con datos específicos",
  "regime": "TRENDING|RANGING|VOLATILE|RISK-OFF",
  "risk_check_passed": true,
  "key_signals": ["RSI=X", "MACD=X", "noticia relevante"],
  "suggested_stop_loss_pct": 1.5,
  "memory_context_used": true
}
```

No agregar texto fuera del JSON. El sistema lo parsea directamente.

## 🔄 Flujo de Trabajo por Ciclo

```
1. [MEMORIA] Consultar MemPalace → contexto reciente del par
2. [DATOS]   Recibir market_data del Orchestrator
3. [NOTICIAS] Leer news_context del WebSearchAgent
4. [ANÁLISIS] Aplicar skills de análisis técnico
5. [RIESGO]  Verificar checks de gestión de riesgo
6. [VOTO]    Emitir JSON con voto y confianza
7. [MEMORIA] Guardar decisión en MemPalace diary
```

## ⚠️ Restricciones Absolutas

- **NUNCA** inventar precios, RSI, MACD u otros datos técnicos
- **NUNCA** sugerir operaciones sin datos de mercado actuales
- **NUNCA** votar BUY si risk_check_passed = false
- **NUNCA** ignorar noticias con impact = HIGH
- **SIEMPRE** que la confianza sea < 0.5 → votar HOLD
- **SIEMPRE** consultar MemPalace al inicio de sesión

## 💰 Contexto del Portafolio

- Plataforma: Binance Testnet (dinero simulado)
- Pares activos: BTCUSDT, ETHUSDT (expandible)
- Risk per trade: máximo 2% del portafolio total
- Stop loss por defecto: 1.5% del precio de entrada
- Take profit mínimo: 3% (ratio 1:2)
- Intervalo de análisis: cada 35 minutos
```

---

### 10.2 Configuración MCP — `.mcp.json`

Crear `.mcp.json` en la raíz del proyecto:

```json
{
  "mcpServers": {
    "mempalace": {
      "command": "python",
      "args": ["-m", "mempalace.mcp_server"],
      "env": {
        "MEMPALACE_PALACE_PATH": "C:\\Users\\Rael\\.mempalace"
      }
    }
  }
}
```

> **Nota Windows:** Usar doble barra invertida `\\` en rutas dentro de JSON.

Verificar que Claude Code detecta el MCP:
```powershell
claude mcp list
# Debe mostrar: mempalace (connected)
```

---

### 10.3 Skills individuales — Archivos de referencia

Crear `skills/trading-analyst.md`:

```markdown
# Skill: Análisis Técnico Avanzado

## Indicadores prioritarios por orden de confianza

### RSI (Relative Strength Index)
- RSI < 25: oversold severo → señal de BUY fuerte (pero verificar tendencia)
- RSI 25-35: oversold moderado → BUY con cautela
- RSI 35-65: zona neutral → depender de MACD y volumen
- RSI 65-75: overbought moderado → HOLD o reducir posición
- RSI > 75: overbought severo → SELL o no entrar BUY

### MACD
- Cruce alcista (MACD cruza señal hacia arriba) + histograma positivo → BUY
- Cruce bajista (MACD cruza señal hacia abajo) + histograma negativo → SELL
- Divergencia alcista (precio baja, MACD sube) → potencial reversión BUY
- Divergencia bajista (precio sube, MACD baja) → potencial reversión SELL

### Bollinger Bands
- Precio toca banda inferior + RSI < 35 → BUY fuerte
- Precio toca banda superior + RSI > 65 → SELL fuerte
- Precio dentro de bandas → mercado en rango, reducir confianza

### Volumen
- Volumen > 150% del promedio 20 períodos → confirma la señal
- Volumen < 70% del promedio → señal débil, reducir confianza en 20%
- Volumen creciente en tendencia → tendencia sostenible
- Volumen decreciente en tendencia → posible reversión próxima

## Confluencia de señales
- 3+ indicadores alineados → confidence 0.75-0.90
- 2 indicadores alineados → confidence 0.55-0.75
- 1 indicador o contradicción → confidence < 0.55 → HOLD
```

Crear `skills/risk-manager.md`:

```markdown
# Skill: Gestión de Riesgo

## Reglas inmutables (no se pueden ignorar)

1. Máximo 2% del portafolio por operación
2. Stop loss mínimo: siempre definido antes de entrar
3. No operar durante las primeras 2 velas después de una noticia HIGH
4. Si pérdida acumulada diaria > 5% → detener trading ese día
5. No abrir nueva posición si hay una posición perdedora abierta > 3%

## Cálculo de tamaño de posición

```
tamaño = portafolio_total × 0.02 / distancia_al_stop_pct
```

Ejemplo: Portafolio $10,000 · Stop a 1.5% del precio:
```
tamaño = 10,000 × 0.02 / 0.015 = $13,333 máximo
```

## Condiciones para AVOID (no operar)

- news_sentiment < -0.70 (WebSearchAgent)
- Conflicto geopolítico activo con impacto HIGH
- RSI > 80 o < 20 (extremos peligrosos)
- Volumen < 50% del promedio (mercado muerto)
- Spread bid-ask > 0.15% en testnet
```

Crear `skills/executor.md`:

```markdown
# Skill: Ejecución de Órdenes

## Protocolo de ejecución

1. Recibir decisión del Orchestrator con consenso ≥ 0.65
2. Verificar que Risk Manager aprobó la orden
3. Calcular quantity según tamaño máximo permitido
4. Ejecutar orden MARKET (testnet — no usar LIMIT por ahora)
5. Confirmar order_id en respuesta de Binance
6. Guardar en MemPalace: order_id, pair, side, qty, price, timestamp

## Formato de confirmación

```json
{
  "executed": true,
  "order_id": "123456",
  "pair": "BTCUSDT",
  "side": "BUY",
  "quantity": 0.001,
  "price": 84200.00,
  "timestamp": "2026-04-13T21:30:00Z",
  "testnet": true
}
```

## En caso de error de Binance

- Código 1100 (parámetros inválidos) → loggear y notificar, no reintentar
- Código 1013 (qty fuera de rango) → recalcular con step_size correcto
- Código 429 (rate limit) → esperar 5 segundos y reintentar una vez
- Cualquier otro error → loggear, votar HOLD en próximo ciclo
```

---

### 10.4 Checklist — FASE 10

- [ ] `CLAUDE.md` creado en raíz del proyecto `vibe-trading/`
- [ ] `.mcp.json` creado con ruta correcta a MemPalace en Windows
- [ ] Carpeta `skills/` creada con los 4 archivos
- [ ] `claude mcp list` muestra `mempalace` como conectado
- [ ] Al iniciar sesión con `claude`, ejecuta `mempalace_status` automáticamente
- [ ] Claude responde en JSON puro cuando se le pide análisis de trading
- [ ] Skills de riesgo funcionan: votar HOLD cuando confianza < 0.5
- [ ] Memoria persiste entre sesiones — verificar guardando y reabriendo Claude

---

## 📋 Checklist de Verificación por Fase

Claude Code debe verificar cada item antes de continuar:

### Fase 0 — Entorno
- [ ] Python 3.11+ instalado y en PATH
- [ ] Node.js 18+ instalado
- [ ] Redis/Memurai corriendo en puerto 6379
- [ ] Entorno virtual activado
- [ ] Carpeta `trading-agent/` creada

### Fase 1 — Modelo Local ✅ COMPLETADA
- [x] Ollama instalado y corriendo en Windows
- [x] Variables de entorno Vulkan configuradas (`OLLAMA_VULKAN=1`)
- [x] GPU detectada: `AMD Radeon RX 9060 XT` vía `library=Vulkan`
- [x] `ollama list` muestra `qwen2.5:14b`
- [x] 37/37 capas offloadeadas a GPU — 9.0 GiB VRAM
- [x] Flash Attention activado
- [x] Respuesta JSON de trading válida — ~7.5s de tiempo de respuesta
- [x] **Usar PowerShell (no CMD) para evitar problemas con comillas en prompts**

### Fase 2 — MemPalace
- [ ] MemPalace instalado sin errores
- [ ] `~/.mempalace/` creado con estructura wings
- [ ] `test_memory.py` guarda y recupera exitosamente
- [ ] Servidor MCP de MemPalace iniciable

### Fase 3 — Vibe-Trading
- [ ] `vibe-trading init` completado
- [ ] `vibe-trading --list-skills` muestra skills
- [ ] Skill `technical-basic` funciona con BTCUSDT
- [ ] Backtesting básico ejecutable

### Fase 4 — Binance Testnet
- [ ] API keys testnet en `.env`
- [ ] `test_binance.py` muestra balance > 0
- [ ] Precio de BTCUSDT recuperable
- [ ] Orden de prueba (cantidad mínima) ejecutable

### Fase 5-6 — Agentes + Orquestación
- [ ] `BaseAgent` importable sin errores
- [ ] `LocalAgent.health_check()` retorna True
- [ ] `ClaudeAgent.health_check()` retorna True
- [ ] `Decider.decide()` con signals de prueba retorna decisión válida
- [ ] `RiskManager.validate_order()` bloquea cuando corresponde
- [ ] Un ciclo completo de análisis ejecutable manualmente

### Fase 7 — API
- [ ] FastAPI corre en `http://localhost:8000`
- [ ] `/health` devuelve `{"status": "ok"}`
- [ ] WebSocket acepta conexiones

### Fase 8 — Dashboard
- [ ] React corre en `http://localhost:5173`
- [ ] Conecta al WebSocket sin errores de CORS

### Fase 9 — Integración
- [ ] Loop principal corre 3 ciclos completos sin crashear
- [ ] MemPalace acumula decisiones entre ciclos
- [ ] Las decisiones del ciclo 2 incluyen contexto del ciclo 1

---

## 🔑 Archivo .env.example

```env
# ===== MODELO LOCAL (✅ FUNCIONANDO) =====
OLLAMA_BASE_URL=http://localhost:11434
LOCAL_MODEL=qwen2.5:14b
# Variables de sistema ya configuradas: OLLAMA_VULKAN=1, OLLAMA_FLASH_ATTENTION=1

# ===== CLAUDE (vía Claude Code CLI — suscripción Pro $20) =====
# No requiere API key — usa tu sesión de Claude Code
# Límite: ~45 mensajes por ventana de 5 horas
# Consultar cada ~35 minutos = uso seguro sin agotar límite
CLAUDE_INTERVAL_SECONDS=2100   # 35 minutos

# ===== GEMINI (GRATIS — 1000 req/día) =====
# Obtener en: https://aistudio.google.com → Get API Key
GOOGLE_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash-lite   # Tier gratuito: 1000 req/día, 15 RPM

# ===== GPT-5.4 MINI (API — $40 budget, ~$0.20/mes uso real) =====
OPENAI_API_KEY=sk-...
GPT_MODEL=gpt-5.4-mini   # $0.40/M input · $1.60/M output

# ===== BINANCE TESTNET =====
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_SECRET=...
BINANCE_TESTNET=true

# ===== TRADING CONFIG =====
TRADING_PAIRS=BTCUSDT,ETHUSDT
ANALYSIS_INTERVAL_SECONDS=2100   # 35 minutos — alineado con límite Claude
MAX_POSITION_SIZE_PERCENT=2.0
MAX_DAILY_LOSS_PERCENT=5.0
MIN_CONSENSUS_SCORE=0.65

# ===== MEMPALACE =====
MEMPALACE_PATH=C:\Users\Rael\.mempalace

# ===== WEB SEARCH AGENT =====
NEWS_INTERVAL_SECONDS=1800        # Cada 30 minutos
NEWS_MAX_RESULTS_PER_QUERY=3
TAVILY_API_KEY=tvly-...           # Opcional — gratis en tavily.com
NEWS_AVOID_THRESHOLD=-0.70

# ===== REDIS (Memurai en Windows) =====
REDIS_URL=redis://localhost:6379

# ===== API SERVER =====
API_PORT=8000
DASHBOARD_PORT=5173
```

---

## ⚠️ Notas Importantes

1. **Modelo local verificado y funcionando** — Qwen2.5:14b corre 100% en GPU vía Vulkan. Su rol es monitoreo, routing y ejecución — **no análisis de trading complejo**.
2. **Claude via CLI (no API)** — Usa tu suscripción Pro $20. Limitar a ~35min entre consultas evita agotar el límite de 45 mensajes/5h. Usar **PowerShell**, no CMD.
3. **Gemini es completamente gratis** — 1,000 req/día con Flash-Lite. Obtener key en aistudio.google.com sin tarjeta de crédito.
4. **GPT-5.4 Mini** — Los $40 duran meses con el volumen real del sistema (~$0.20/mes).
5. **Nunca usar estas keys en producción.** El sistema está diseñado exclusivamente para Binance Testnet.
6. **Las opciones binarias no están disponibles en Binance.** El sistema se enfoca en spot y futuros perpetuos básicos.
7. **El apalancamiento en futuros requiere configuración adicional** — comenzar con spot únicamente.
8. **MemPalace es muy nuevo (lanzado abril 2026)** — si hay bugs, el fallback es un archivo JSON simple como memoria temporal.
9. **CLAUDE.md es obligatorio** — sin él Claude no usará MemPalace proactivamente y perderá todo el contexto entre sesiones.

---

## 📚 Referencias

- **Vibe-Trading:** https://github.com/HKUDS/Vibe-Trading
- **MemPalace:** https://github.com/milla-jovovich/mempalace
- **MemPalace setup guide:** https://www.mempalace.tech/guides/setup
- **Ollama AMD Vulkan:** https://docs.ollama.com/gpu
- **Binance Testnet:** https://testnet.binance.vision/
- **Gemini API free key:** https://aistudio.google.com
- **LangGraph docs:** https://langchain-ai.github.io/langgraph/
- **python-binance:** https://python-binance.readthedocs.io/
- **GPT-5.4 Mini pricing:** https://openai.com/api/pricing/

---

*Última actualización: 13 de abril de 2026*
*Estado del modelo local: ✅ OPERATIVO — Qwen2.5:14b · Vulkan · RX 9060 XT · 37/37 capas GPU*
*Siguiente paso: Instalar MemPalace + configurar CLAUDE.md*
