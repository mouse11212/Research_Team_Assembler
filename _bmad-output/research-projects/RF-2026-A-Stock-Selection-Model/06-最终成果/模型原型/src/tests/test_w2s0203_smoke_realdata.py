import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors
f = DailyW2SFactors(); L = f.lookback_L
c = sqlite3.connect('data/stock_history.db')
codes = [r[0] for r in c.execute(
    'SELECT DISTINCT stock_code FROM stock_kline WHERE trade_date="20260626" LIMIT 200')]
s02, s03 = [], []
for code in codes:
    rows = c.execute('SELECT close_price,volume,ma20,change_pct,ma5,ma10,open_price,high_price,low_price '
                     'FROM stock_kline WHERE stock_code=? AND trade_date<="20260626" '
                     'ORDER BY trade_date DESC LIMIT ?', (code, L + 1)).fetchall()
    if len(rows) < L + 1:
        continue
    rows = rows[::-1]  # oldest->newest
    today = rows[-1]; window = [{'close': r[0], 'volume': r[1], 'ma20': r[2]} for r in rows[:-1]]
    td = {'close': today[0], 'volume': today[1], 'change_pct': today[3],
          'ma5': today[4], 'ma10': today[5], 'open': today[6], 'high': today[7], 'low': today[8],
          'ma20': today[2], 'window_klines': window}
    v02 = f.calculate_W2S02(td, {}); v03 = f.calculate_W2S03(td, {})
    if v02 is not None: s02.append(v02)
    if v03 is not None: s03.append(v03)
def report(name, xs):
    full = sum(1 for s in xs if s >= 99)
    print(f'{name}: 样本={len(xs)} 满分={full} 均值={sum(xs)/max(len(xs),1):.1f} max={max(xs) if xs else 0:.1f}')
    assert len(xs) > 50, f'{name} 样本过少'
    assert full < len(xs) * 0.3, f'{name} 满分泛滥未改善'
report('W2S02', s02); report('W2S03', s03)
print('PASS smoke_w2s0203')
