# 💰 Estrategia de Costo — Claude API como Cerebro Central

> Decisión tomada el 14 de abril de 2026. Referencia rápida para implementación.

---

## El Rol de Claude en el Sistema

Claude Sonnet 4.6 es el **agente de análisis profundo** dentro del sistema multi-agente. Es el experto en:
- Análisis técnico profundo (RSI, MACD, Elliott Wave, SMC, Ichimoku)
- Cálculos estadísticos y quant
- Interpretación de noticias geopolíticas en términos de mercado
- Voto ponderado en el Decider junto a Gemini y GPT

**Peso en el Decider: 40-45%** — suficiente para ser el agente con mayor influencia sin crear dependencia de un solo modelo. Si Claude falla o está caído, Gemini (30%) + GPT (20%) + Qwen (10%) siguen operando con 60% del sistema intacto.

---

## Configuración Óptima

| Parámetro | Valor |
|---|---|
| Modelo | Claude Sonnet 4.6 |
| Frecuencia de consulta | **cada 25 minutos** |
| Prompt caching | ✅ Activado |
| Formato de respuesta | JSON corto (~150 tokens) |
| Presupuesto | $30 USD |
| Duración estimada | **~3 meses** |

---

## Por qué funciona: Prompt Caching

La mayor parte del prompt de Claude es **siempre igual** — el CLAUDE.md, las skills de trading, el contexto base. Con caching activado, esa parte se paga completa solo la primera vez y al 10% en todas las siguientes.

```
PARTE FIJA → se cachea (paga 10% desde la 2da llamada)
  CLAUDE.md + skills de trading     ~2,000 tokens
  Skills de análisis técnico        ~1,500 tokens
  Contexto base de MemPalace        ~500 tokens
  Total cacheado:                   ~4,000 tokens

PARTE VARIABLE → siempre nueva (paga precio completo)
  Precio actual + OHLCV             ~300 tokens
  RSI, MACD, indicadores            ~200 tokens
  Resumen de noticias               ~300 tokens
  Votos de Gemini y GPT             ~200 tokens
  Total fresco:                     ~1,000 tokens

OUTPUT de Claude (JSON estructurado) ~150 tokens
```

> **Nota sobre el TTL del cache (5 min):** El cache de Sonnet expira a los 5 minutos. Con ciclos de 25 min el cache no persiste entre ciclos — pero sí aplica **dentro del mismo ciclo** cuando se analizan múltiples pares. Con BTCUSDT y ETHUSDT en el mismo ciclo, el segundo análisis ya aprovecha el cache del primero. El ahorro real es ligeramente mayor al calculado abajo.

---

## Cálculo de Costo Mensual

```
58 ciclos/día (cada 25 min) × 2 pares (BTCUSDT + ETHUSDT) = 116 llamadas/día

Primer análisis del ciclo (sin cache):
  Input cacheado   (4,000t × 10% = 400t) × 58:
    23,200 tokens × $3/1M =              $0.070/día
  Input fresco     (1,000t) × 58:
    58,000 tokens × $3/1M =              $0.174/día

Segundo análisis del ciclo (mismo par alterno, cache aún activo <5min):
  Input cacheado   (4,000t × 10% = 400t) × 58:
    23,200 tokens × $3/1M =              $0.070/día
  Input fresco     (1,000t) × 58:
    58,000 tokens × $3/1M =              $0.174/día

Output JSON corto (150t × 116 llamadas):
  17,400 tokens × $15/1M =               $0.261/día

──────────────────────────────────────────────────
Total diario (2 pares):    ~$0.749/día
Total mensual:             ~$22.47/mes   ← con 2 pares
Total mensual (1 par):     ~$11.24/mes   ← si se empieza solo con BTC

$30 ÷ $22.47 = 1.3 meses con 2 pares
$30 ÷ $11.24 = 2.7 meses con 1 par

→ Recomendado: comenzar solo BTCUSDT hasta validar el sistema,
  luego agregar ETHUSDT cuando el presupuesto lo permita.
```

---

## Comparativa de Frecuencias (1 par — BTCUSDT)

| Frecuencia | Llamadas/día | Costo/mes | $30 dura |
|---|---|---|---|
| Cada 15 min | 96 | ~$18.72 | 1.6 meses ❌ |
| Cada 20 min | 72 | ~$14.04 | 2.1 meses ❌ |
| **Cada 25 min** | **58** | **~$11.24** | **2.7 meses ✅** |
| Cada 30 min | 48 | ~$9.36 | 3.2 meses ✅ |

> Con 2 pares activos, multiplicar el costo por ~2. Empezar con 1 par.

---

## Formato de Respuesta Esperado de Claude

Claude razona internamente con toda su profundidad analítica, pero su **output final** es JSON compacto para no desperdiciar tokens en texto explicativo largo:

```json
{
  "vote": "SELL",
  "confidence": 0.82,
  "reasoning": "RSI=71 sobrecompra + MACD cruce bajista + volumen -15%",
  "regime": "OVERBOUGHT",
  "stop_loss_pct": 1.5,
  "take_profit_pct": 3.0,
  "news_impact": "HIGH",
  "gemini_agreement": true,
  "gpt_agreement": false,
  "final_recommendation": "SELL con stop en 1.5%"
}
```

El razonamiento profundo ocurre — solo no se desperdician tokens enviándolo como texto libre.

---

## Implementación del Caching en Python

```python
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# System prompt con cache_control — se cachea automáticamente
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=300,  # Limitar output para controlar costo
    system=[
        {
            "type": "text",
            "text": CLAUDE_MD_CONTENT + TRADING_SKILLS,
            "cache_control": {"type": "ephemeral"}  # ← CLAVE
        }
    ],
    messages=[
        {
            "role": "user",
            "content": f"""
Analiza y vota. Datos actuales:
Par: {symbol} | Precio: {price}
RSI: {rsi} | MACD: {macd} | Volumen: {volume_pct}%
Noticias: {news_summary}
Gemini vota: {gemini_vote} ({gemini_confidence})
GPT vota: {gpt_vote} ({gpt_confidence})

Responde SOLO con JSON.
"""
        }
    ]
)
```

---

## Variables de entorno relevantes

```env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_INTERVAL_SECONDS=1500    # 25 minutos
CLAUDE_MAX_OUTPUT_TOKENS=300    # Limitar output
CLAUDE_BUDGET_USD=30.00         # Presupuesto total
CLAUDE_MONTHLY_LIMIT_USD=10.50  # Alerta si supera esto
```

---

## Notas Importantes

- **Cache TTL 5 min:** se renueva por ciclo, pero sí aplica dentro del mismo ciclo si hay múltiples pares. El cálculo arriba ya lo refleja correctamente.
- **Haiku 4.5 como fallback** ($1/$5 por MTok vs $3/$15 de Sonnet): dos usos recomendados:
  1. `WebSearchAgent` — ya implementado con Haiku (análisis de noticias, tarea repetitiva y de bajo costo)
  2. Fallback automático de `ClaudeAgent` si el gasto mensual supera `CLAUDE_MONTHLY_LIMIT_USD`
- **Peso en el Decider:** mantener en 40-45%. No subir a 60-70% — la redundancia multi-agente es la ventaja del sistema. Si Claude está caído, los otros agentes cubren el 60% restante.
- Los $30 son solo para Claude API — Gemini es gratis, GPT-5.4-nano tiene su propio presupuesto separado.
- Configurar alertas de gasto en **platform.anthropic.com** en $10 y $20 para no sorprenderse.
- Empezar **solo con BTCUSDT** hasta validar que el sistema funciona correctamente, luego agregar ETHUSDT.

---

*Documento de referencia — 14 de abril de 2026*
*Sistema: Multi-Agent Trading · Testnet Binance · Claude como cerebro central*
