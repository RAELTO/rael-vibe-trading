# 📋 Trading Agent — Implementation Checklist

> Archivo de seguimiento del progreso de implementación.
> Marcar cada item con `[x]` al completar. Ver `TRADING_AGENT_ROADMAP.md` para detalles de cada fase.

**Librerías principales:**
- **Vibe-Trading** — `github.com/HKUDS/Vibe-Trading` — skills financieras, backtesting, análisis técnico, swarm de agentes
- **MemPalace** — `github.com/milla-jovovich/mempalace` — memoria persistente de agentes (ChromaDB + SQLite KG)

---

## FASE 0 — Entorno Windows ✅ COMPLETADA

- [x] Python 3.13.1 instalado y en PATH
- [x] Node.js 22.13.1 instalado · npm 10.1.0
- [x] Memurai (Redis) corriendo en puerto 6379 — Developer Edition RC1
- [x] Entorno virtual creado (`venv/`) y verificado
- [x] Estructura de carpetas creada: `core/`, `agents/`, `memory/`, `skills/`, `execution/`, `api/`, `dashboard/`
- [x] `.gitignore` creado
- [x] `.env.example` creado
- [x] `requirements.txt` creado
- [x] `docker-compose.yml` creado (Redis via Docker cuando esté disponible)

---

## FASE 1 — Modelo Local (Ollama + Qwen2.5:14b) ✅ COMPLETADA

- [x] Ollama instalado y corriendo en Windows
- [x] `OLLAMA_VULKAN=1` y `OLLAMA_FLASH_ATTENTION=1` configurados como variables de sistema
- [x] GPU detectada: `AMD Radeon RX 9060 XT` · `library=Vulkan` · 15.9 GiB
- [x] `ollama list` muestra `qwen2.5:14b`
- [x] 37/37 capas offloadeadas a GPU · 9.0 GiB VRAM · Flash Attention ON
- [x] Respuesta JSON válida de trading (`{"vote":"SELL","confidence":0.8,...}`)
- [x] Tiempo de respuesta ~7.5s verificado

---

## FASE 2 — MemPalace (Memoria Persistente) ✅ COMPLETADA

- [x] `pip install chromadb pyyaml` sin errores
- [x] `git clone` y `pip install -e .` de MemPalace 3.3.0 completado
- [x] `mempalace init` crea `~/.mempalace/` correctamente — 751 drawers indexados
- [x] `identity.txt` configurado con contexto del sistema de trading
- [x] `mempalace.yaml` generado con wing `vibe_trading` y rooms: agents, backend, core, dashboard, execution, memory, skills...
- [x] `mempalace search` retorna resultados semánticos correctos
- [x] MCP conectado: `claude mcp list` muestra `mempalace ✓ Connected`
- [x] Wake-up context activo con identidad del sistema de trading

---

## FASE 3 — Vibe-Trading (Skills Financieras) ✅ COMPLETADA

- [x] `pip install -e Vibe-Trading/` — v0.1.4 instalado desde repo local
- [x] `.env` configurado: provider `openai` · modelo `gpt-4o-mini` · presupuesto $10
- [x] Gemini API key configurada como fallback (`gemini-2.0-flash`)
- [x] `vibe-trading --skills` muestra 69 skills disponibles
- [x] Swarm presets disponibles: `crypto_trading_desk`, `crypto_research_lab`, `technical_analysis_panel`, `geopolitical_war_room`, etc.
- [x] Análisis BTC-USDT ejecutado correctamente — resultado: HOLD (ADX 24.76, RSI overbought)
- [x] Status: SUCCESS en 189s — datos reales de mercado obtenidos

---

## FASE 3.5 — WebSearchAgent (Inteligencia de Mercado Proactiva) ✅ COMPLETADA

- [x] `ddgs`, `feedparser`, `httpx`, `beautifulsoup4`, `lxml`, `tavily-python` instalados
- [x] `agents/web_search_agent.py` creado — 14 queries en 3 categorías + 2 feeds RSS
- [x] `search_duckduckgo("Bitcoin news")` retorna noticias reales (NewsBTC, Cryptonews, etc.)
- [x] `fetch_rss(COINTELEGRAPH_URL)` retorna artículos correctamente
- [x] `get_latest_context()` retorna default context sin errores
- [x] `analyze_with_llm()` usa claude-haiku-4-5 — extrae JSON con sentiment + asset scores
- [x] `save_to_memory()` con soporte MemPalace wing `news-intel`
- [x] `tests/test_web_search_agent.py` — todos los tests OK sin warnings

---

## FASE 4 — Binance Testnet ✅ COMPLETADA

- [x] Cuenta creada en `testnet.binance.vision` (login con GitHub)
- [x] API Key y Secret Key generadas y guardadas en `.env`
- [x] `pip install python-binance` sin errores — v1.0.36
- [x] `test_binance.py` conecta y muestra balance > 0 — 454 assets con fondos
- [x] Precio de BTCUSDT recuperable — $74,005 en tiempo real
- [x] Klines históricos (OHLCV) recuperables — 5 velas 1h verificadas
- [x] Orden de prueba — cubierta por BinanceTestnetClient en Fase 6

---

## FASE 5 — Capa de Orquestación Multi-Agente ✅ COMPLETADA

- [x] `pip install google-genai python-binance` sin errores
- [x] `agents/base_agent.py` creado (`BaseAgent`, `TradingSignal`, `AgentVote`)
- [x] `agents/local_agent.py` creado (`LocalAgent` wrapping Ollama + gate_check) — health OK
- [x] `agents/claude_agent.py` creado (`ClaudeAgent` — prompt caching, 40%) — health OK, voto HOLD 0.62
- [x] `agents/gemini_agent.py` creado (`GeminiAgent` — SDK nativo, thinking_budget=0) — fallback/scanner
- [x] `agents/gpt_agent.py` creado (`GPTAgent` — gpt-5.4-mini, 15%) — health OK, voto HOLD 0.56
- [x] `agents/deepseek_agent.py` creado (`DeepSeekAgent` — 20%) — health OK, voto HOLD 0.65
- [x] `agents/qwen_agent.py` creado (`QwenAPIAgent` — qwen3.5-plus free tier, 20%) — health OK, voto SELL 0.75
- [x] `core/decider.py` actualizado: claude=0.40, qwen-api=0.20, deepseek=0.20, gpt=0.15, local=0.05
- [x] `core/risk_manager.py` creado — valida confianza, daily loss, tamaño posición, posiciones abiertas
- [x] Todos los agentes `health_check()` retornan True — 5/5 verificados
- [x] `RiskManager.validate_order()` bloquea cuando corresponde — 3 casos verificados
- [x] Stop loss (-2.5%) y take profit (+4.0%) calculados correctamente
- [x] `ClaudeAgent` con prompt caching activo — $10 presupuesto cargado
- [x] Intervalo ajustado a 20 min (`ANALYSIS_INTERVAL_SECONDS=1200`)
- [ ] Integración WebSearchAgent en Orchestrator (`asyncio.gather()` para ambos loops)
- [ ] Decider aplica multiplicador `NEWS_IMPACT_MULTIPLIER` en ciclo real

---

## FASE 6 — Cliente Binance Testnet ✅ COMPLETADA

- [x] `execution/binance_testnet.py` creado (`BinanceTestnetClient`)
- [x] `get_portfolio_value()` retorna $10,000 USDT
- [x] `get_market_data(symbol)` retorna precio, RSI, MACD, BB, EMA20/50, volumen
- [x] `get_top_volume_pairs()` rankea universo de 10 pares por volumen real
- [x] Indicadores técnicos calculados internamente (RSI, MACD, BB, EMA)
- [x] Precisión de quantity ajustada con `step_size` — 0.00267 BTC = $199.44
- [x] `place_stop_loss()` y `place_take_profit()` implementados con tick size
- [x] `place_market_order()` implementado — pendiente ejecución real en Fase 9
- [x] Cache de symbol info para evitar llamadas repetidas a Binance

---

## FASE 7 — FastAPI Server ✅ COMPLETADA

- [x] `api/main.py` creado con CORS, WebSocket, y rutas base
- [x] FastAPI corre en `http://localhost:8000` (`uvicorn api.main:app`)
- [x] `/health` devuelve `{"status": "ok"}` — verificado
- [x] `/state` devuelve estado completo del sistema
- [x] `/portfolio`, `/decisions`, `/news`, `/risk` implementados
- [x] WebSocket en `/ws` con ping/pong y envío de estado inicial al conectar
- [x] `broadcast()` con 7 eventos: cycle_start, agent_vote, decision, order_placed, portfolio_update, news_update, error
- [x] `app_state` compartido listo para recibir updates del Orchestrator

---

## FASE 8 — Dashboard React ✅ COMPLETADA

- [x] Proyecto React creado con Vite + TypeScript en `dashboard/`
- [x] `npm install recharts lucide-react @tanstack/react-query tailwindcss` sin errores
- [x] Dashboard corre en `http://localhost:5173`
- [x] Conecta al WebSocket sin errores de CORS (proxy vite + manager.connect)
- [x] Panel de log de agentes renderiza votos en tiempo real (`AgentVotesPanel`)
- [x] Panel de portafolio muestra balance y P&L (`PortfolioPanel`)
- [x] Panel de noticias recibe actualizaciones del WebSearchAgent vía WebSocket (`NewsPanel`)
- [x] Panel de decisión con arc SVG de confianza (`DecisionPanel`)
- [x] Gráfico de precio con indicadores técnicos — RSI, MACD, BB, EMA (`MarketChart`)
- [x] Header sticky: status, ciclo, riesgo, WS ping/pong vivo
- [x] Auto-reconnect WebSocket cada 3s si cae la conexión
- [x] `ErrorLog` compacto visible solo cuando hay errores

---

## FASE 9 — Integración Final y Loop Principal ✅ COMPLETADA

- [x] `core/orchestrator.py` creado con `TradingOrchestrator`
- [x] `asyncio.gather()` corre WebSearchAgent + trading loop + FastAPI server en paralelo
- [x] Loop principal analiza top-volume pair o asset recomendado por news
- [x] Todos los agentes se lanzan en paralelo por ciclo con timeout individual (60s)
- [x] Decider aplica `NEWS_IMPACT_MULTIPLIER` en cada ciclo real
- [x] Gate-check vía `LocalAgent.gate_check()` antes de ejecutar orden
- [x] `RiskManager.validate_order()` como segunda barrera antes de Binance
- [x] `broadcast_*` llamados en todos los pasos — dashboard se actualiza en tiempo real
- [x] `app_state["market_data"]` poblado por Orchestrator — MarketChart lo consume
- [x] Ruta `/market/{symbol}` añadida a FastAPI
- [x] `python core/orchestrator.py` inicia TODO: API + News + Trading desde un solo comando

---

## FASE 10 — CLAUDE.md y Skills de Especialización ✅ COMPLETADA

- [x] `CLAUDE.md` creado en raíz del proyecto — arquitectura, arranque, reglas, notas técnicas
- [x] `.mcp.json` creado con ruta absoluta al venv de Windows (`\\` en JSON)
- [x] Carpeta `skills/` con los 4 archivos:
  - [x] `skills/trading-analyst.md` — JSON puro, señales técnicas de referencia
  - [x] `skills/risk-manager.md` — 6 validaciones, SL/TP automáticos, contexto del sistema
  - [x] `skills/news-interpreter.md` — sentiment -1/+1, AVOID conditions, multiplicadores
  - [x] `skills/executor.md` — checklist de 9 pasos, comandos Binance debugging
- [x] `claude mcp list` muestra `mempalace ✓ Connected`

---

## MEJORAS PENDIENTES

### Prioridad Alta

- [x] **Persistencia de estado** — SQLite via `core/state_store.py` ✅ 16 abril 2026
  - Tablas: `decisions`, `votes`, `risk_state`, `portfolio_snapshots`
  - Al reiniciar restaura `daily_loss` y `open_positions` del día actual automáticamente
  - DB en `data/vibe_trading.db` — visualizable con cualquier SQLite viewer

- [x] **KronosAgent** — agente cuantitativo local basado en Kronos-mini (4.1M params) ✅ 16 abril 2026
  - Lee las últimas 50 velas de 1h (OHLCV) y predice las próximas 5 horas
  - Señal: `predicted_close_h5 vs current` — umbral ±0.3% para BUY/SELL
  - Peso probatorio: 5% (igual que local-qwen) hasta validar track record
  - Ver `agents/kronos_agent.py`

- [x] **Fix DeepSeek conservadurismo** ✅ 16 abril 2026
  - Eliminado "Prioritize capital preservation" del system prompt
  - Reemplazado por instrucción neutral: "vote BUY when bullish, SELL when bearish"
  - Ver `agents/deepseek_agent.py` línea 36

### Prioridad Media

- [x] **Memoria episódica para agentes LLM** ✅ 16 abril 2026
  - `_build_context()` ahora lee últimas 5 decisiones desde SQLite (persiste entre reinicios)
  - PnL acumulado histórico incluido en contexto de todos los agentes
  - Post-mortem de época anterior pasado a ClaudeAgent cuando aplica

- [ ] **Soporte Futures / Short Selling** — implementación paralela, NO refactoring del sistema Spot
  - **Arquitectura:** Spot y Futures corren con los mismos agentes/decider, diferente cliente de ejecución. Switch manual desde el dashboard
  - **Lo que se AÑADE (nada se rompe):**
    - `execution/binance_futures.py` — cliente paralelo a `binance_testnet.py`, endpoints `/fapi/v1/`, URL `testnet.binancefuture.com`
    - Toggle `Spot | Futures` en el header del dashboard — llama a `POST /api/mode`
    - `app_state["trading_mode"]` = `"spot"` | `"futures"` — el orquestador elige cliente según el valor
    - Columna `mode TEXT DEFAULT 'spot'` en todas las tablas SQLite — historial separado por modo sin tablas nuevas
  - **Un solo `if` cambia la lógica de ejecución:** en Spot `SELL` = vender activo; en Futures `SELL` = abrir short (posición nueva)
  - **RiskManager:** añadir cálculo de `liquidation_price` para Futures — crítico para no perder colateral
  - **Apalancamiento x1 por defecto** — se beneficia del short sin riesgo de liquidación prematura; configurable vía `.env`
  - **Por qué Kronos vale más aquí:** en Spot, forecast de -1.5% = "no hacer nada". En Futures = "abrir short y ganar ese -1.5%"
  - **`.env` additions:** `BINANCE_FUTURES_TESTNET_API_KEY`, `BINANCE_FUTURES_TESTNET_SECRET`, `FUTURES_LEVERAGE=1`
  - **Prerequisito:** track record mínimo de 1-2 semanas en Spot antes de activar Futures

- [ ] **Reemplazar LocalAgent por GroqAgent** para despliegue cloud
  - LocalAgent depende de Ollama + GPU AMD local — no funciona en servidor
  - Groq (Llama 3.3 70B): free tier 14,400 req/día, ~2s latencia, supera Qwen2.5:14b
  - Integración idéntica a los demás agentes (cliente OpenAI con base_url distinta)

- [x] **Sistema de recuperación por drawdown (Epoch Manager)** ✅ 16 abril 2026
  - `core/epoch_manager.py` — trigger cuando balance < 20% del inicial ($200 de $1000)
  - Genera post-mortem automático y lo pasa como contexto a los agentes en la nueva época
  - Modo conservador: threshold sube a 0.75 por 5 ciclos post-reset
  - Pausa automática si hay 3 resets consecutivos sin recuperación
  - Tabla `epochs` en SQLite para comparar performance entre épocas

- [x] **Reducir multiplicador HIGH impact** ✅ 16 abril 2026
  - Cambiado a 0.92 base + ajuste por sentimiento: HIGH positivo no penaliza igual que HIGH negativo
  - Fórmula: `multiplier = min(1.0, 0.92 + sentiment × 0.05)`

- [x] **Mejorar WebSearchAgent** ✅ 16 abril 2026
  - Retry con backoff exponencial (2s, 4s) en DuckDuckGo — 3 intentos por query
  - Queries actualizadas con año/fecha explícita para evitar resultados históricos
  - Filtro de 48h en RSS feeds (descarta artículos viejos)

### Prioridad Baja

- [x] Reemplazar `datetime.utcnow()` por `datetime.now(timezone.utc)` ✅ 16 abril 2026
- [x] Persistencia de sesión en dashboard — localStorage guarda last_decision, last_news, portfolio, agent_votes ✅ 16 abril 2026
- [x] Soporte multi-par por ciclo — analiza top 3 pares, ejecuta en el de mayor score accionable ✅ 16 abril 2026

---

## Archivos de Configuración

- [ ] `.env` creado con todas las keys (basado en `.env.example`)
- [ ] `.env.example` creado en el repo (sin valores reales)
- [ ] `.gitignore` incluye `.env` y archivos sensibles
- [ ] `requirements.txt` generado (`pip freeze > requirements.txt`)
- [ ] `docker-compose.yml` creado para Redis + servicios opcionales

---

## Estado General

| Fase | Estado | Notas |
|------|--------|-------|
| 0 - Entorno | ✅ Completada | 14 abril 2026 |
| 1 - Modelo Local | ✅ Completada | 13 abril 2026 — Qwen2.5:14b en GPU Vulkan |
| 2 - MemPalace | ✅ Completada | 14 abril 2026 — 751 drawers, MCP conectado |
| 3 - Vibe-Trading | ✅ Completada | 14 abril 2026 — gpt-4o-mini, 69 skills |
| 3.5 - WebSearchAgent | ✅ Completada | 14 abril 2026 — DuckDuckGo + RSS funcionando |
| 4 - Binance Testnet | ✅ Completada | 15 abril 2026 — 454 assets, BTC/ETH/USDT verificados |
| 5 - Orquestación | ✅ Completada | 15 abril 2026 — 5/5 agentes OK, pesos rebalanceados, Qwen3.5-plus integrado |
| 6 - Cliente Binance | ✅ Completada | 15 abril 2026 — market data real, indicadores, scanner de volumen |
| 7 - FastAPI | ✅ Completada | 15 abril 2026 — 5 rutas REST + WebSocket + 7 eventos broadcast |

| 8 - Dashboard React | ✅ Completada | 15 abril 2026 — Vite+React+TS+Tailwind v4, 6 paneles, WS live |
| 9 - Integración | ✅ Completada | 15 abril 2026 — asyncio.gather 3 loops, gate-check, SL/TP automático |
| 10 - CLAUDE.md | ✅ Completada | 15 abril 2026 — CLAUDE.md + 4 skills + .mcp.json |
