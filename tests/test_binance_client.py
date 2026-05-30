import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from execution.binance_testnet import BinanceTestnetClient

client = BinanceTestnetClient()

print("=== Test BinanceTestnetClient — Fase 6 ===\n")

# 1. Portfolio
balance = client.get_portfolio_value()
print(f"Balance USDT:   ${balance:,.2f}")

# 2. Market data completo
print("\nMarket data BTCUSDT:")
data = client.get_market_data("BTCUSDT")
print(f"  Price:     ${data['price']:,.2f}")
print(f"  RSI(14):   {data['rsi']}")
print(f"  MACD:      {data['macd']}")
print(f"  BB upper:  ${data['bb_upper']:,.2f}")
print(f"  BB lower:  ${data['bb_lower']:,.2f}")
print(f"  EMA20:     ${data['ema20']:,.2f}")
print(f"  EMA50:     ${data['ema50']:,.2f}")
print(f"  Vol 24h:   {data['volume']:,.2f}")
print(f"  Closes[-3:]: {data['closes'][-3:]}")

# 3. Market data ETH
print("\nMarket data ETHUSDT:")
eth = client.get_market_data("ETHUSDT")
print(f"  Price:   ${eth['price']:,.2f}")
print(f"  RSI(14): {eth['rsi']}")
print(f"  MACD:    {eth['macd']}")

# 4. Scanner por volumen
universe = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","DOTUSDT","LINKUSDT"]
ranked = client.get_top_volume_pairs(universe)
print(f"\nAssets por volumen 24h:")
for i, s in enumerate(ranked, 1):
    print(f"  {i}. {s}")

# 5. Precision
from core.risk_manager import RiskManager
rm = RiskManager()
rm.update_balance(balance)
price = data["price"]
qty   = rm.calculate_quantity("BTCUSDT", price)
qty_adjusted = client._adjust_quantity("BTCUSDT", qty)
sl  = rm.calculate_stop_loss("BUY", price)
tp  = rm.calculate_take_profit("BUY", price)
sl_rounded = client._round_price("BTCUSDT", sl)
tp_rounded = client._round_price("BTCUSDT", tp)

print(f"\nSimulacion orden BUY BTCUSDT:")
print(f"  Qty raw:      {qty}")
print(f"  Qty adjusted: {qty_adjusted} BTC  (${qty_adjusted * price:,.2f})")
print(f"  Stop loss:    ${sl_rounded:,.2f}")
print(f"  Take profit:  ${tp_rounded:,.2f}")

print("\nStatus: FASE 6 OK")
