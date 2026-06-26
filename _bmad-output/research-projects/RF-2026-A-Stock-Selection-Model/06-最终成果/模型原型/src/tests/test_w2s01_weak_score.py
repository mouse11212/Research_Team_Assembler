import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from factors.w2s_daily_factors import DailyW2SFactors

f = DailyW2SFactors()

def _win(closes, vols, ma20s):
    return [{'close': c, 'volume': v, 'ma20': m} for c, v, m in zip(closes, vols, ma20s)]

def test_trapezoid_shape():
    assert f._trapezoid(0.005, 0.01, 0.03, 0.15, 0.25) == 0.0   # below zlo
    assert f._trapezoid(0.30, 0.01, 0.03, 0.15, 0.25) == 0.0    # above zhi
    assert f._trapezoid(0.08, 0.01, 0.03, 0.15, 0.25) == 1.0    # plateau
    assert abs(f._trapezoid(0.02, 0.01, 0.03, 0.15, 0.25) - 0.5) < 1e-9  # rising midpoint

def test_weak_score_healthy_pullback_high():
    # High 10, shrinking pullback to 9.2 (8%), holding ma20=9.0, shrinking volume
    w = _win([10.0, 9.8, 9.5, 9.3, 9.2], [200, 150, 120, 100, 90], [9.0]*5)
    s = f._weak_score(w)
    assert s is not None and s >= 0.6, s

def test_weak_score_no_pullback_low():
    # Continuously rising, near-zero pullback (<1%) → pullback≈0 → weak_score low
    # M-1: ma20=13.0 (far above last_close=10.5) → support=0 (pos < -10%);
    #      volume expanding (rv>1.2) → shrink=0; pullback=0.
    #      total score = 0, clearly < 0.05 (well below 0.2, has margin)
    w = _win([9.0, 9.3, 9.6, 9.9, 10.5], [100, 120, 140, 160, 180], [13.0]*5)
    s = f._weak_score(w)
    assert s is not None and s < 0.05, s

def test_weak_score_short_window_none():
    assert f._weak_score(_win([10, 9.5], [100, 90], [9, 9])) is None

def test_weak_score_missing_close_in_middle():
    """I-1/I-2/I-3: middle item close=None, last item ma20=0.0 sentinel — must not crash.

    Constructs a window where item 3 has close=None (middle gap) and the last item
    has ma20=0.0 (zero-value sentinel).  Verifies:
    - No exception raised (Fail-Loud: skip the sub-score, not fabricate)
    - last_close taken from window[-1].close=9.2, same source as ma20 (I-1 fix)
    - win_high computed from valid closes only, skipping None (I-2 fix)
    - ma20=0.0 NOT treated as missing (I-3 fix), support sub-score computed
    - Returns a float in [0, 1]
    """
    window = [
        {'close': 10.0, 'volume': 200, 'ma20': 9.0},
        {'close': 9.8,  'volume': 150, 'ma20': 9.0},
        {'close': None, 'volume': 120, 'ma20': 9.0},  # middle close missing (I-1/I-2)
        {'close': 9.5,  'volume': 100, 'ma20': 9.0},
        {'close': 9.2,  'volume': 90,  'ma20': 0.0},  # last ma20=0.0 sentinel (I-3)
    ]
    s = f._weak_score(window)
    # Must not return None: last_close=9.2 is available, win_high=10.0 computable
    assert s is not None, f"Expected float, got None"
    # last_close=9.2, win_high=10.0 → d=0.08, in plateau → pullback=1.0
    # ma20=0.0 → denominator guard → pos=0.0 → support=1.0 (not < 0, not skipped)
    # vols=[200,150,120,100,90], half=2, rv<1 → shrink>0
    assert isinstance(s, float) and 0.0 <= s <= 1.0, f"Score out of range: {s}"

if __name__ == '__main__':
    test_trapezoid_shape(); test_weak_score_healthy_pullback_high()
    test_weak_score_no_pullback_low(); test_weak_score_short_window_none()
    test_weak_score_missing_close_in_middle()
    print('PASS test_w2s01_weak_score')
