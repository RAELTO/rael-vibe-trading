#!/usr/bin/env python3
"""
Backfill P0.1 — limpieza de contaminación del loop de aprendizaje.

Detecta trades CERRADOS con un cierre INCOHERENTE (el `exit_reason` contradice el signo del
PnL o la dirección entry→exit) y purga las lecciones (`trade_lessons`) derivadas de ellos, que
de otro modo se reinyectan en el prompt del decisor en cada ciclo.

Usa exactamente la misma regla que `TradingOrchestrator._close_is_coherent` en producción.

Uso (en el VPS, dentro de /opt/rael-vibe-trading):
    python scripts/backfill_close_coherence.py                 # dry-run: solo reporta
    python scripts/backfill_close_coherence.py --apply         # borra las lecciones contaminadas
    python scripts/backfill_close_coherence.py --db data/vibe_trading.db --apply
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def close_is_coherent(side, entry_price, exit_price, exit_reason, pnl, tol=0.001) -> bool:
    """Espejo de TradingOrchestrator._close_is_coherent (mantener en sync)."""
    if exit_reason not in ("TP", "SL", "LIQUIDATED") or pnl is None:
        return True
    if exit_reason == "TP" and pnl < 0:
        return False
    if exit_reason in ("SL", "LIQUIDATED") and pnl > 0:
        return False
    if entry_price and exit_price:
        is_long = side in ("BUY", "LONG")
        band = entry_price * tol
        if exit_reason == "TP":
            if is_long and exit_price < entry_price - band:
                return False
            if not is_long and exit_price > entry_price + band:
                return False
        else:  # SL / LIQUIDATED
            if is_long and exit_price > entry_price + band:
                return False
            if not is_long and exit_price < entry_price - band:
                return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Purga lecciones derivadas de cierres incoherentes.")
    ap.add_argument("--db", default="data/vibe_trading.db", help="ruta a la DB SQLite")
    ap.add_argument("--apply", action="store_true", help="aplica los borrados (sin esto, dry-run)")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: DB no encontrada en {db}")
        sys.exit(1)

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row

    trades = con.execute(
        "SELECT id, side, entry_price, exit_price, exit_reason, pnl "
        "FROM trades WHERE status = 'CLOSED'"
    ).fetchall()

    bad = [
        t for t in trades
        if not close_is_coherent(t["side"], t["entry_price"], t["exit_price"], t["exit_reason"], t["pnl"])
    ]
    print(f"Trades cerrados: {len(trades)} | incoherentes: {len(bad)}")
    if not bad:
        print("Nada que limpiar.")
        return

    bad_ids = [t["id"] for t in bad]
    for t in bad:
        print(
            f"  trade #{t['id']:>4} {t['side']:<5} entry={t['entry_price']} "
            f"exit={t['exit_price']} reason={t['exit_reason']} pnl={t['pnl']}"
        )

    placeholders = ",".join("?" * len(bad_ids))
    lessons = con.execute(
        f"SELECT id, trade_id, lesson FROM trade_lessons WHERE trade_id IN ({placeholders})",
        bad_ids,
    ).fetchall()
    print(f"\nLecciones derivadas de esos trades: {len(lessons)}")
    for l in lessons:
        print(f"  lesson #{l['id']} (trade #{l['trade_id']}): {(l['lesson'] or '')[:90]}")

    if args.apply and lessons:
        con.execute(f"DELETE FROM trade_lessons WHERE trade_id IN ({placeholders})", bad_ids)
        con.commit()
        print(f"\n✓ Borradas {len(lessons)} lecciones contaminadas.")
    elif lessons:
        print("\n(dry-run) Re-ejecuta con --apply para borrar las lecciones listadas.")
    else:
        print("\nNo hay lecciones asociadas — nada que borrar.")


if __name__ == "__main__":
    main()
