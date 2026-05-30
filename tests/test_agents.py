import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from agents.local_agent   import LocalAgent
from agents.gemini_agent  import GeminiAgent
from agents.gpt_agent     import GPTAgent
from agents.deepseek_agent import DeepSeekAgent
from core.risk_manager    import RiskManager, OrderRequest

# Datos de mercado simulados
MARKET_DATA = {
    "symbol":    "BTCUSDT",
    "price":     74005.0,
    "rsi":       68.5,
    "macd":      -120.4,
    "bb_upper":  76500.0,
    "bb_lower":  71200.0,
    "ema20":     73800.0,
    "ema50":     72100.0,
    "volume":    1850000000,
    "closes":    [72100, 73000, 73800, 74200, 74005],
}

CONTEXT = {
    "news_sentiment": -0.3,
    "news_impact":    "MEDIUM",
    "key_events":     ["Fed hawkish tone", "BTC ETF outflow"],
    "news_bias":      "SELL",
    "recent_decisions": "Ciclo anterior: HOLD (volumen bajo)",
    "portfolio_balance": "10000.00",
    "open_positions": 0,
    "daily_pnl": "+0.00",
}


async def test_agent(agent, name):
    print(f"\n--- {name} ---")
    try:
        healthy = await agent.health_check()
        print(f"  Health: {'OK' if healthy else 'FAIL'}")
        if healthy:
            signal = await agent.analyze(MARKET_DATA, CONTEXT)
            print(f"  Vote:       {signal.vote.value}")
            print(f"  Confidence: {signal.confidence:.2f}")
            print(f"  Reasoning:  {signal.reasoning}")
    except Exception as e:
        print(f"  ERROR: {e}")


async def main():
    print("=== Test Agentes — Fase 5 ===\n")

    # Agentes API (paralelo)
    from agents.claude_agent import ClaudeAgent
    from agents.qwen_agent   import QwenAPIAgent
    agents = [
        (ClaudeAgent(),   "ClaudeAgent  (40%)"),
        (QwenAPIAgent(),  "QwenAPIAgent (20%)"),
        (DeepSeekAgent(), "DeepSeekAgent(20%)"),
        (GPTAgent(),      "GPTAgent     (15%)"),
        (LocalAgent(),    "LocalAgent   ( 5%)"),
    ]

    for agent, name in agents:
        await test_agent(agent, name)

    # RiskManager
    print("\n--- RiskManager ---")
    rm = RiskManager()
    rm.update_balance(10000.0)

    order_ok = OrderRequest("BTCUSDT", "BUY", 0.00027, 74005.0, confidence=0.72)
    order_low_conf = OrderRequest("BTCUSDT", "BUY", 0.00027, 74005.0, confidence=0.50)
    order_too_big  = OrderRequest("BTCUSDT", "BUY", 1.0,     74005.0, confidence=0.80)

    approved, reason = rm.validate_order(order_ok)
    print(f"  Orden normal    -> {'APROBADA' if approved else 'BLOQUEADA'}: {reason}")

    approved, reason = rm.validate_order(order_low_conf)
    print(f"  Conf. baja      -> {'APROBADA' if approved else 'BLOQUEADA'}: {reason}")

    approved, reason = rm.validate_order(order_too_big)
    print(f"  Posicion grande -> {'APROBADA' if approved else 'BLOQUEADA'}: {reason}")

    qty = rm.calculate_quantity("BTCUSDT", 74005.0)
    sl  = rm.calculate_stop_loss("BUY", 74005.0)
    tp  = rm.calculate_take_profit("BUY", 74005.0)
    print(f"\n  Qty calculada: {qty} BTC (${qty*74005:.2f})")
    print(f"  Stop loss:     ${sl:,.2f}  (-2.5%)")
    print(f"  Take profit:   ${tp:,.2f}  (+4.0%)")
    print(f"  Health:        {rm.get_health()['status']}")


asyncio.run(main())
