# Vibe Trading — Multi-Agent Crypto Trading System

Sistema automatizado de daytrading en **Binance Demo (USD-M Futures)** coordinado por seis agentes de IA que votan con pesos ponderados. Un orquestador central agrega los votos, aplica gestión de riesgo y ejecuta órdenes con stop-loss y take-profit automáticos, todo monitoreable desde un dashboard React en tiempo real.

---

## Arquitectura general

```
python core/orchestrator.py
        │
        ├── asyncio.gather()
        │       ├── FastAPI + WebSocket  (:8000)
        │       ├── WebSearchAgent loop  (cada 30 min)
        │       ├── Trading loop         (cada 20 min)
        │       ├── Position monitor     (cada 3 min)
        │       └── Reconnect loop       (agentes caídos)
        │
        │   Por ciclo de trading:
        │   1. Verificar hard stop (balance efectivo >= $4,600)
        │   2. Seleccionar par (volumen / recomendación noticias)
        │   3. Obtener market data desde Binance Demo Futures
        │   4. Lanzar 6 agentes en paralelo con timeout de 60s
        │   5. Decider agrega votos ponderados + ajusta por noticias
        │   6. RiskManager valida la orden (6 reglas)
        │   7. Ejecutar en Binance Demo + colocar SL/TP via Algo API
        │   8. Broadcast al dashboard vía WebSocket
        │
        └── Dashboard React (:5173) — conectado al WS, muestra todo en tiempo real
```

---

## Agentes y pesos de votación

| Agente | Modelo | Peso | Rol | Costo aprox. |
|--------|--------|------|-----|--------------|
| `ClaudeAgent` | claude-sonnet-4-6 | **38%** | Análisis macro + memoria histórica (prompt caching) | ~$0.15/día |
| `QwenAPIAgent` | qwen3-235b-a22b | **20%** | Análisis quant, free tier 1M tokens/modelo | $0 (free tier) |
| `DeepSeekAgent` | deepseek-chat (V3) | **18%** | Análisis matemático/cuantitativo | ~$0.02/día |
| `GPTAgent` | gpt-5.4-nano | **14%** | Segunda opinión, sentimiento macro | ~$0.05/día |
| `KronosAgent` | Kronos-mini (local) | **5%** | Forecasting OHLCV — predice las próximas 5 velas de 1h | $0 (CPU local) |
| `LocalAgent` | Qwen2.5:14b (Ollama) | **5%** | Scanner técnico + gatekeeper final | $0 (GPU local) |
| `WebSearchAgent` | claude-haiku-4-5 | — | Noticias DuckDuckGo + RSS, no vota | ~$0.01/día |
| `GeminiAgent` | gemini-2.5-flash | — | Excluido del voting (20 req/día). Disponible como fallback manual | $0 |

**Redistribución de pesos**: si un agente no responde, su peso se redistribuye automáticamente — 50% al siguiente disponible en jerarquía de confianza, 50% proporcional al resto. Los pesos siempre suman 1.0.

**Nota sobre Qwen**: El `agent_id` incluye el nombre del modelo (`qwen-api(qwen3-235b-a22b)`). El Decider normaliza esto internamente con `_base_id()`.

---

## Modo de trading: USD-M Futures (Demo)

El sistema opera en modo **FUTURES** usando la [Binance Demo Trading API](https://demo-fapi.binance.com) con apalancamiento 3×.

| Parámetro | Valor |
|-----------|-------|
| Plataforma | Binance Demo (`demo-fapi.binance.com`) |
| Modo | USD-M Futures perpetuos |
| Apalancamiento | 3× (conservador) |
| Balance total demo | $5,000 USDT |
| Presupuesto operativo | $1,000 USDT (position sizing) |
| Hard stop | $4,600 USDT (pérdida máxima $400) |
| Stop-loss | −1.5% del precio de entrada |
| Take-profit | +2.5% del precio de entrada |
| SL/TP vía | `POST /fapi/v1/algoOrder` (Algo API) |

### Hard Stop
Cuando el **balance efectivo** (capital inicial $5,000 + PnL acumulado de todos los trades cerrados) cae a $4,600 o menos:
1. Se cancela toda orden pendiente
2. Se cierra la posición activa a mercado
3. Se registra evento `HARD_STOP` en la base de datos
4. El dashboard muestra un banner de alerta con instrucciones de reset
5. El trading loop se detiene hasta reiniciar el sistema

Para resetear el saldo demo, ir a [demo.binance.com](https://demo.binance.com) → Reset Assets.

### Balance efectivo
El balance real de Binance siempre muestra $5,000 (el testnet no descuenta pérdidas reales). El sistema rastrea el **balance efectivo** internamente:

```
balance_efectivo = $5,000 + Σ(PnL de trades cerrados en DB)
```

---

## Stack tecnológico

| Capa | Tecnología | Detalle |
|------|-----------|---------|
| Modelo local | Ollama + Qwen2.5:14b | AMD RX 9060 XT · Vulkan · 37/37 capas en GPU · ~7.5s/análisis |
| Memoria persistente | MemPalace 3.3.0 | ChromaDB (vector) + SQLite (knowledge graph) · MCP conectado |
| Skills financieras | Vibe-Trading 0.1.4 | 69 skills · backtesting · análisis técnico · swarm presets |
| Ejecución | python-binance 1.0.36 | Demo Futures API · Algo API para SL/TP · step_size/tick_size |
| Backend | FastAPI + uvicorn | WebSocket con 10 eventos broadcast · 8 rutas REST |
| Frontend | React 19 + Vite 8 + Tailwind v4 | 8 paneles · auto-reconnect WS · @tanstack/react-query |
| Noticias | DuckDuckGo Search + feedparser | 14 queries en 3 categorías + 2 feeds RSS |

---

## Requisitos previos

### Software
- Python 3.13+
- Node.js 22+
- Ollama corriendo en `localhost:11434` con `qwen2.5:14b` descargado *(opcional — el sistema arranca sin él)*

### Variables de entorno Windows (Sistema)
```
OLLAMA_VULKAN=1
OLLAMA_FLASH_ATTENTION=1
```

### APIs necesarias
| Servicio | Free tier | Notas |
|----------|-----------|-------|
| Anthropic | No | $10 recomendado para pruebas |
| Alibaba DashScope | Sí (1M tokens/modelo) | Endpoint: `dashscope-intl.aliyuncs.com` · modelo: `qwen3-235b-a22b` |
| DeepSeek | No | Muy barato ($0.27/MTok input) |
| OpenAI | No | gpt-5.4-nano · usar `max_completion_tokens` (no `max_tokens`) |
| Google AI | No | Solo como fallback manual (20 req/día) |
| Binance Demo | Sí | Crear cuenta en [demo.binance.com](https://demo.binance.com) · generar API key en el perfil |

---

## Instalación

```bash
# 1. Entrar al proyecto
cd C:\Users\Rael\Desktop\vibe-trading

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate

# 3. Instalar dependencias Python
pip install -r requirements.txt

# 4. Instalar Vibe-Trading (skills financieras)
pip install -e Vibe-Trading/

# 5. Instalar MemPalace
pip install -e mempalace/

# 6. Configurar entorno
cp .env.example .env
# Editar .env con tus API keys

# 7. Instalar dependencias del dashboard
cd dashboard && npm install && cd ..
```

---

## Configuración (.env)

```env
# ── Modelos ────────────────────────────────────────
CLAUDE_MODEL=claude-sonnet-4-6
GEMINI_MODEL=gemini-2.5-flash
GPT_MODEL=gpt-5.4-nano
DEEPSEEK_MODEL=deepseek-chat
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3-235b-a22b
QWEN_MODEL_FALLBACK=qwen-plus
LOCAL_MODEL=qwen2.5:14b
OLLAMA_BASE_URL=http://localhost:11434

# ── Binance Demo Futures ───────────────────────────
BINANCE_FUTURES_API_KEY=<tu_key>
BINANCE_FUTURES_SECRET=<tu_secret>

# ── Modo de trading ────────────────────────────────
TRADING_MODE=FUTURES
FUTURES_LEVERAGE=3
FUTURES_SL_PCT=0.015       # Stop-loss 1.5%
FUTURES_TP_PCT=0.025       # Take-profit 2.5%
POSITION_MONITOR_INTERVAL=180

# ── Presupuesto ────────────────────────────────────
DEMO_BUDGET_USDT=5000.0        # Saldo total del demo
TRADING_BUDGET_USDT=1000.0     # Presupuesto operativo (position sizing)
HARD_STOP_BALANCE=4600.0       # Hard stop si balance efectivo <= $4600

# ── Trading ────────────────────────────────────────
ANALYSIS_INTERVAL_SECONDS=1200
NEWS_INTERVAL_SECONDS=3600
MIN_CONSENSUS_SCORE=0.62
MAX_POSITION_SIZE_PERCENT=2.0
MAX_DAILY_LOSS_PERCENT=5.0
AGENT_TIMEOUT_SECONDS=60

# ── Servidores ────────────────────────────────────
API_PORT=8000
DASHBOARD_PORT=5173
```

---

## Arranque

Necesitas **dos terminales abiertas simultáneamente**.

**Terminal 1 — Orchestrator (backend completo)**
```bash
cd C:\Users\Rael\Desktop\vibe-trading
venv\Scripts\activate
python core/orchestrator.py
```

Verás en consola:
1. Health-checks de los 6 agentes
2. Balance inicial: `$5,000.00 USDT (operativo: $1,000.00)`
3. Ciclo de noticias inicial (puede tardar ~1 min)
4. Loops paralelos iniciados: API + News + Trading + Reconnect + Monitor
5. Cada ciclo de trading con los votos de cada agente en tiempo real

> **Primera vez con Kronos**: descargará los pesos desde HuggingFace (~50 MB). Se cachea en `~/.cache/huggingface/`.

> **Sin Ollama**: `local-qwen` aparecerá como FAIL en el health-check pero el sistema arranca con los 5 agentes restantes. Sus pesos se redistribuyen automáticamente.

**Terminal 2 — Dashboard**
```bash
cd C:\Users\Rael\Desktop\vibe-trading\dashboard
npm run dev
```

Abrir **`http://localhost:5173`** en el navegador.

---

## Flujo de un ciclo de trading

```
[00:00] Cycle #N inicia — verificar hard stop
        └── balance_efectivo = $5000 + Σ PnL_cerrados

[00:01] get_market_data(BTCUSDT)
        └── OHLCV + RSI + MACD + BB + EMA20/50 + funding_rate + open_interest + leverage

[00:02] Lanzar 6 agentes en paralelo (asyncio.gather, timeout=60s)
        ├── ClaudeAgent   → TradingSignal(vote=BUY,  conf=0.74)
        ├── QwenAPIAgent  → TradingSignal(vote=BUY,  conf=0.71)
        ├── DeepSeekAgent → TradingSignal(vote=HOLD, conf=0.58)
        ├── GPTAgent      → TradingSignal(vote=BUY,  conf=0.69)
        ├── KronosAgent   → TradingSignal(vote=BUY,  conf=0.72)
        └── LocalAgent    → TradingSignal(vote=BUY,  conf=0.66)

[00:45] Decider.decide(signals, news_context)
        ├── BUY  score: 0.38×0.74 + 0.20×0.71 + 0.14×0.69 + 0.05×0.72 + 0.05×0.66 = 0.614
        ├── HOLD score: 0.18×0.58 = 0.104
        ├── News multiplier: catalyst BULLISH veracity=0.90 → ×1.15
        └── Final score: 0.614 × 1.15 = 0.706 >= 0.62 → ejecutar BUY

[00:46] RiskManager.validate_order(qty, price, conf) → OK
        ├── place_futures_order(BUY, qty, leverage=3)
        ├── place_stop_loss  → POST /fapi/v1/algoOrder (algoType=CONDITIONAL)
        └── place_take_profit → POST /fapi/v1/algoOrder (algoType=CONDITIONAL)

[cada 3 min] Position monitor
        ├── Actualizar PnL no realizado → broadcast position_update
        ├── Trailing stop: si PnL > 1.5%, mover SL para proteger ganancia
        └── Detectar liquidación o cierre por SL/TP

[20:00] Siguiente ciclo...
```

---

## Dashboard — Guía de la interfaz

Abrir `http://localhost:5173`. Todos los datos se actualizan en tiempo real vía WebSocket.

| Panel | Qué muestra |
|-------|-------------|
| **Header** | Estado del sistema · modo FUTURES/SPOT · ciclo actual · indicador WS |
| **Portfolio** | Balance efectivo · Total PnL · posiciones abiertas |
| **Position Panel** | Posición futures activa: side (LONG/SHORT) · precio entrada/mark · PnL no realizado · precio de liquidación |
| **Last Decision** | Arc SVG de consensus score · par analizado · veredicto final · reasoning del agente líder |
| **Market Chart** | Precio en tiempo real · área chart últimas 50 velas 1h · RSI/MACD/BB/EMA |
| **Agent Votes** | Voto + confianza + reasoning de cada agente con su peso |
| **News / Market Intelligence** | Sentimiento −1/+1 · impacto · asset scores · catalizadores verificados |
| **PnL Chart** | Curva acumulada de PnL · barras por trade (FUTURES win/loss / SPOT win/loss) |
| **Hard Stop Banner** | Modal de alerta cuando se alcanza el límite de pérdida — instrucciones de reset |

---

## Gestión de riesgo

| Regla | Valor | Descripción |
|-------|-------|-------------|
| Consensus mínimo | 0.62 | Score ponderado de los agentes |
| Daily loss máximo | 5% | $50 sobre presupuesto operativo $1,000 |
| Tamaño máximo por posición | 2% | $20 por orden (sobre $1,000 operativo) |
| Posiciones abiertas | 3 | Máximo simultáneas |
| Balance insuficiente | 95% | La orden no puede usar más del 95% del saldo |
| **Hard stop total** | **$4,600** | **Pérdida máxima $400 sobre $5,000 totales** |

**Futures** (modo actual):
- Stop-loss: −1.5% del precio de entrada
- Take-profit: +2.5% del precio de entrada
- Ratio riesgo/recompensa: 1:1.67
- Trailing stop: se activa cuando PnL supera +1.5%, sube el SL para proteger la ganancia

---

## Persistencia SQLite

El sistema guarda todo en `data/vibe_trading.db` (se crea al primer arranque):

| Tabla | Qué guarda |
|-------|-----------|
| `decisions` | Decisión final por ciclo: par, BUY/SELL/HOLD, score, agentes que votaron |
| `votes` | Voto individual de cada agente: confianza, reasoning, timestamp |
| `risk_state` | Estado del RiskManager al final de cada ciclo: daily_loss, open_positions |
| `portfolio_snapshots` | Balance + PnL + PnL% por ciclo |
| `trades` | Cada posición abierta/cerrada: entry/exit price, PnL, SL/TP, leverage, funding fees, sl_order_id |
| `system_events` | Hard stops, epoch resets, eventos críticos |

Al reiniciar, el sistema restaura automáticamente `daily_loss`, `open_positions` y el `sl_order_id` del trailing stop activo.

---

## Estructura de archivos

```
vibe-trading/
├── core/
│   ├── orchestrator.py      # Punto de entrada — asyncio.gather de 5 loops
│   ├── decider.py           # Votación ponderada + multiplicador de noticias + _base_id()
│   ├── risk_manager.py      # Validación de órdenes + cálculo SL/TP
│   ├── state_store.py       # SQLite — trades, decisions, votes, system_events
│   └── epoch_manager.py     # Reset automático de epoch si pérdidas consecutivas
│
├── agents/
│   ├── base_agent.py        # ABC: BaseAgent, TradingSignal, AgentVote
│   ├── claude_agent.py      # Anthropic SDK, prompt caching ephemeral
│   ├── qwen_agent.py        # OpenAI client → DashScope intl, enable_thinking=False
│   ├── deepseek_agent.py    # OpenAI client → api.deepseek.com
│   ├── gpt_agent.py         # OpenAI client, max_completion_tokens (no max_tokens)
│   ├── local_agent.py       # OpenAI client → Ollama :11434, gate_check()
│   ├── kronos_agent.py      # TimeMixer local — forecasting OHLCV, pesos HuggingFace
│   ├── gemini_agent.py      # google-genai SDK, ThinkingConfig(budget=0), solo fallback
│   └── web_search_agent.py  # DuckDuckGo + RSS + Haiku analysis, loop 1h
│
├── execution/
│   ├── binance_futures.py   # BinanceFuturesClient — Demo API, Algo API SL/TP, trailing stop
│   └── binance_testnet.py   # BinanceTestnetClient — SPOT (modo alternativo)
│
├── api/
│   └── main.py              # FastAPI — /health /state /portfolio /decisions /news /risk
│                            # /market/{symbol} /mode/{mode} /pnl-history
│                            # WebSocket /ws — 10 eventos broadcast
│
├── dashboard/               # React 19 + Vite 8 + Tailwind v4
│   └── src/
│       ├── App.tsx
│       ├── hooks/useWebSocket.ts     # WS con auto-reconnect cada 3s
│       └── components/
│           ├── Header.tsx            # Status · modo FUTURES/SPOT · ciclo · WS indicator
│           ├── PortfolioPanel.tsx    # Balance efectivo · PnL · posiciones abiertas
│           ├── PositionPanel.tsx     # Posición futures activa + toggle FUTURES/SPOT
│           ├── DecisionPanel.tsx     # Último par + decisión + arc SVG de confianza
│           ├── MarketChart.tsx       # Precio + area chart + RSI/MACD/BB/EMA
│           ├── AgentVotesPanel.tsx   # Votos actuales + barra de confianza + historial
│           ├── NewsPanel.tsx         # Sentiment -1/+1 · impacto · asset scores
│           ├── PnLChart.tsx          # Curva PnL acumulada + barras por trade
│           ├── HardStopBanner.tsx    # Modal de alerta de hard stop
│           └── ErrorLog.tsx          # Log de errores del sistema
│
├── skills/                  # Skills para Claude Code CLI
├── tests/
├── CLAUDE.md                # Guía del proyecto para Claude Code
├── .mcp.json                # MemPalace MCP — venv local Windows
├── .env                     # API keys (no commitear)
├── .env.example             # Plantilla sin valores reales
├── requirements.txt
└── README.md
```

---

## API Reference

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Estado del servidor |
| `/state` | GET | Estado completo del sistema |
| `/portfolio` | GET | Balance efectivo, PnL, PnL% |
| `/decisions` | GET | Última decisión + votos de agentes |
| `/news` | GET | Último contexto de noticias |
| `/risk` | GET | Salud del risk manager + posiciones abiertas |
| `/market/{symbol}` | GET | Market data + indicadores del par |
| `/mode/{mode}` | POST | Cambiar entre FUTURES y SPOT |
| `/pnl-history` | GET | Trades cerrados con PnL acumulado por ciclo |
| `/ws` | WebSocket | Stream en tiempo real |

### Eventos WebSocket

| Evento | Cuándo | Payload |
|--------|--------|---------|
| `init` | Al conectar | Estado completo del sistema |
| `cycle_start` | Inicio de ciclo | `{cycle, pairs}` |
| `agent_vote` | Por cada agente | `{agent_id, vote, confidence, reasoning}` |
| `decision` | Decisión final | `{symbol, decision, score, reason}` |
| `order_placed` | Orden ejecutada | `{symbol, side, qty, price, sl, tp}` |
| `portfolio_update` | Tras cada ciclo | `{balance, pnl, pnl_pct}` |
| `news_update` | Ciclo de noticias | `{sentiment, impact, summary, assets}` |
| `position_update` | Monitor cada 3 min | `{side, entry_price, mark_price, unrealized_pnl, liquidation_price}` |
| `mode_change` | Cambio FUTURES↔SPOT | `{mode}` |
| `hard_stop` | Hard stop activado | `{message}` |
| `error` | Error del sistema | `{message, ts}` |

---

## Indicadores técnicos

| Indicador | Parámetros | Señal |
|-----------|-----------|-------|
| RSI | period=14 | <30 sobreventa / >70 sobrecompra |
| MACD | EMA12 − EMA26 | >0 bullish / <0 bearish |
| Bollinger Bands | period=20, σ=2 | Precio < BB lower → posible reversión |
| EMA 20 | — | Tendencia corto plazo |
| EMA 50 | — | Tendencia medio plazo |
| Volumen 24h | suma últimas 24 velas 1h | Confirma o niega la señal |
| Funding rate | Binance mark price | >0 longs pagan / <0 shorts pagan |
| Open interest | Binance OI | Confirma convicción del mercado |
| Long/Short ratio | Global top traders | >1 longs dominan / <1 shorts dominan |

---

## Hardware del sistema

| Componente | Especificación |
|-----------|---------------|
| CPU | AMD Ryzen 7 5700X (8c/16t) |
| GPU | AMD Radeon RX 9060 XT — 16 GB VRAM (RDNA4 / gfx1201) |
| RAM | 32 GB DDR4 3200 MHz |
| OS | Windows 11 Pro |
| Backend local | Ollama con Vulkan — 37/37 capas en GPU · 9.0 GB VRAM · Flash Attention ON |

---

## Estado del proyecto

| Fase | Estado | Fecha |
|------|--------|-------|
| 0 - Entorno Windows | Completada | 14 abril 2026 |
| 1 - Modelo Local (Ollama + Qwen2.5:14b) | Completada | 13 abril 2026 |
| 2 - MemPalace (Memoria Persistente) | Completada | 14 abril 2026 |
| 3 - Vibe-Trading (Skills Financieras) | Completada | 14 abril 2026 |
| 3.5 - WebSearchAgent | Completada | 14 abril 2026 |
| 4 - Binance Testnet (SPOT) | Completada | 15 abril 2026 |
| 5 - Orquestación Multi-Agente | Completada | 15 abril 2026 |
| 6 - FastAPI + Dashboard React | Completada | 15 abril 2026 |
| 7 - Modo Futures (Demo API) | Completada | 16 abril 2026 |
| 8 - Algo API (SL/TP post-Dec 2025) | Completada | 16 abril 2026 |
| 9 - Hard Stop + Balance efectivo | Completada | 17 abril 2026 |
| 10 - PositionPanel + PnLChart + HardStopBanner | Completada | 17 abril 2026 |
| 11 - Presupuesto $5K / operativo $1K | Completada | 17 abril 2026 |
