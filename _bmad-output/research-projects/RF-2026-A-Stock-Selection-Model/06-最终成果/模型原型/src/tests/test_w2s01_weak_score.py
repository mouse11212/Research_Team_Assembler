import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors

f = DailyW2SFactors()

def _win(closes, vols, ma20s):
    return [{'close': c, 'volume': v, 'ma20': m} for c, v, m in zip(closes, vols, ma20s)]

def test_trapezoid_shape():
    assert f._trapezoid(0.005, 0.01, 0.03, 0.15, 0.25) == 0.0   # 低于zlo
    assert f._trapezoid(0.30, 0.01, 0.03, 0.15, 0.25) == 0.0    # 高于zhi
    assert f._trapezoid(0.08, 0.01, 0.03, 0.15, 0.25) == 1.0    # 平台区
    assert abs(f._trapezoid(0.02, 0.01, 0.03, 0.15, 0.25) - 0.5) < 1e-9  # 上升沿中点

def test_weak_score_healthy_pullback_high():
    # 高点10、缩量回调到9.2(回撤8%)、守ma20(=9.0)、近段缩量
    w = _win([10.0, 9.8, 9.5, 9.3, 9.2], [200, 150, 120, 100, 90], [9.0]*5)
    s = f._weak_score(w)
    assert s is not None and s >= 0.6, s

def test_weak_score_no_pullback_low():
    # 持续走高、几乎无回撤(回撤<1%) → pullback≈0 → weak_score低
    w = _win([9.0, 9.3, 9.6, 9.9, 10.0], [100, 120, 140, 160, 180], [9.0]*5)
    s = f._weak_score(w)
    assert s is not None and s <= 0.2, s

def test_weak_score_short_window_none():
    assert f._weak_score(_win([10, 9.5], [100, 90], [9, 9])) is None

if __name__ == '__main__':
    test_trapezoid_shape(); test_weak_score_healthy_pullback_high()
    test_weak_score_no_pullback_low(); test_weak_score_short_window_none()
    print('PASS test_w2s01_weak_score')
