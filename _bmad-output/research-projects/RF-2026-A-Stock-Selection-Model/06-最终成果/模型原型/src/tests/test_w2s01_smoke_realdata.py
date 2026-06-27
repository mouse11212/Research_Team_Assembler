import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors
f = DailyW2SFactors(); L = f.lookback_L
c = sqlite3.connect('data/stock_history.db')
codes = [r[0] for r in c.execute(
    'SELECT DISTINCT stock_code FROM stock_kline WHERE trade_date="20260624" LIMIT 200')]
scored = []
for code in codes:
    rows = c.execute('SELECT close_price,volume,ma20,change_pct,ma5 FROM stock_kline '
                     'WHERE stock_code=? AND trade_date<="20260624" ORDER BY trade_date DESC '
                     'LIMIT ?', (code, L + 1)).fetchall()
    if len(rows) < L + 1:
        continue
    rows = rows[::-1]  # oldest->newest
    today = rows[-1]; window = [{'close': r[0], 'volume': r[1], 'ma20': r[2]} for r in rows[:-1]]
    td = {'change_pct': today[3], 'volume': today[1], 'close': today[0],
          'ma5': today[4], 'window_klines': window}
    scored.append(f.calculate_W2S01(td, {}))
nz = [s for s in scored if s > 0]
print(f'样本={len(scored)} 非零={len(nz)} 满分(100)={sum(1 for s in scored if s>=99)} '
      f'均值={sum(scored)/max(len(scored),1):.1f} max={max(scored) if scored else 0}')
assert len(scored) > 50, '样本过少'
assert sum(1 for s in scored if s >= 99) < len(scored) * 0.3, '满分泛滥未改善'
print('PASS smoke')
