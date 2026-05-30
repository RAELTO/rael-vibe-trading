# Plan: Restructuración Multi-Agente Real
# Vibe Trading — de Ensemble a Pipeline Orquestado

## Problema actual

Los 6 agentes hacen la misma tarea (votar BUY/SELL/HOLD) sobre los mismos datos en paralelo.
El resultado es un promedio ponderado, no inteligencia colectiva real.

---

## Presupuesto disponible (26 abril 2026)

| Proveedor | Saldo | Duración estimada (8h/día) |
|---|---|---|
| DeepSeek | $1.85 | ~85 días (2 llamadas/ciclo × $0.0043) |
| Claude (Anthropic) | $9.35 | ~23 días (1 llamada/ciclo × $0.0165) |
| OpenAI | $9.96 | ~infinite (gate only, $0.000225/ciclo) |
| Qwen DashScope | 952K tokens free (vence 15 jul) | ~12 días 8h/día → fallback qwen3.6-plus free (100%) |
| Kimi K2.6 | sin fondos | pendiente — usar DeepSeek como sustituto temporal |

---

## PLAN A — Temporal (pruebas locales ahora)

Solo modelos con saldo disponible: **DeepSeek + Claude + GPT-5.4-nano**

```
FASE 1 — paralela (2 especialistas)
  [DeepSeek V4 Flash]  → technical_analysis   (price action, patrones, S/R)
  [DeepSeek V4 Flash]  → sentiment_analysis    (noticias/macro — prompt diferente)

        ↓

FASE 2 — síntesis
  [Claude Sonnet 4.6]  → synthesis + final vote + conviction score

        ↓

FASE 3 — gate de riesgo
  [GPT-5.4-nano]       → approved: bool
```

> QuantAgent (Qwen) omitido temporalmente — Claude puede inferir señales quant
> desde el market_data (funding, OI, L/S) que ya recibe en el prompt de síntesis.

### Costo Plan A por ciclo

| Agente | Llamadas | Costo/ciclo |
|---|---|---|
| DeepSeek (technical) | 1 | ~$0.0005 |
| DeepSeek (sentiment) | 1 | ~$0.0005 |
| Claude (synthesis) | 1 | ~$0.0165 |
| GPT (gate) | 0-1 | ~$0.0002 |
| **Total** | | **~$0.018/ciclo** |

### Duración del saldo en Plan A (8h/día = 24 ciclos/día)

| Proveedor | Costo/día | Días restantes |
|---|---|---|
| DeepSeek ($1.85) | $0.024 | **~77 días** |
| Claude ($9.35) | $0.396 | **~23 días** ← binding constraint |
| OpenAI ($9.96) | $0.005 | **~1992 días** |

> **Claude es el límite.** A 8h/día de operación continua, $9.35 dura ~23 días.
> A 4h/día dura ~46 días. Se puede extender reduciendo el intervalo de ciclos.

### Variables de entorno Plan A

```env
# Plan A — Temporal (solo DeepSeek + Claude + GPT)
TECHNICAL_MODEL=deepseek-v4-flash
SENTIMENT_MODEL=deepseek-v4-flash
SYNTHESIS_MODEL=claude-sonnet-4-6
GATE_MODEL=gpt-5.4-nano

MIN_CONVICTION=0.60          # ligeramente más bajo — solo 2 fase-1 en lugar de 3
PHASE1_TIMEOUT_SECONDS=30
SYNTHESIS_TIMEOUT_SECONDS=60
GATE_TIMEOUT_SECONDS=15
```

---

## PLAN B — Principal (producción con todos los modelos)

```
FASE 1 — paralela (3 especialistas)
  [DeepSeek V4 Flash]     → technical_analysis   (OHLCV, patrones, niveles)
  [Qwen3-235b-a22b]       → quant_analysis        (funding, OI, L/S, carry math)
  [Kimi K2.6]             → sentiment_analysis    (noticias, macro, catalizadores)

        ↓

FASE 2 — síntesis
  [Claude Sonnet 4.6]     → synthesis + final vote + conviction score

        ↓

FASE 3 — gate de riesgo
  [GPT-5.4-nano]          → approved: bool
```

### Costo Plan B por ciclo

| Agente | Modelo | Costo/ciclo |
|---|---|---|
| TechnicalAgent | deepseek-v4-flash | ~$0.0005 |
| QuantAgent | qwen3-235b-a22b | $0 (free) |
| SentimentAgent | kimi-k2.6 | ~$0.002 |
| SynthesisAgent | claude-sonnet-4-6 | ~$0.0165 |
| GateAgent | gpt-5.4-nano | ~$0.0002 |
| **Total** | | **~$0.019/ciclo** |

### Variables de entorno Plan B

```env
# Plan B — Principal (todos los modelos)
TECHNICAL_MODEL=deepseek-v4-flash
QUANT_MODEL=qwen3-235b-a22b
QUANT_MODEL_FALLBACK=qwen3.6-plus   # free tier 100% disponible
SENTIMENT_MODEL=kimi-k2.6           # activar cuando haya fondos
SYNTHESIS_MODEL=claude-sonnet-4-6
GATE_MODEL=gpt-5.4-nano

MIN_CONVICTION=0.65
PHASE1_TIMEOUT_SECONDS=45
SYNTHESIS_TIMEOUT_SECONDS=60
GATE_TIMEOUT_SECONDS=15
```

---

## Arquitectura común (ambos planes)

### Output schemas Fase 1

**TechnicalAgent:**
```json
{
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0.0,
  "pattern": "nombre del patrón dominante",
  "key_levels": {"support": 0.0, "resistance": 0.0},
  "trend_structure": "UPTREND|DOWNTREND|CHOPPY",
  "signal_quality": "STRONG|MODERATE|WEAK",
  "analysis": "max 3 sentences"
}
```

**QuantAgent:**
```json
{
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0.0,
  "funding_signal": "CARRY_LONG|CARRY_SHORT|NEUTRAL",
  "oi_signal": "EXPANDING_LONGS|EXPANDING_SHORTS|FLAT",
  "crowd_signal": "CROWDED_LONG|CROWDED_SHORT|BALANCED",
  "squeeze_risk": "HIGH|MEDIUM|LOW",
  "analysis": "max 3 sentences"
}
```

**SentimentAgent:**
```json
{
  "direction": "BULLISH|BEARISH|NEUTRAL",
  "confidence": 0.0,
  "catalyst_present": false,
  "catalyst_strength": "HIGH|MEDIUM|LOW|NONE",
  "market_regime": "RISK_ON|RISK_OFF|UNCERTAIN",
  "analysis": "max 3 sentences"
}
```

### Output schema Fase 2 (Claude Synthesis)

```json
{
  "vote": "BUY|SELL|HOLD",
  "conviction": 0.0,
  "dominant_dimension": "technical|quant|sentiment",
  "confluences": ["señal confirmada por múltiples agentes"],
  "conflicts": "descripción de desacuerdos y por qué se priorizó X",
  "reasoning": "max 3 sentences"
}
```

**Reglas de Claude:**
- 3/3 coinciden → conviction alta (≥0.75)
- 2/3 coinciden → conviction media (0.55-0.70), priorizar dimensión más relevante
- 1/3 coinciden o split total → HOLD
- Plan A (2 agentes): ambos coinciden → conviction media, uno solo → HOLD

### Output schema Fase 3 (Gate)

```json
{"approved": true, "reason": "OK"}
```

---

## Nuevo ciclo en orchestrator.py

```python
async def run_trading_cycle(self):
    # FASE 1 — paralela
    phase1_tasks = [
        self.technical_agent.analyze(market_data),
        self.sentiment_agent.analyze(news_ctx),
    ]
    if hasattr(self, 'quant_agent'):   # solo Plan B
        phase1_tasks.append(self.quant_agent.analyze(market_data))

    results = await asyncio.gather(*phase1_tasks, return_exceptions=True)
    analyses = [r for r in results if not isinstance(r, Exception)]

    await broadcast_phase1(analyses)

    # FASE 2 — Claude sintetiza
    synthesis = await self.synthesis_agent.synthesize(
        analyses=analyses,
        market_data=market_data,
        active_position=context.get("active_position"),
    )
    await broadcast_decision(symbol, synthesis.vote, synthesis.conviction, synthesis.reasoning)

    # FASE 3 — gate (solo si hay señal con convicción)
    if synthesis.vote in ("BUY", "SELL") and synthesis.conviction >= MIN_CONVICTION:
        gate = await self.gate_agent.check(synthesis, self.risk.state)
        if gate.approved:
            await self._execute_order(...)
```

---

## Archivos a crear/modificar

### Nuevos:
- `agents/technical_agent.py`   — DeepSeek, solo price action
- `agents/quant_agent.py`       — Qwen, solo derivados (Plan B)
- `agents/sentiment_agent.py`   — DeepSeek temp / Kimi (Plan B)
- `agents/synthesis_agent.py`   — Claude, síntesis + decisión
- `agents/gate_agent.py`        — GPT-nano, aprobación riesgo

### Eliminar:
- `agents/local_agent.py`
- `agents/kronos_agent.py`
- `agents/claude_agent.py`      → reemplazado por synthesis_agent.py
- `agents/deepseek_agent.py`    → reemplazado por technical_agent.py
- `agents/qwen_agent.py`        → reemplazado por quant_agent.py
- `agents/gpt_agent.py`         → reemplazado por gate_agent.py

### Modificar:
- `core/orchestrator.py`        → ciclo 3 fases, detección Plan A/B
- `core/decider.py`             → conviction-based, sin weighted average
- `api/main.py`                 → broadcast por fases
- `dashboard/src/components/AgentVotesPanel.tsx` → panel Fase 1 + Synthesis separados

---

## Orden de implementación

1. Plan A primero — más simple, 2 agentes en Fase 1
2. Validar con testnet que el pipeline funciona
3. Agregar QuantAgent (Qwen) cuando se quiera activar Plan B
4. Reemplazar SentimentAgent con Kimi K2.6 cuando haya fondos
