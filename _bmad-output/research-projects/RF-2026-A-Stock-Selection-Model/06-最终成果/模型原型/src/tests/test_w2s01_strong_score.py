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

# --- Fail-Loud: is not None 判定缺失（不得 falsy 丢弃 0 值），与 _weak_score 同口径 ---

def test_zero_volume_today_keeps_quantity_dim():
    # 今量=0 是有效数据（停牌/无成交），量比维应保留并算出 vr=0→缩量分0，而非被剔除
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [100, 100, 100, 100, 100])
    today = {'change_pct': 5.0, 'volume': 0, 'close': 10.5, 'ma5': 9.6}
    s = f._strong_score(today, window)
    # 三维全保留: 涨幅0.5*0.4 + 量比0*0.3 + 突破1.0*0.3 = 0.5
    assert s is not None and abs(s - 0.5) < 1e-9, s

def test_zero_close_today_keeps_breakout_dim():
    # 今收=0 是有效数据，突破维应保留并算出 brk=0，而非被剔除
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [100, 100, 100, 100, 100])
    today = {'change_pct': 5.0, 'volume': 300, 'close': 0, 'ma5': 9.6}
    s = f._strong_score(today, window)
    # 涨幅0.5*0.4 + 量比1.0*0.3 + 突破0*0.3 = 0.5
    assert s is not None and abs(s - 0.5) < 1e-9, s

def test_zero_volume_window_drops_quantity_no_divzero():
    # 窗口均量为0时量比维剔除并重归一化（避免除零），整体仍可算
    window = _win([10.0, 9.8], [0, 0])
    today = {'change_pct': 5.0, 'volume': 300, 'close': 10.5, 'ma5': 9.6}
    s = f._strong_score(today, window)
    # 量比维剔除: (涨幅0.5*0.4 + 突破1.0*0.3)/(0.4+0.3)
    assert s is not None and abs(s - (0.5 * 0.4 + 1.0 * 0.3) / 0.7) < 1e-9, s

def test_zero_ma5_today_breakout_uses_window_high():
    # 今 ma5=0 是有效值；今收突破窗口高点时 brk 仍应为 1.0（窗口高点分支优先）
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [100, 100, 100, 100, 100])
    today = {'change_pct': 9.8, 'volume': 300, 'close': 10.5, 'ma5': 0}
    s = f._strong_score(today, window)
    assert s is not None and s >= 0.85, s

def test_missing_change_pct_returns_none():
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [100, 100, 100, 100, 100])
    today = {'volume': 300, 'close': 10.5, 'ma5': 9.6}  # 无 change_pct
    assert f._strong_score(today, window) is None

if __name__ == '__main__':
    test_strong_full_when_limit_up_breakout_volume(); test_strong_low_when_weak_move()
    test_zero_volume_today_keeps_quantity_dim(); test_zero_close_today_keeps_breakout_dim()
    test_zero_volume_window_drops_quantity_no_divzero(); test_zero_ma5_today_breakout_uses_window_high()
    test_missing_change_pct_returns_none()
    print('PASS test_w2s01_strong_score')
