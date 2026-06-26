import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors
f = DailyW2SFactors()

def _win(closes, vols):
    return [{'close': c, 'volume': v, 'ma20': 9.0} for c, v in zip(closes, vols)]

def test_strong_full_when_limit_up_breakout_volume():
    # 今日涨停9.8%、放量3倍、突破窗口高点10.0
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [100, 100, 100, 100, 100])
    today = {'change_pct': 9.8, 'volume': 300, 'close': 10.5, 'ma5': 9.6}
    s = f._strong_score(today, window)
    assert s is not None and s >= 0.85, s

def test_strong_low_when_weak_move():
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [100, 100, 100, 100, 100])
    today = {'change_pct': 1.0, 'volume': 90, 'close': 9.25, 'ma5': 9.6}  # 涨1%、缩量、未突破
    s = f._strong_score(today, window)
    assert s is not None and s <= 0.25, s

if __name__ == '__main__':
    test_strong_full_when_limit_up_breakout_volume(); test_strong_low_when_weak_move()
    print('PASS test_w2s01_strong_score')
