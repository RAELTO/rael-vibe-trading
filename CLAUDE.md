# Vibe Trading — Sistema de Crypto Trading con IA

## Identidad del proyecto

Sistema automatizado de daytrading de **BTCUSDT perpetual futures** en Binance Testnet. El modo de decisión por defecto es **`DEEPSEEK_SINGLE`**: un único agente DeepSeek decide BUY/SELL/HOLD con una convicción, y un auditor Claude revisa solo las señales borderline. Un orquestador central coordina los loops, valida riesgos y ejecuta órdenes con stop-loss y take-profit automáticos. Existen modos `MULTI_AGENT` y `ENSEMBLE` (legacy, ver más abajo).

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
core/orchestrator.py      ← Punto de entrada. asyncio.gather de 5 loops:
  │                          API + News + Trading + Reconnect + PositionMonitor
  ├── agents/
  │     deepseek_decision_agent.py  PRIMARIO (modo DEEPSEEK_SINGLE) — decisión única en JSON
  │     claude_audit_agent.py       Auditor — revisa señales borderline antes de ejecutar
  │     web_search_agent.py         Noticias GPT web-search (no vota; corre cada 3h)
  │     claude/qwen/deepseek/gpt/local_agent.py  Ensemble legacy (solo modo ENSEMBLE)
  │     technical/sentiment/quant/synthesis/gate_agent.py  Pipeline legacy (modo MULTI_AGENT)
  ├── core/
  │     decider.py        Votación ponderada (solo ENSEMBLE)
  │     risk_manager.py   Validación de riesgo antes de ejecutar (SIEMPRE se aplica)
  │     state_store.py    Persistencia SQLite (data/vibe_trading.db): trades, decisiones, PnL
  │     epoch_manager.py  Control de drawdown / resets de balance
  ├── execution/
  │     binance_futures.py  Cliente Futures USD-M — OHLCV, órdenes, SL/TP, funding, indicadores
  │     binance_testnet.py  Cliente Spot (modo TRADING_MODE=SPOT)
  ├── api/main.py         FastAPI + WebSocket en :8000 (broadcast al dashboard)
  └── dashboard/          React + Vite + Tailwind en :5173
```

## Flujo de decisión (modo DEEPSEEK_SINGLE)

1. Cada `ANALYSIS_INTERVAL_SECONDS` (15 min) el trading loop arma el contexto (mercado, derivados, noticias, historial de trades, posición activa).
2. **Dentro del horario de trading** llama a `DeepSeekDecisionAgent.analyze()` → devuelve JSON `{vote, confidence, reasoning, ...}`.
3. Si `confidence >= MIN_CONVICTION` y vote es BUY/SELL, y la señal es borderline (`0.58–0.66`), el **auditor Claude** la aprueba o bloquea.
4. `RiskManager.validate_futures_order()` valida tamaño, liquidación, pérdida diaria y máximo de posiciones. **El modelo nunca dimensiona la orden ni fija SL/TP — eso es código.**
5. Se abre la posición con SL/TP automáticos; el PositionMonitor la gestiona 24/7.

### Si se pide a Claude un análisis de trading
Responder ÚNICAMENTE con JSON válido:
```json
{
  "vote": "BUY|SELL|HOLD",
  "confidence": 0.0,
  "reasoning": "máx 3 oraciones con datos concretos",
  "key_signals": ["señal1", "señal2"]
}
```

## Reglas de riesgo (futures — siempre las aplica el código)

- HOLD si `confidence < MIN_CONVICTION` (0.60).
- HOLD si la pérdida diaria alcanza el 3% del balance.
- **Máximo 1 posición de futures abierta a la vez.**
- Tamaño de posición: escala de `MIN_POSITION_USDT` ($500) a `MAX_POSITION_USDT` ($1000) según convicción.
- Stop-loss: **−1.5%** | Take-profit: **+2.5%** | Leverage: **3x**.
- La liquidación debe quedar al menos 2× más lejos que el SL, o se bloquea.
- **Hard stop**: si la pérdida acumulada alcanza `MAX_TRADING_LOSS_USDT` ($600), se suspende el trading.

## Horario de trading

El decisor solo abre posiciones nuevas dentro de la ventana `[TRADING_HOURS_START, TRADING_HOURS_END)` en `TRADING_TIMEZONE`. **El PositionMonitor (SL/TP/trailing/liquidación), el refresco del dashboard y el loop de noticias siguen 24/7.** Fuera de horario el decisor se pausa y solo refresca el dashboard (sin gastar LLM).

## Variables de entorno clave (.env)

| Variable | Valor actual | Nota |
|----------|--------------|------|
| `DECISION_MODE` | `DEEPSEEK_SINGLE` | Modo de decisión. Alternativas: `MULTI_AGENT`, `ENSEMBLE` (legacy) |
| `DEEPSEEK_DECISION_MODEL` | `deepseek-chat` | Modelo decisor principal (JSON mode) |
| `CLAUDE_AUDIT_MODEL` | `claude-sonnet-4-6` | Auditor de señales borderline |
| `TRADING_MODE` | `FUTURES` | `FUTURES` o `SPOT` |
| `ANALYSIS_INTERVAL_SECONDS` | `900` | 15 min entre ciclos de decisión |
| `NEWS_INTERVAL_SECONDS` | `10800` | 3 h entre búsquedas de noticias |
| `MIN_CONVICTION` | `0.60` | Convicción mínima para ejecutar |
| `FUTURES_LEVERAGE` | `3` | Apalancamiento |
| `MIN_POSITION_USDT` / `MAX_POSITION_USDT` | `500` / `1000` | Rango de nocional por posición |
| `MAX_TRADING_LOSS_USDT` | `600` | Pérdida acumulada → hard stop |
| `TRADING_HOURS_ENABLED` | `true` | Activa el horario de trading |
| `TRADING_HOURS_START` / `_END` | `8` / `20` | Ventana activa (hora) |
| `TRADING_TIMEZONE` | `UTC` | Zona de la ventana (ej: `America/Bogota`) |
| `CLAUDE_AUDIT_MIN_CONF` / `_MAX_CONF` | `0.58` / `0.66` | Rango borderline que audita Claude |
| `TRADING_BUDGET_USDT` | `1000.0` | Capital operativo de referencia |
| `AGENT_TIMEOUT_SECONDS` | `60` | Timeout por agente |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | LocalAgent (solo ENSEMBLE) |

## Notas importantes

- **DeepSeek JSON mode**: la llamada usa `response_format={"type":"json_object"}` y `max_tokens=4000`. El prompt DEBE contener la palabra "json" o DeepSeek devuelve content vacío. NO usar `enable_thinking` (es un parámetro de Qwen/DashScope, no de DeepSeek).
- **Cierre de trades**: la fuente de verdad es `_resolve_close_from_binance()` (consulta REALIZED_PNL + fills reales para inferir TP/SL/LIQUIDATED). La usan el arranque (`_reconcile_open_trades`), el `PositionMonitor` y `_check_closed_trades`. No reintroducir cierres con `exit_price = entry_price`.
- **Apagado**: uvicorn NO captura señales (`server.capture_signals` anulado) para que `asyncio.run` maneje Ctrl+C y cancele todos los loops limpiamente.
- **Timestamps**: usar siempre `datetime.now(timezone.utc).isoformat()` (con `+00:00`) — el frontend lo interpreta como UTC. `datetime.utcnow()` produce naive y descuadra el dashboard.
- **Balance**: `get_portfolio_value()` hace `min(real, budget)` — retorna ~$1000 operativo aunque el testnet tenga más.
- **Config del frontend**: el intervalo y el horario se exponen en `app_state["config"]` y llegan al dashboard por el evento WS `init`. No hardcodear el intervalo en el frontend.

### Modos legacy (referencia)
- **`ENSEMBLE`**: 5 agentes (Claude/Qwen/DeepSeek/GPT/Local) votan ponderado vía `decider.py`. Notas: Qwen requiere `extra_body={"enable_thinking": False}`; GPT usa `max_completion_tokens`; Gemini está fuera del pool (cuota baja).
- **`MULTI_AGENT`**: pipeline de 3 fases (especialistas → síntesis Claude → gate).

## Memoria con MemPalace
Wing activo: `vibe_trading`. Al iniciar sesión, ejecutar `mempalace_status` para cargar contexto. Guardar decisiones relevantes en room `core`, noticias en room `agents`.

## Skills disponibles

- `/trading-analyst` — Análisis técnico de un par con JSON output
- `/risk-manager` — Validar si una orden cumple reglas de riesgo
- `/news-interpreter` — Interpretar contexto de noticias para trading
- `/executor` — Revisar si una orden está lista para ejecutarse en testnet
