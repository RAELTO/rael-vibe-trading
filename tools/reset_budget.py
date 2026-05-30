"""
Reset the operational trading budget without deleting trade history.

This inserts a row in budget_resets, so StateStore.get_total_pnl() starts
counting closed-trade PnL from this moment forward.

Usage:
    python tools/reset_budget.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv

from core.state_store import StateStore


def main():
    load_dotenv(os.path.join(ROOT, ".env"))
    balance = float(os.getenv("DEMO_BUDGET_USDT", "5000.0"))
    store = StateStore()
    before = store.get_total_pnl()
    store.reset_trading_budget(current_balance=balance, prev_balance=None)
    after = store.get_total_pnl()
    print(f"Budget reset inserted. Previous operational PnL: {before:+.4f} USDT")
    print(f"New operational PnL: {after:+.4f} USDT")


if __name__ == "__main__":
    main()
