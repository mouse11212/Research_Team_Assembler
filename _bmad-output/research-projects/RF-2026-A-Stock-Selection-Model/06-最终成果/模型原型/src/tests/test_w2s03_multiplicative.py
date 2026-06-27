import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors

f = DailyW2SFactors()

def test_perfect_bull_high():
    # 完美多头发散 ma5>ma10>ma20 间距充分 + 收盘站稳三线上方
    today = {'close': 10.5, 'ma5': 10.2, 'ma10': 9.9, 'ma20': 9.6, 'change_pct': 5.0}
    s = f.calculate_W2S03(today, {})
    assert s is not None and s >= 60, s

def test_bear_alignment_near_zero():
    # 空头排列 ma5<ma10<ma20 + 收盘跌破 → ≈0
    today = {'close': 9.0, 'ma5': 9.3, 'ma10': 9.6, 'ma20': 9.9, 'change_pct': -3.0}
    s = f.calculate_W2S03(today, {})
    assert s is not None and s <= 10, s

def test_entangled_mid():
    # 均线纠缠（间距≈0）、收盘刚好贴线 → 中间分（不满不空）
    today = {'close': 10.0, 'ma5': 10.0, 'ma10': 9.99, 'ma20': 9.98, 'change_pct': 1.0}
    s = f.calculate_W2S03(today, {})
    assert s is not None and 0 < s < 40, s

def test_continuity_no_cliff():
    # close 微变,分数平滑（无二值悬崖）
    base = {'ma5': 10.2, 'ma10': 9.9, 'ma20': 9.6, 'change_pct': 5.0}
    s1 = f.calculate_W2S03({**base, 'close': 10.49}, {})
    s2 = f.calculate_W2S03({**base, 'close': 10.51}, {})
    assert abs(s1 - s2) < 5, (s1, s2)

def test_backward_compat_no_ma_values():
    # 无 ma 数值、有 above_maX 二值 → 回落旧逻辑
    today = {'above_ma5': True, 'above_ma10': True, 'above_ma20': False, 'change_pct': 5.0}
    yest = {'above_ma5': False, 'above_ma10': False, 'above_ma20': False}
    s = f.calculate_W2S03(today, yest)
    assert s is not None and s > 0

if __name__ == '__main__':
    test_perfect_bull_high(); test_bear_alignment_near_zero()
    test_entangled_mid(); test_continuity_no_cliff(); test_backward_compat_no_ma_values()
    print('PASS test_w2s03_multiplicative')
