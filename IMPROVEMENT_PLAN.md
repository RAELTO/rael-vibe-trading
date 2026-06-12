# Plan de mejoras — Vibe Trading

> **Estado de referencia (2026-06-11):** producción corre en el VPS (`core/orchestrator.py`), monitoreo vía dashboard en Vercel (`rael-vibe-trading-dashboard.vercel.app`). Modo `DEEPSEEK_SINGLE` con `deepseek-v4-pro` como decisor único, Claude solo como **módulo de aprendizaje** (post-mortems + daily review, `CLAUDE_ADVISOR_ENABLED=true`; auditor en línea eliminado del flujo), y MiMo v2.5 Pro vía OpenRouter como **fallback de noticias** cuando se agota el presupuesto de OpenAI.
>
> **Datos reales (dashboard, epoch actual):** 8 ops cerradas, win rate 62.5%, +10.44 USDT, **8/8 SHORT**, racha actual −2 (dos SL consecutivos en entradas counter-trend). El daily review de Claude ya señaló: sesgo persistente a shorts y pobre disciplina de entrada tras la racha.

Prioridades: **P0** = corregir/medir antes de tocar nada más · **P1** = mayor impacto en calidad de decisión · **P2** = expansión de capacidad barata · **P3** = mantenibilidad.

---

## P0.1 — Bug: cierre atribuido a `TP` con PnL negativo

**Evidencia:** trade del Jun 4 06:09 — SHORT entry `62,800.1` → exit `63,204.9`, reason `TP`, PnL `−0.65`. En un short, un exit POR ENCIMA del entry no puede ser TP. La lección auto-generada "TP hit but price reversed against short" es el modelo intentando explicar un dato corrupto: **contamina el loop de aprendizaje** (las lecciones se inyectan al prompt del decisor).

**Dónde mirar:**
- `core/orchestrator.py:360` `_resolve_close_from_binance()` — la inferencia de TP/SL/LIQUIDATED a partir de REALIZED_PNL + fills. Probable confusión de lado al emparejar la orden de cierre, o uso del orderId equivocado (los dos últimos commits `1dbe521`/`3fb8ea2` tocaron justo la recuperación de orderId — validar contra los datos del VPS).
- `core/orchestrator.py:437` `_verify_close_consistency()` — ya existe; **extenderlo** para validar coherencia direccional.

**Implementación:**
1. En `_verify_close_consistency`, añadir reglas duras (con tolerancia por fees/slippage, p.ej. 0.1%):
   - `SHORT` + `exit_reason=TP` ⇒ `exit_price < entry_price`; `SHORT` + `SL` ⇒ `exit_price > entry_price` (invertido para LONG).
   - `exit_reason=TP` ⇒ `pnl > 0`; `exit_reason=SL` ⇒ `pnl < 0`.
   - Si falla: reclasificar `exit_reason` a `MANUAL/UNKNOWN`, registrar `system_event` y loggear el payload completo de fills para diagnóstico.
2. **Guard del post-mortem:** en `_run_post_mortem` (`orchestrator.py:2006`), si el trade no pasa la verificación de coherencia, NO generar lección (o marcarla `data_quality=suspect` y excluirla de `get_lessons_summary`).
3. Backfill: script one-shot que recorra `trades` cerrados en la DB del VPS, marque los incoherentes y purgue las lecciones derivadas de ellos.

**Aceptación:** ningún trade cerrado en DB viola las reglas direccionales; las lecciones existentes contaminadas quedan excluidas del prompt.

---

## P0.2 — Harness de evaluación contrafactual (shadow signals)

**Problema:** con ~8 trades por epoch no hay muestra para calibrar nada (umbral, prompt, modelo). Cada decisión del decisor — incluidos HOLD y señales sub-umbral — es un experimento gratis que hoy se tira.

**Diseño:**
1. Nueva tabla en `core/state_store.py`:
   ```sql
   CREATE TABLE IF NOT EXISTS shadow_signals (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     ts TEXT NOT NULL,                -- UTC ISO con +00:00
     cycle INTEGER,
     vote TEXT NOT NULL,              -- BUY | SELL | HOLD
     confidence REAL NOT NULL,
     executed INTEGER DEFAULT 0,      -- 1 si se convirtió en trade real
     blocked_reason TEXT,             -- umbral / riesgo / cooldown / etc.
     entry_price REAL NOT NULL,
     sl_price REAL, tp_price REAL,    -- los que habría usado el sistema
     status TEXT DEFAULT 'PENDING',   -- PENDING | TP_FIRST | SL_FIRST | EXPIRED
     resolved_ts TEXT,
     horizon_hours INTEGER DEFAULT 48
   );
   ```
2. **Registro:** al final de `_run_single_decision_cycle` (`orchestrator.py:890`), guardar TODA señal BUY/SELL con el SL (−1.5%) y el TP adaptativo (`calculate_adaptive_tp`) que se habrían usado, ejecutada o no, con `blocked_reason` cuando aplique. Para HOLD basta registrar vote+confidence (sirve para la curva de calibración, no se resuelve).
3. **Resolución:** loop horario (o pegado al MarketRefresh) que tome los `PENDING`, baje klines 15m desde `ts` (`futures_klines`) y determine qué tocó primero (TP o SL, usando high/low de cada vela; si ambos en la misma vela ⇒ `SL_FIRST` conservador). `EXPIRED` a las 48h.
4. **Métricas** (endpoint en `api/main.py` + panel en dashboard):
   - Tasa TP-first por bucket de confianza (0.50–0.55, 0.55–0.60, …) ⇒ curva de calibración real del decisor.
   - Comparativa señales ejecutadas vs bloqueadas (¿los gates bloquean bien?).
   - Distribución direccional BUY/SELL (monitorear el sesgo short detectado).

**Uso:** ajustar `MIN_CONVICTION` con datos (¿0.58 es el codo real de la curva?), y A/B de cualquier cambio de prompt/modelo (P1) comparando cohortes de shadow signals antes/después.

**Aceptación:** tras 2 semanas en el VPS hay >200 señales resueltas y el dashboard muestra la curva de calibración.

---

## P1.1 — DeepSeek: razonamiento en la decisión

Hoy la decisión es una llamada greedy (`temperature=0.0`) en modo chat. A 96 ciclos/día el costo de habilitar thinking sigue siendo de centavos, y ponderar 6 dimensiones (técnicos, derivados, noticias, historial, lecciones, posición activa) es el caso de uso ideal de un modelo razonador.

**Implementación (`agents/deepseek_decision_agent.py`):**
1. Hacerlo config-driven: probar la variante con razonamiento de DeepSeek (vía `DEEPSEEK_DECISION_MODEL`, p.ej. `deepseek-reasoner` o el toggle de thinking de v4-pro según lo que exponga la API al momento de implementar)(Usando un loader indicador en dashboard de que el modelo está pensando). El parser ya tolera `reasoning_content` (`deepseek_decision_agent.py:278`) y tiene salvage de JSON malformado — reutilizar tal cual.
2. Subir `max_tokens` si hace falta para que el JSON quepa tras el thinking (mismo aprendizaje que con MiMo: el cap alto no cuesta de más, solo se facturan tokens generados).
3. Validar con el shadow harness (P0.2): correr 1 semana el modelo razonador y comparar tasa TP-first por bucket contra la cohorte previa. **No adoptar a ciegas.**

## P1.2 — DeepSeek: self-consistency en señales borderline

Una sola muestra greedy decide hoy abrir un short de $600. En la banda incierta, votar entre muestras elimina esa fragilidad por un costo despreciable.

**Implementación:**
1. Env: `DECISION_SELF_CONSISTENCY=true`, `SC_BAND_LOW=0.55`, `SC_BAND_HIGH=0.65`, `SC_SAMPLES=3`.
2. En `_run_single_decision_cycle`: si `vote ∈ {BUY,SELL}` y `confidence` cae en la banda ⇒ lanzar `SC_SAMPLES−1` llamadas adicionales con `temperature=0.6` (en paralelo, `asyncio.gather`).
3. Regla: ejecutar solo si la mayoría coincide en dirección; confianza final = mediana. Si no hay mayoría ⇒ HOLD con razón "self-consistency disagreement" (registrar en shadow signals con `blocked_reason`).
4. Broadcast al dashboard de los votos individuales (reutilizar `broadcast_agent_vote` con sufijo `#2`, `#3`).

## P1.3 — DeepSeek: aprovechar el context caching (reordenar el prompt)

El prefix cache de DeepSeek es automático pero solo cubre el prefijo **estático**. Hoy el user prompt arranca con datos dinámicos (precio, RSI) y deja el bloque más largo y fijo ("Decision rules", ~500 tokens) al final ⇒ cache hit casi nulo.

**Implementación (`deepseek_decision_agent.py`):**
1. Mover el bloque completo de "Decision rules" y el esquema JSON de respuesta al `SYSTEM_PROMPT`.
2. Reordenar el user prompt: primero lo semi-estable (lessons, vetoes, historial), al final lo que cambia cada ciclo (mercado, derivados, posición).
3. Verificar en la respuesta de la API los campos de cache (`prompt_cache_hit_tokens`) y loggearlos en `_log_decision_debug` para confirmar el hit.

## P1.4 — DeepSeek: multi-timeframe + dieta de tokens

Decide cada 15 min con SL de 1.5% pero solo ve **50 velas de 1h** (`execution/binance_futures.py:72`) — le falta la estructura intradía.

**Implementación:**
1. `get_market_data`: añadir un segundo fetch de klines `15m` (últimas ~64) y un resumen `4h` (solo OHLC de las últimas 12, para contexto de tendencia). Exponer como `closes_15m`, `highs_15m`, `lows_15m`, `summary_4h`.
2. En el prompt, presentar las series **redondeadas** (precios BTC a enteros, volúmenes a 1 decimal) — las series actuales con floats completos queman cientos de tokens por ciclo sin aportar señal.
3. Calcular RSI/EMA también sobre 15m y etiquetar claramente cada timeframe en el prompt ("1H trend / 15M entry timing").
4. Medir con shadow harness antes/después.

## P1.5 — Riesgo: cooldown por racha de SLs (codifica el ajuste del daily review)

El daily review ya lo pidió explícitamente: *"After two consecutive stop-loss hits, impose a mandatory 24-hour cooldown on new directional entries"*. Con `FUTURES_MAX_DAILY_LOSS_PCT=0`, entre cero y el hard stop de $700 no hay ninguna red — esta es la red conductual.

**Implementación:**
1. Env: `FUTURES_LOSS_STREAK_LIMIT=2`, `FUTURES_COOLDOWN_HOURS=24` (0 = desactivado).
2. `core/risk_manager.py`: trackear racha de cierres SL consecutivos (alimentada desde `_finalize_close`); si `streak >= limit` ⇒ `validate_futures_order` rechaza con razón explícita hasta que pase el cooldown.
3. **Persistir** racha y timestamp del cooldown en `state_store` (sobrevivir reinicios del VPS).
4. Mostrar el estado de cooldown en el dashboard (badge en el header, junto a HEALTHY/RUNNING) y registrarlo como `system_event`.
5. El cooldown NO afecta al PositionMonitor ni a la gestión de la posición abierta — solo bloquea entradas nuevas.

## P1.6 — Riesgo: gate estructural para shorts (corrige el sesgo 8/8 SHORT)

Segundo ajuste del daily review: los dos peores trades fueron shorts mono-factor contra momentum en recuperación. Codificarlo como gate de código (siempre activo), no como instrucción de prompt.

**Implementación:**
1. Env: `SHORT_STRUCTURE_GATE=true`, exigir **2 de 3** confirmaciones para ejecutar un SELL:
   - `price < EMA20 < EMA50` (o al menos `price < EMA20` y `price < EMA50`),
   - lower-high confirmado en 1H (computable con `highs[-N:]`),
   - funding anualizado > umbral (p.ej. 100%, crowded longs).
2. Implementar como método en `RiskManager` (recibe `market_data`), llamado desde `_execute_futures_order` antes de abrir. Si bloquea ⇒ `save_gate_result` (alimenta el feedback `audit_vetoes` que ya llega al prompt del decisor — la tubería existe).
3. Simétrico opcional para LONGs (price > EMAs, higher-low, funding muy negativo) — dejar para después de validar el de shorts.
4. Medir con shadow signals: ¿qué habría pasado con los SELLs bloqueados?

## P1.7 — Riesgo: SL/TP escalados por volatilidad (ATR)

El SL fijo de 1.5% es estrecho cuando BTC se mueve 4% diario y holgado cuando se mueve 1%. Coherente con el principio del proyecto: **el sizing/SL/TP es código, no modelo**.

**Implementación:**
1. `binance_futures.py`: añadir `_calc_atr(highs, lows, closes, period=14)` (sobre velas 1h).
2. SL dinámico: `sl_pct = clamp(1.2 × ATR%, 1.0%, 2.5%)`. TP adaptativo existente (`calculate_adaptive_tp`) se mantiene, pero su banda `[1.5%, 4%]` pasa a `[max(1.5%, sl_pct), 4%]`.
3. El gate `MIN_REWARD_RISK=1.2` queda intacto y sigue siendo el árbitro final.
4. El trailing stop (`_check_trailing_stop`) debe leer el `sl_pct` real del trade (ya se persiste `sl_price` — verificar que no asuma 1.5% hardcodeado).

---

## P2.1 — MiMo: segunda opinión barata en señales borderline

El auditor Claude se eliminó porque sobre-vetaba (3+ días sin ejecutar). Pero la infraestructura del veto (`save_gate_result`, feedback `audit_vetoes` al prompt) sigue viva y es valiosa. Reemplazo: MiMo como abogado del diablo **solo en la banda incierta**, donde el costo de equivocarse es máximo y el veto no puede paralizar el sistema.

**Implementación:**
1. Nuevo `agents/mimo_review_agent.py` — cliente OpenRouter (`xiaomi/mimo-v2.5-pro`, **sin** `:online`; reutiliza `OPENROUTER_API_KEY`). Prompt: "given this trade thesis and market snapshot, what would invalidate it? Approve only if the thesis survives" ⇒ JSON `{approved, reason}`.
2. Env: `MIMO_REVIEW_ENABLED=true`, `MIMO_REVIEW_BAND_LOW=0.58`, `MIMO_REVIEW_BAND_HIGH=0.68`, `MIMO_REVIEW_MODEL=xiaomi/mimo-v2.5-pro`, `MIMO_REVIEW_MAX_TOKENS=5000` (mismo aprendizaje de truncamiento: es modelo razonador, thinking 1.4k–2.6k tokens).
3. Trigger en `_run_single_decision_cycle`: solo si `vote ∈ {BUY,SELL}` y `confidence` en banda. Señales con convicción > banda pasan directo (no repetir el sobre-veto de Claude).
4. Veto unidireccional + **fail-open** (mismo contrato que tenía el auditor). Registrar con `save_gate_result` ⇒ el decisor ve los vetos en su siguiente ciclo automáticamente.
5. Dashboard: reutilizar el slot visual del antiguo claude-auditor (tag `REVIEW`).
6. Medir con shadow signals: comparar outcome de señales vetadas vs aprobadas. Si MiMo también sobre-veta, hay datos para apagarlo.

## P2.2 — MiMo: verificación cruzada de catalizadores

Un `verified_catalyst=true` de la ruta primaria puede subir convicción y mover dinero real. Una confirmación independiente barata reduce el riesgo de operar sobre una alucinación de GPT. Solo se dispara en catalizadores (raros) ⇒ costo marginal.

**Implementación (`agents/web_search_agent.py`):**
1. Si la ruta primaria devuelve `verified_catalyst=true` y `catalyst_veracity >= 0.7` ⇒ segunda llamada con `xiaomi/mimo-v2.5-pro:online` preguntando SOLO por ese evento concreto: "confirm or deny with sources: {catalyst_evidence}".
2. Si MiMo no lo confirma ⇒ degradar `catalyst_veracity` a 0.5 y `verified_catalyst=false` (el guardarraíl existente de `_parse_context` ya degrada `market_impact` en consecuencia).
3. Env: `CATALYST_CROSSCHECK_ENABLED=true`.

## P2.3 — Observabilidad de la ruta de noticias

Hoy, si OpenAI se queda sin créditos y entra el fallback MiMo, solo se ve en la consola del VPS.

**Implementación:** añadir `news_source_route: "openai" | "mimo-fallback" | "default"` al contexto que produce `analyze_with_gpt_search()`, propagarlo a `app_state` y mostrarlo en el panel Market Intelligence del dashboard (badge pequeño). Registrar `system_event` en cada transición primaria→fallback.

---

## P3.1 — Limpieza de código muerto (Kronos, agentes locales, legacy)

Producción es `DEEPSEEK_SINGLE` puro; todo lo demás es peso muerto que infla el orquestador y los deploys del VPS.

**Eliminar (sin decisión pendiente):**
| Qué | Dónde |
|---|---|
| Sub-repo Kronos completo | `Kronos/` |
| Agente Kronos | `agents/kronos_agent.py` |
| Agente local (Ollama) | `agents/local_agent.py` + import/instanciación en `core/orchestrator.py:35,160,234` |
| Llamadas a `local_agent.gate_check` | `core/orchestrator.py:1505,1619` (ya bypassed en DEEPSEEK_SINGLE — eliminar la rama legacy) |
| Agente Gemini | `agents/gemini_agent.py`, `tests/test_gemini.py` |
| Pesos de kronos en el decider | `core/decider.py:21,34,45` |
| Vars de entorno muertas | `.env.example`: `OLLAMA_BASE_URL`, `LOCAL_MODEL`, `GOOGLE_API_KEY`, `GEMINI_MODEL` |
| Repo de referencia embebido | `Vibe-Trading/` (clon externo — borrar del repo o mover fuera) |

**Eliminar (recomendado, decisión explícita):** los modos legacy completos `ENSEMBLE` y `MULTI_AGENT` — `agents/{claude,qwen,deepseek,gpt}_agent.py`, `agents/{technical,sentiment,quant,synthesis,gate}_agent.py`, `core/decider.py`, y en el orquestador `_run_pipeline_cycle` + `_collect_votes` + el registro de esos agentes. El historial de git los preserva si algún día se quieren resucitar. Esto recorta `orchestrator.py` en varios cientos de líneas de un golpe.

**Después de borrar:** depurar `requirements.txt` (torch/transformers si solo los usaba Kronos; verificar que pandas/numpy no se usen en otro lado), actualizar `CLAUDE.md` (árbol de arquitectura y sección de modos legacy) y los docs raíz obsoletos (`MULTI_AGENT_PLAN.md`).

**Aceptación:** `python core/orchestrator.py` arranca limpio en el VPS sin los módulos eliminados; `grep -ri "kronos\|ollama\|gemini"` en `core/ agents/ api/` no devuelve nada.

## P3.2 — Reorganización del orquestador y utilidades compartidas

`core/orchestrator.py` tiene ~2.300 líneas y 6 responsabilidades. Tras la limpieza P3.1, dividir:

```
core/
  orchestrator.py        ← solo wiring: arranque, asyncio.gather, shutdown
  trading_cycle.py       ← _run_cycle, _run_single_decision_cycle, _build_context
  position_monitor.py    ← _enforce_tp_sl, _check_trailing_stop, _finalize_close,
                            _resolve_close_from_binance, _reconcile_open_trades
  execution_service.py   ← _execute_futures_order, _execute_spot_order
  learning.py            ← _run_post_mortem, _maybe_daily_review
agents/
  _json_utils.py         ← parser JSON-de-LLM compartido (hoy hay 3 copias casi
                            idénticas en deepseek_decision, claude_advisor y web_search)
```

Mecánico, sin cambios de comportamiento; hacerlo en un PR aparte de cualquier cambio funcional. Aprovechar para decidir el destino de `_log_decision_debug` (marcado "quitar cuando ya no haga falta") — recomendación: mantenerlo detrás de `DECISION_DEBUG_LOG=true`.

---

## Orden de implementación sugerido

| Fase | Items | Razón |
|---|---|---|
| 1 | **P0.1** (bug TP/SL) + **P0.2** (shadow harness) | Sin datos limpios y sin medición, el resto es fe |
| 2 | **P1.5** (cooldown) + **P1.6** (gate shorts) | Riesgo: tapan el hueco que el daily review ya señaló, son baratos y no dependen de nada |
| 3 | **P1.3** (cache) + **P1.4** (multi-timeframe) | Mejor input para el decisor, costo menor por ciclo |
| 4 | **P1.1** (razonamiento) y/o **P1.2** (self-consistency) | El salto de calidad del decisor — validar con el harness de la fase 1 |
| 5 | **P2.1–P2.3** (MiMo review + crosscheck + observabilidad) | Expansión barata una vez el núcleo está medido |
| 6 | **P3.1** (limpieza) → **P3.2** (reorganización) | En cualquier momento; ideal antes de la fase 5 para no refactorizar sobre código muerto |
| — | **P1.7** (ATR) | Después de tener ≥2 semanas de shadow data para validar las bandas |

**Regla transversal:** todo cambio que toque la calidad de decisión (fases 3–5 y P1.7) se valida contra el shadow harness comparando cohortes antes/después — nunca por sensación con 8 trades de muestra.
