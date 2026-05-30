import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from binance.client import Client
from binance.exceptions import BinanceAPIException

API_KEY    = os.getenv("BINANCE_TESTNET_API_KEY")
API_SECRET = os.getenv("BINANCE_TESTNET_SECRET")

print("=== Test Binance Testnet ===\n")

client = Client(API_KEY, API_SECRET, testnet=True)

# 1. Ping
client.ping()
print("Ping:       OK")

# 2. Server time
server_time = client.get_server_time()
print(f"Servidor:   {server_time['serverTime']}")

# 3. Balance
account = client.get_account()
balances = [b for b in account["balances"] if float(b["free"]) > 0 or float(b["locked"]) > 0]
print(f"\nBalance ({len(balances)} assets con fondos):")
for b in balances[:20]:  # top 20 para no saturar pantalla
    asset = b['asset'].encode('ascii', 'replace').decode('ascii')
    print(f"  {asset:8s}  libre: {float(b['free']):>14.4f}  bloqueado: {float(b['locked']):>10.4f}")

# 4. Precio BTC
btc_price = client.get_symbol_ticker(symbol="BTCUSDT")
print(f"\nBTCUSDT:    ${float(btc_price['price']):,.2f}")

# 5. Precio ETH
eth_price = client.get_symbol_ticker(symbol="ETHUSDT")
print(f"ETHUSDT:    ${float(eth_price['price']):,.2f}")

# 6. Klines (datos históricos — últimas 5 velas de 1h)
klines = client.get_klines(symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1HOUR, limit=5)
print(f"\nÚltimas 5 velas BTCUSDT 1h:")
for k in klines:
    print(f"  open={float(k[1]):>10.2f}  high={float(k[2]):>10.2f}  low={float(k[3]):>10.2f}  close={float(k[4]):>10.2f}  vol={float(k[5]):>12.4f}")

print("\nStatus: TESTNET OK")
