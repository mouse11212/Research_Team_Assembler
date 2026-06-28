"""
动态阈值体系模块
Dynamic Threshold System Module

核心原则：替代固定阈值（85/75/60/40），使用历史分位数动态调整

实现功能：
1. 基于过去60日综合得分历史分布设定阈值
2. 适应市场环境变化
3. 信号分级：Strong Buy / Buy / Hold / Sell
"""

import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

# 生产错误走统一日志（不再 print 到 stdout）；path 兜底以支持 __main__ 独立运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logging_config import get_logger

logger = get_logger(__name__)


class DynamicThresholdSystem:
    """
    动态阈值系统

    基于历史分位数设定信号阈值，替代固定阈值
    - Strong Buy: Top 10%（90分位）
    - Buy: Top 25%（75分位）
    - Hold: Top 50%（50分位）
    - Sell: Bottom 25%（25分位）
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # 历史窗口（默认60日）
        self.history_window = self.config.get('history_window', 60)

        # 分位数配置
        self.quantile_config = self.config.get('quantile_config', {
            'strong_buy': 0.90,  # Top 10%
            'buy': 0.75,         # Top 25%
            'hold': 0.50,        # Top 50%
            'sell': 0.25         # Bottom 25%
        })

        # 信号类型
        self.signal_types = ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']

        # 市场环境调节系数
        self.market_adjustments = self.config.get('market_adjustments', {
            '情绪冰点': 1.2,     # 冰点时提高阈值（更苛刻）
            '情绪启动': 1.0,     # 启动时维持正常
            '情绪上升': 0.9,     # 上升时降低阈值（更宽松）
            '情绪高潮': 0.85,    # 高潮时大幅降低阈值（积极）
            '情绪过热': 1.1      # 过热时提高阈值（谨慎）
        })

    def calculate_dynamic_thresholds(self, score_history: pd.Series) -> Dict[str, float]:
        """
        基于历史分位数设定动态阈值

        Args:
            score_history: 过去N日的综合得分历史

        Returns:
            动态阈值字典
        """
        try:
            # 数据清洗
            clean_history = score_history.dropna()

            if len(clean_history) < 30:
                # 数据不足，使用默认阈值
                return self._get_default_thresholds()

            # 使用最近N日数据
            recent_history = clean_history.tail(self.history_window)

            # 计算分位数阈值
            thresholds = {}
            for signal_type, quantile in self.quantile_config.items():
                threshold_value = recent_history.quantile(quantile)
                thresholds[signal_type] = round(threshold_value, 2)

            # 添加极端阈值
            thresholds['strong_sell'] = round(recent_history.quantile(0.10), 2)  # Bottom 10%

            return thresholds

        except Exception as e:
            logger.warning(f"[错误] 动态阈值计算失败: {e}")
            return self._get_default_thresholds()

    def _get_default_thresholds(self) -> Dict[str, float]:
        """获取默认阈值（固定阈值）"""
        # 阈值校准(2026-06-28): W2S01/02/03 乘性化根治满分泛滥后,综合分基线整体下移
        # (旧版虚高 54-57 → 真实 ~30-45;0626 实测 max=53.5 / P90=46.8 / P75=43.7 / 中位=40.4)。
        # 原固定阈值为旧"虚高分"校准,致 daily 全部跌破 buy=60 → 0 推荐。
        # 按原设计分位数语义(strong_buy≈Top10%/buy≈Top25%)对新分布重校准。留后续动态阈值/调优。
        return {
            'strong_buy': 47,
            'buy': 44,
            'hold': 35,
            'sell': 25,
            'strong_sell': 15
        }

    def adjust_threshold_by_emotion(self, thresholds: Dict[str, float],
                                      emotion_phase: str) -> Dict[str, float]:
        """
        根据情绪阶段调节阈值

        Args:
            thresholds: 基础动态阈值
            emotion_phase: 情绪阶段

        Returns:
            调节后的阈值
        """
        try:
            adjustment_factor = self.market_adjustments.get(emotion_phase, 1.0)

            adjusted = {}
            for signal_type, threshold in thresholds.items():
                # 买入信号阈值向上调整（更苛刻）
                # 卖出信号阈值向下调整（更宽松）
                if signal_type in ['strong_buy', 'buy']:
                    adjusted[signal_type] = round(threshold * adjustment_factor, 2)
                elif signal_type in ['sell', 'strong_sell']:
                    # 卖出阈值反向调整
                    reverse_factor = 2.0 - adjustment_factor
                    adjusted[signal_type] = round(threshold * reverse_factor, 2)
                else:
                    adjusted[signal_type] = threshold

            return adjusted

        except Exception as e:
            logger.warning(f"[错误] 阈值调节失败: {e}")
            return thresholds

    def classify_signal(self, score: float, thresholds: Dict[str, float]) -> str:
        """
        根据评分和动态阈值分类信号

        Args:
            score: 综合评分
            thresholds: 动态阈值字典

        Returns:
            信号类型
        """
        try:
            if score >= thresholds.get('strong_buy', 80):
                return 'strong_buy'
            elif score >= thresholds.get('buy', 60):
                return 'buy'
            elif score >= thresholds.get('hold', 40):
                return 'hold'
            elif score >= thresholds.get('sell', 20):
                return 'sell'
            else:
                return 'strong_sell'

        except Exception as e:
            logger.warning(f"[错误] 信号分类失败: {e}")
            return 'hold'

    def get_position_suggestion(self, signal_type: str, emotion_phase: str) -> float:
        """
        根据信号类型和情绪阶段给出仓位建议

        Args:
            signal_type: 信号类型
            emotion_phase: 情绪阶段

        Returns:
            仓位建议（0-1）
        """
        # 基础仓位配置
        base_positions = {
            'strong_buy': 0.40,  # 强买入：40%仓位
            'buy': 0.30,         # 买入：30%仓位
            'hold': 0.00,        # 持有：不建仓
            'sell': 0.00,        # 卖出：清仓
            'strong_sell': 0.00  # 强卖出：立即清仓
        }

        # 情绪调节系数
        emotion_multipliers = {
            '情绪冰点': 0.5,     # 冰点：减半仓位
            '情绪启动': 0.8,     # 启动：八成仓位
            '情绪上升': 1.0,     # 上升：正常仓位
            '情绪高潮': 1.0,     # 高潮：正常仓位
            '情绪过热': 0.5      # 过热：减半仓位（防风险）
        }

        try:
            base_position = base_positions.get(signal_type, 0.0)
            emotion_mult = emotion_multipliers.get(emotion_phase, 1.0)

            # 单只股票仓位上限33%
            max_position = 0.33

            adjusted_position = min(base_position * emotion_mult, max_position)

            return round(adjusted_position, 2)

        except Exception as e:
            logger.warning(f"[错误] 仓位建议计算失败: {e}")
            return 0.0

    def calculate_threshold_stability(self, threshold_history: pd.DataFrame) -> Dict[str, float]:
        """
        计算阈值稳定性（阈值波动越小越稳定）

        Args:
            threshold_history: 阈值历史数据

        Returns:
            各阈值的稳定性指标
        """
        try:
            stability = {}

            for col in threshold_history.columns:
                # 稳定性 = 1 - (标准差 / 均值)
                mean_val = threshold_history[col].mean()
                std_val = threshold_history[col].std()

                if mean_val > 0:
                    stability[col] = round(1 - (std_val / mean_val), 4)
                else:
                    stability[col] = 0.0

            return stability

        except Exception as e:
            logger.warning(f"[错误] 阈值稳定性计算失败: {e}")
            return {}

    def update_thresholds_rolling(self, score_series: pd.Series) -> pd.DataFrame:
        """
        滚动更新阈值历史

        Args:
            score_series: 评分序列

        Returns:
            阈值历史DataFrame
        """
        try:
            threshold_history = pd.DataFrame()

            for i in range(self.history_window, len(score_series)):
                date = score_series.index[i]
                history_window = score_series.iloc[i-self.history_window:i]

                thresholds = self.calculate_dynamic_thresholds(history_window)

                # 记录当日阈值
                threshold_history.loc[date] = thresholds

            return threshold_history

        except Exception as e:
            logger.warning(f"[错误] 滚动阈值更新失败: {e}")
            return pd.DataFrame()

    def generate_threshold_report(self, thresholds: Dict[str, float],
                                    emotion_phase: str) -> str:
        """
        生成阈值分析报告

        Args:
            thresholds: 当前阈值
            emotion_phase: 情绪阶段

        Returns:
            报告文本
        """
        report = []
        report.append(f"\n{'='*50}")
        report.append("动态阈值体系报告")
        report.append(f"{'='*50}")

        report.append(f"\n当前情绪阶段: {emotion_phase}")

        report.append(f"\n动态阈值:")
        for signal_type, threshold in thresholds.items():
            report.append(f"  - {signal_type}: {threshold:.2f}")

        # 与固定阈值对比
        default = self._get_default_thresholds()
        report.append(f"\n与固定阈值对比:")
        for signal_type in thresholds.keys():
            diff = thresholds[signal_type] - default.get(signal_type, 0)
            report.append(f"  - {signal_type}: {thresholds[signal_type]:.2f} (固定{default.get(signal_type, 0)}, 差异{diff:.2f})")

        # 仓位建议示例
        report.append(f"\n仓位建议示例:")
        for signal_type in ['strong_buy', 'buy']:
            position = self.get_position_suggestion(signal_type, emotion_phase)
            report.append(f"  - {signal_type}: {position*100:.0f}%仓位")

        return "\n".join(report)


# ==================== 测试代码 ====================

def test_dynamic_thresholds():
    """测试动态阈值系统"""
    print("\n" + "="*70)
    print("动态阈值系统测试")
    print("="*70)

    system = DynamicThresholdSystem()

    # 模拟历史评分数据
    np.random.seed(42)
    n_days = 120
    dates = pd.date_range('2024-01-01', periods=n_days, freq='D')

    # 模拟评分：均值60，标准差15
    scores = pd.Series(
        np.random.normal(60, 15, n_days),
        index=dates
    )

    # 测试动态阈值计算
    print("\n【测试1】动态阈值计算")
    thresholds = system.calculate_dynamic_thresholds(scores)
    for k, v in thresholds.items():
        print(f"  {k}: {v}")

    # 测试情绪调节
    print("\n【测试2】情绪调节阈值")
    emotion_phases = ['情绪冰点', '情绪启动', '情绪上升', '情绪高潮', '情绪过热']
    for phase in emotion_phases:
        adjusted = system.adjust_threshold_by_emotion(thresholds, phase)
        print(f"  {phase}: strong_buy阈值={adjusted['strong_buy']:.2f}")

    # 测试信号分类
    print("\n【测试3】信号分类")
    test_scores = [85, 70, 55, 35, 15]
    for score in test_scores:
        signal = system.classify_signal(score, thresholds)
        print(f"  评分{score}: {signal}")

    # 测试仓位建议
    print("\n【测试4】仓位建议")
    for signal in ['strong_buy', 'buy']:
        for phase in ['情绪冰点', '情绪上升', '情绪高潮']:
            position = system.get_position_suggestion(signal, phase)
            print(f"  {signal} + {phase}: {position*100:.0f}%仓位")

    # 生成报告
    print("\n【测试5】阈值报告")
    report = system.generate_threshold_report(thresholds, '情绪上升')
    print(report)


if __name__ == '__main__':
    test_dynamic_thresholds()