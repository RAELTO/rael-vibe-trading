import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.deepseek_agent import DeepSeekAgent
from core.decider import Decider
from agents.base_agent import TradingSignal, AgentVote

# 4 agentes simulados votando
signals = [
    TradingSignal("BTCUSDT", AgentVote.SELL, 0.82, "RSI=71 overbought + MACD bearish", "claude-sonnet"),
    TradingSignal("BTCUSDT", AgentVote.SELL, 0.75, "EMA20 below EMA50, descending channel", "qwen-api"),
    TradingSignal("BTCUSDT", AgentVote.HOLD, 0.55, "volume too low to confirm", "gpt-5.4-nano"),
    TradingSignal("BTCUSDT", AgentVote.SELL, 0.78, "BB upper touch + negative momentum", "deepseek-v3"),
]

news = {
    "market_impact": "MEDIUM",
    "overall_sentiment": -0.3,
    "recommended_action_bias": "SELL",
    "key_events": ["Fed hawkish tone", "BTC ETF outflow"],
}

d = Decider()
result = d.decide(signals, news_context=news)

print("=== Test Decider — 4 agentes ===\n")
print(f"DeepSeekAgent importado: OK")
print(f"Decisión final:  {result['decision']}")
print(f"Score ajustado:  {result['consensus_score']} (raw: {result['raw_score']})")
print(f"News multiplier: {result['news_multiplier']}")
print(f"Consenso:        {'SI' if result['reached_consensus'] else 'NO'}")
print(f"Votos:           {result['votes']}")
print(f"Agentes:         {result['agents_voted']}")
print(f"\nRazonamiento:")
for r in result["reasoning"]:
    print(f"  {r}")
