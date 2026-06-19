DB=/opt/rael-vibe-trading/data/vibe_trading.db

echo "===== 1. DUMP DIRECCIONAL ====="
sqlite3 -header -column "$DB" "SELECT id, substr(ts,1,16) AS ts, vote, round(confidence,2) AS conf, executed AS exec, status, round(entry_price) AS entry, round(sl_price) AS sl, round(tp_price) AS tp, round(100.0*abs(entry_price-sl_price)/entry_price,2) AS sl_pct, round(100.0*abs(tp_price-entry_price)/entry_price,2) AS tp_pct, blocked_reason FROM shadow_signals WHERE vote IN ('BUY','SELL') ORDER BY id;"

echo ""
echo "===== 2. RESULTADO POR DIRECCION ====="
sqlite3 -header -column "$DB" "SELECT vote, status, COUNT(*) AS n, round(AVG(confidence),2) AS avg_conf FROM shadow_signals WHERE vote IN ('BUY','SELL') GROUP BY vote, status ORDER BY vote, status;"

echo ""
echo "===== 3. TP-FIRST RATE POR CONVICCION (resueltas) ====="
sqlite3 -header -column "$DB" "SELECT CASE WHEN confidence<0.60 THEN '<0.60' WHEN confidence<0.65 THEN '0.60-0.65' WHEN confidence<0.70 THEN '0.65-0.70' WHEN confidence<0.75 THEN '0.70-0.75' ELSE '0.75+' END AS bucket, COUNT(*) AS n, SUM(status='TP_FIRST') AS tp, SUM(status='SL_FIRST') AS sl, round(100.0*SUM(status='TP_FIRST')/COUNT(*),0) AS tp_rate FROM shadow_signals WHERE status IN ('TP_FIRST','SL_FIRST') GROUP BY bucket ORDER BY bucket;"

echo ""
echo "===== 4. EJECUTADAS vs BLOQUEADAS ====="
sqlite3 -header -column "$DB" "SELECT CASE WHEN executed=1 THEN 'EJECUTADA' ELSE 'BLOQUEADA' END AS tipo, COALESCE(blocked_reason,'(ejecutada)') AS motivo, COUNT(*) AS n, SUM(status='TP_FIRST') AS tp_first, SUM(status='SL_FIRST') AS sl_first, SUM(status='EXPIRED') AS expired, SUM(status='PENDING') AS pending FROM shadow_signals WHERE vote IN ('BUY','SELL') GROUP BY tipo, motivo ORDER BY tipo, n DESC;"
