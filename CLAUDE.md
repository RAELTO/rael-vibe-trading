# Vibe Trading — Sistema Multi-Agente de Crypto Trading

## Identidad del proyecto

Sistema automatizado de daytrading en Binance Testnet. Cinco agentes de IA votan con pesos ponderados sobre decisiones BUY/SELL/HOLD cada 20 minutos. Un orquestador central coordina los votos, valida riesgos y ejecuta órdenes con stop-loss y take-profit automáticos.

## Arranque rápido

```bash
# Terminal 1 — Todo el backend (API + News + Trading)
cd C:\Users\Rael\Desktop\vibe-trading
python core/orchestrator.py

# Terminal 2 — Dashboard React
cd C:\Users\Rael\Desktop\vibe-trading\dashboard
npm run dev
# Abre http://localhost:5173
```

## Arquitectura

```
core/orchestrator.py      ← Punto de entrada. asyncio.gather de 3 loops
  ├── agents/             ← 5 agentes votantes + WebSearchAgent
  │     claude_agent.py   40% peso — prompt caching, memoria histórica
  │     qwen_agent.py     20% — Qwen3.5-plus free tier, DashScope intl
  │     deepseek_agent.py 20% — DeepSeek V3, análisis quant
  │     gpt_agent.py      15% — GPT-5.4-mini
  │     local_agent.py     5% — Qwen2.5:14b local, gatekeeper final
  │     web_search_agent  Noticias DuckDuckGo + RSS cada 30 min (no vota)
  ├── core/
  │     decider.py        Votación ponderada + multiplicador de noticias
  │     risk_manager.py   Validación de riesgo antes de ejecutar
  ├── execution/
  │     binance_testnet.py Cliente Binance Testnet — OHLCV, órdenes, indicadores
  ├── api/main.py         FastAPI + WebSocket en :8000
  └── dashboard/          React + Vite + Tailwind en :5173
```

## Comportamiento esperado al usar Claude en este proyecto

### Análisis de trading
Cuando se pida análisis de un par, responder ÚNICAMENTE con JSON válido:
```json
{
  "vote": "BUY|SELL|HOLD",
  "confidence": 0.0,
  "reasoning": "máx 2 oraciones con datos concretos",
  "key_signals": ["señal1", "señal2"]
}
```

### Reglas de riesgo (siempre aplicar)
- HOLD si confianza < 0.65
- HOLD si daily_loss >= 5% del balance
- Máximo 3 posiciones abiertas simultáneas
- Tamaño máximo por posición: 2% del balance ($20 sobre $1000 demo)
- Stop-loss: -2.5% | Take-profit: +4.0%

### Memoria con MemPalace
Wing activo: `vibe_trading`
Al iniciar sesión, ejecutar `mempalace_status` para cargar contexto del sistema.
Guardar decisiones relevantes en room `core`, noticias en room `agents`.

## Variables de entorno clave (.env)

| Variable | Valor | Nota |
|----------|-------|------|
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Agente principal |
| `DEMO_BUDGET_USDT` | `1000.0` | Presupuesto demo |
| `ANALYSIS_INTERVAL_SECONDS` | `1200` | 20 min entre ciclos |
| `NEWS_INTERVAL_SECONDS` | `1800` | 30 min entre búsquedas |
| `MIN_CONSENSUS_SCORE` | `0.65` | Score mínimo para ejecutar |
| `AGENT_TIMEOUT_SECONDS` | `60` | Timeout por agente |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | LocalAgent |
| `QWEN_BASE_URL` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | Qwen API |

## Notas importantes

- **Gemini 2.5 Flash**: Excluido del voting pool (20 req/día). Usado como fallback manual.
- **Qwen enable_thinking**: SIEMPRE `extra_body={"enable_thinking": False}` — obligatorio para no-streaming.
- **GPT**: Usar `max_completion_tokens`, NO `max_tokens` (da 400 en gpt-5.4).
- **Balance**: `get_portfolio_value()` hace `min(real, DEMO_BUDGET_USDT)` — retorna $1000 aunque testnet tenga $10k.
- **LocalAgent**: Corre Ollama con `OLLAMA_VULKAN=1` + `OLLAMA_FLASH_ATTENTION=1` en variables de sistema Windows.

## Skills disponibles

- `/trading-analyst` — Análisis técnico de un par con JSON output
- `/risk-manager` — Validar si una orden cumple reglas de riesgo
- `/news-interpreter` — Interpretar contexto de noticias para trading
- `/executor` — Revisar si una orden está lista para ejecutarse en testnet
