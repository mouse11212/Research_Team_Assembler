import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors

f = DailyW2SFactors()

def _win(vols):
    return [{'close': 10.0, 'volume': v, 'ma20': 9.0} for v in vols]

def test_volume_breakout_bald_yang_high():
    # 放量3倍、光头大阳(收在最高、实体大) → 高分
    today = {'open': 10.0, 'close': 10.9, 'high': 10.9, 'low': 10.0,
             'volume': 300, 'change_pct': 9.0, 'window_klines': _win([100]*5)}
    s = f.calculate_W2S02(today, {})
    assert s is not None and s >= 60, s

def test_volume_long_upper_shadow_low():
    # 放量3倍但收长上影(冲高回落,收在低位) → 价格不确认 → 低分
    today = {'open': 10.0, 'close': 10.1, 'high': 11.0, 'low': 10.0,
             'volume': 300, 'change_pct': 1.0, 'window_klines': _win([100]*5)}
    s = f.calculate_W2S02(today, {})
    assert s is not None and s <= 25, s

def test_volume_yin_near_zero():
    # 放量但收阴(实体为负、收在低位) → price_confirm≈0 → ≈0
    today = {'open': 10.5, 'close': 10.0, 'high': 10.6, 'low': 10.0,
             'volume': 300, 'change_pct': -2.0, 'window_klines': _win([100]*5)}
    s = f.calculate_W2S02(today, {})
    assert s is not None and s <= 10, s

def test_no_volume_shrink_low():
    # 缩量(今量<窗口均量) → vol_burst≈0 → 低分
    today = {'open': 10.0, 'close': 10.9, 'high': 10.9, 'low': 10.0,
             'volume': 80, 'change_pct': 9.0, 'window_klines': _win([100]*5)}
    s = f.calculate_W2S02(today, {})
    assert s is not None and s <= 10, s

def test_limit_up_one_word_no_divzero():
    # 一字涨停 high==low,closepos 守卫=1,不除零
    today = {'open': 11.0, 'close': 11.0, 'high': 11.0, 'low': 11.0,
             'volume': 300, 'change_pct': 10.0, 'window_klines': _win([100]*5)}
    s = f.calculate_W2S02(today, {})
    assert s is not None and s >= 30, s

def test_backward_compat_no_window():
    # 无 window_klines + 无 open → 回落旧逻辑(昨弱今强放量 base)
    today = {'change_pct': 6.0, 'volume': 300}
    yest = {'change_pct': 1.0, 'volume': 100}
    s = f.calculate_W2S02(today, yest)
    assert s is not None and s > 0

if __name__ == '__main__':
    test_volume_breakout_bald_yang_high(); test_volume_long_upper_shadow_low()
    test_volume_yin_near_zero(); test_no_volume_shrink_low()
    test_limit_up_one_word_no_divzero(); test_backward_compat_no_window()
    print('PASS test_w2s02_multiplicative')
