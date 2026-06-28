import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_fetcher_v3_integrated import IntegratedDataFetcher
import pandas as pd

f = IntegratedDataFetcher()

def test_gate_filters_pseudo_weak():
    # 0626 今日Top5:605366/600520/002668 为伪弱(W2S01<50),603977/002225 真弱转强(≥50)
    codes = ['605366', '600520', '002668', '603977', '002225']
    cand = pd.DataFrame({'stock_code': codes, 'change_pct': [10.0, 7.5, 7.0, 10.0, 6.9]})
    out = f._filter_by_w2s01_gate(cand, '20260626', gate=50)
    kept = set(out['stock_code'])
    assert '605366' not in kept and '600520' not in kept and '002668' not in kept, kept
    assert '603977' in kept and '002225' in kept, kept

def test_gate_window_insufficient_excluded():
    # 不存在的 code(无历史)→ 窗口不足 → 剔除
    cand = pd.DataFrame({'stock_code': ['ZZZNONE'], 'change_pct': [9.0]})
    out = f._filter_by_w2s01_gate(cand, '20260626', gate=50)
    assert len(out) == 0, out['stock_code'].tolist()

def test_empty_candidates_passthrough():
    out = f._filter_by_w2s01_gate(pd.DataFrame(), '20260626', gate=50)
    assert out is None or len(out) == 0

if __name__ == '__main__':
    test_gate_filters_pseudo_weak()
    test_gate_window_insufficient_excluded()
    test_empty_candidates_passthrough()
    print('PASS test_w2s01_gate')
