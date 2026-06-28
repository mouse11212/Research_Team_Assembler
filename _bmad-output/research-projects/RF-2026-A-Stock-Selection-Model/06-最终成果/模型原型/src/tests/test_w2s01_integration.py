import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors
f = DailyW2SFactors()

def _win(closes, vols):
    return [{'close': c, 'volume': v, 'ma20': 9.0} for c, v in zip(closes, vols)]

def test_high_level_stagnation_scored_near_zero():
    # 致命点修复：持续走高无回调(高位滞涨)，今日反抽——weak≈0→W2S01≈0
    window = _win([9.0, 9.3, 9.6, 9.9, 10.0], [100, 120, 140, 160, 180])
    today = {'change_pct': 6.0, 'volume': 300, 'close': 10.6, 'ma5': 10.0,
             'window_klines': window}
    assert f.calculate_W2S01(today, {}) <= 15, f.calculate_W2S01(today, {})

def test_healthy_pullback_then_strong_high_score():
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [200, 150, 120, 100, 90])
    today = {'change_pct': 9.8, 'volume': 270, 'close': 10.5, 'ma5': 9.6,
             'window_klines': window}
    assert f.calculate_W2S01(today, {}) >= 55, f.calculate_W2S01(today, {})

def test_continuity_no_cliff():
    # 涨幅5.9→6.1微变，分数应平滑(差<5)，不再有2%/3%悬崖
    window = _win([10.0, 9.8, 9.5, 9.3, 9.2], [200, 150, 120, 100, 90])
    base = dict(volume=270, close=10.5, ma5=9.6, window_klines=window)
    s1 = f.calculate_W2S01({**base, 'change_pct': 5.9}, {})
    s2 = f.calculate_W2S01({**base, 'change_pct': 6.1}, {})
    assert abs(s1 - s2) < 5, (s1, s2)

def test_backward_compat_when_no_window():
    # 无 window_klines → 回落旧两日逻辑(昨弱今强 base 50)
    today = {'change_pct': 6.0, 'volume': 200, 'above_ma5': True}
    yest = {'change_pct': 1.0, 'volume': 100, 'above_ma5': False}
    assert f.calculate_W2S01(today, yest) >= 50

def test_window_present_but_uncomputable_returns_none():
    # IMPORTANT-1(final review)：有效窗口但子分不可算(close全None→_weak_score返None)→
    # Fail-Loud返None(非0.0),对齐W2S02/03,由signal_generator剔除重归一化,不拉低最大权重因子。
    window = [{'close': None, 'volume': 100, 'ma20': 9.0} for _ in range(5)]
    today = {'change_pct': 9.0, 'volume': 300, 'close': 10.5, 'ma5': 9.6, 'window_klines': window}
    assert f.calculate_W2S01(today, {}) is None, f.calculate_W2S01(today, {})

if __name__ == '__main__':
    test_high_level_stagnation_scored_near_zero()
    test_healthy_pullback_then_strong_high_score()
    test_continuity_no_cliff(); test_backward_compat_when_no_window()
    test_window_present_but_uncomputable_returns_none()
    print('PASS test_w2s01_integration')
