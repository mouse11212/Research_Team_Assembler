"""
日线弱转强因子模块 (W2S类)
Weak-to-Strong Factors - Daily Line Based

核心原则：以日线弱转强为核心信号，分时数据仅作辅助

基于文档规范重构：
- W2S01: 日线弱转强（核心）
- W2S02: 量价日线弱转强
- W2S03: 技术日线弱转强
- W2S04: 资金日线弱转强
- W2S05: 消息弱转强
- W2S06: 板块日线弱转强
"""

import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

# 生产错误走统一日志（不再 print 到 stdout）；path 兜底以支持本文件 __main__ 独立运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logging_config import get_logger

logger = get_logger(__name__)


class DailyW2SFactors:
    """
    日线弱转强因子计算器

    核心逻辑：昨日弱势 + 今日强势 + 量价配合 = 弱转强

    弱势定义：
    - 昨日涨幅 < 2%
    - 或昨日收阴
    - 或昨日未突破关键均线

    强势定义：
    - 今日涨幅 > 3%
    - 或今日突破关键均线
    - 或今日涨停
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # 弱势阈值
        self.weak_threshold = self.config.get('weak_threshold', 2.0)  # 昨日涨幅<2%为弱势
        # 强势阈值
        self.strong_threshold = self.config.get('strong_threshold', 3.0)  # 今日涨幅>3%为强势
        # 涨停阈值
        self.limit_up_threshold = self.config.get('limit_up_threshold', 9.5)
        # 放量阈值
        self.volume_ratio_threshold = self.config.get('volume_ratio_threshold', 1.5)

        # 改进版 W2S01 参数（计划1）
        self.lookback_L = int(self.config.get('w2s_lookback_L', 5))
        self.pullback_zlo = self.config.get('w2s_pullback_zlo', 0.01)
        self.pullback_lo = self.config.get('w2s_pullback_lo', 0.03)
        self.pullback_hi = self.config.get('w2s_pullback_hi', 0.15)
        self.pullback_zhi = self.config.get('w2s_pullback_zhi', 0.25)
        self.weak_w = self.config.get('weak_weights', (0.5, 0.3, 0.2))  # 回调/缩量/支撑

        # 强势参数
        self.strong_w = self.config.get('strong_weights', (0.4, 0.3, 0.3))  # 涨幅/量比/突破
        self.chg_full = self.config.get('w2s_chg_full', 10.0)   # 涨幅满分点(%)
        self.vr_span = self.config.get('w2s_vr_span', 2.0)      # 量比从1→满分的跨度

        # W2S02 量价配合参数(本计划)
        self.w2s02_vr_span = self.config.get('w2s02_vr_span', 1.5)      # 量比满分跨度(vr=2.5封顶)
        self.w2s02_body_span = self.config.get('w2s02_body_span', 0.05)  # 实体多头度满分跨度
        self.w2s02_pc_w = self.config.get('w2s02_pc_weights', (0.5, 0.5))  # (实体, 收盘强势)

        # W2S03 均线趋势参数(本计划)
        self.w2s03_align_span = self.config.get('w2s03_align_span', 0.02)  # 均线间距满分跨度
        self.w2s03_pos_span = self.config.get('w2s03_pos_span', 0.03)      # 站位满分跨度
        self.w2s03_pos_w = self.config.get('w2s03_pos_weights', (0.5, 0.3, 0.2))  # (ma5,ma10,ma20)

    @staticmethod
    def _trapezoid(x, zlo, lo, hi, zhi):
        if x <= zlo or x >= zhi:
            return 0.0
        if x < lo:
            return (x - zlo) / (lo - zlo)
        if x <= hi:
            return 1.0
        return (zhi - x) / (zhi - hi)

    def _weak_score(self, window):
        """过去L日健康回调分[0,1]；窗口不足L日返None。Fail-Loud:子项缺失则同侧重归一化。"""
        if not window or len(window) < self.lookback_L:
            return None
        # I-2: 用 is not None 避免 close=0.0 被当缺失丢弃（与 volume 口径一致）
        closes = [w.get('close') for w in window if w.get('close') is not None]
        vols = [w.get('volume') for w in window if w.get('volume') is not None]
        if not closes:
            return None
        win_high = max(closes)
        # I-1: last_close 直接取自真正末日 window[-1]，与 last_ma20 同源；
        #       win_high 仍由有效 closes 求 max（健康回调区间）
        last_close = window[-1].get('close')
        parts, weights = [], []
        # ① 回调充分度：last_close 为 None 则该子项按缺失跳过（Fail-Loud）
        if last_close is not None:
            d = (win_high - last_close) / win_high if win_high > 0 else 0.0
            parts.append(self._trapezoid(d, self.pullback_zlo, self.pullback_lo,
                                         self.pullback_hi, self.pullback_zhi))
            weights.append(self.weak_w[0])
        # ② 缩量度：近半段均量/前半段均量，rv≤0.6→1, rv≥1.2→0
        if len(vols) >= 2:
            half = len(vols) // 2
            base_v = sum(vols[:half]) / max(half, 1)
            recent_v = sum(vols[half:]) / max(len(vols) - half, 1)
            rv = recent_v / base_v if base_v > 0 else 1.0
            shrink = max(0.0, min(1.0, (1.2 - rv) / 0.6))
            parts.append(shrink); weights.append(self.weak_w[1])
        # ③ 支撑度：末日收盘 vs ma20，>=ma20→1，低10%→0
        #    I-3: 用 is not None 避免 ma20=0.0 被误判为缺失
        last_ma20 = window[-1].get('ma20')
        if last_ma20 is not None and last_close is not None:
            pos = (last_close - last_ma20) / last_ma20 if last_ma20 != 0 else 0.0
            support = max(0.0, min(1.0, 1.0 + pos / 0.10)) if pos < 0 else 1.0
            parts.append(support); weights.append(self.weak_w[2])
        wsum = sum(weights)
        return sum(p * w for p, w in zip(parts, weights)) / wsum if wsum > 0 else 0.0

    def _strong_score(self, today, window):
        """今日放量转强分[0,1]。"""
        pct = today.get('change_pct')
        if pct is None:
            return None
        parts, weights = [], []
        # ① 涨幅力度：0→0, chg_full→1
        parts.append(max(0.0, min(1.0, pct / self.chg_full)))
        weights.append(self.strong_w[0])
        # ② 量比：今量/窗口均量；1→0, (1+vr_span)→1
        #    用 is not None 避免 volume=0.0 被当缺失丢弃（与 _weak_score 口径一致）；
        #    avg_v>0 兜底避免全 0 量基准导致除零
        vols = [w.get('volume') for w in (window or []) if w.get('volume') is not None]
        tv = today.get('volume')
        if vols and tv is not None:
            avg_v = sum(vols) / len(vols)
            if avg_v > 0:
                vr = tv / avg_v
                parts.append(max(0.0, min(1.0, (vr - 1.0) / self.vr_span)))
                weights.append(self.strong_w[1])
        # ③ 突破：今收>窗口高点→1；否则今收>ma5→0.5；否则0
        #    用 is not None 避免 close=0.0/ma5=0.0 被当缺失丢弃
        closes = [w.get('close') for w in (window or []) if w.get('close') is not None]
        tc, tma5 = today.get('close'), today.get('ma5')
        if closes and tc is not None:
            if tc > max(closes):
                brk = 1.0
            elif tma5 is not None and tc > tma5:
                brk = 0.5
            else:
                brk = 0.0
            parts.append(brk); weights.append(self.strong_w[2])
        wsum = sum(weights)
        return sum(p * w for p, w in zip(parts, weights)) / wsum if wsum > 0 else None

    def _vol_burst(self, today, window):
        """量能爆发门控[0,1]:今量/窗口均量,clamp((vr-1)/vr_span,0,1)。不可算返None。"""
        tv = today.get('volume')
        vols = [w.get('volume') for w in (window or []) if w.get('volume') is not None]
        if tv is None or not vols:
            return None
        avg_v = sum(vols) / len(vols)
        if avg_v <= 0:
            return None
        vr = tv / avg_v
        return max(0.0, min(1.0, (vr - 1.0) / self.w2s02_vr_span))

    def _price_confirm(self, today):
        """价格确认度[0,1]:实体多头度 + 收盘强势度加权。关键字段缺失返None。"""
        o = today.get('open'); c = today.get('close')
        h = today.get('high'); l = today.get('low')
        if o is None or c is None or h is None or l is None:
            return None
        parts, weights = [], []
        # ① 实体多头度:收阳实体越大越高,收阴→0
        if o > 0:
            body = max(0.0, min(1.0, (c - o) / o / self.w2s02_body_span))
            parts.append(body); weights.append(self.w2s02_pc_w[0])
        # ② 收盘强势度:(close-low)/(high-low);一字板 high==low 守卫=1
        closepos = 1.0 if h <= l else max(0.0, min(1.0, (c - l) / (h - l)))
        parts.append(closepos); weights.append(self.w2s02_pc_w[1])
        wsum = sum(weights)
        return sum(p * w for p, w in zip(parts, weights)) / wsum if wsum > 0 else None

    def _trend_align(self, ma5, ma10, ma20):
        """多头排列度[0,1]:相邻均线间距连续打分。均线全缺返None。"""
        S = self.w2s03_align_span
        parts = []
        if ma5 is not None and ma10 is not None and ma10 > 0:
            parts.append(max(0.0, min(1.0, (ma5 - ma10) / ma10 / S)))
        if ma10 is not None and ma20 is not None and ma20 > 0:
            parts.append(max(0.0, min(1.0, (ma10 - ma20) / ma20 / S)))
        if not parts:
            return None
        return sum(parts) / len(parts)

    def _ma_position(self, close, ma5, ma10, ma20):
        """站位度[0,1]:close相对各均线距离加权。close缺或均线全缺返None。"""
        if close is None:
            return None
        P = self.w2s03_pos_span
        parts, weights = [], []
        for ma, wi in zip((ma5, ma10, ma20), self.w2s03_pos_w):
            if ma is not None and ma > 0:
                parts.append(max(0.0, min(1.0, (close - ma) / ma / P)))
                weights.append(wi)
        wsum = sum(weights)
        return sum(p * w for p, w in zip(parts, weights)) / wsum if wsum > 0 else None

    def calculate_W2S01(self, today_data: Dict, yesterday_data: Dict) -> float:
        """
        W2S01: 日线弱转强（核心因子）

        计算逻辑：
        - 昨日涨幅 < 2%（弱势）
        - 今日涨幅 > 3%（强势）
        - 量价配合加分

        Args:
            today_data: 今日日线数据
                - change_pct: 今日涨幅
                - volume: 今日成交量
                - above_ma5: 是否突破5日线
                - above_ma10: 是否突破10日线
            yesterday_data: 昨日日线数据
                - change_pct: 昨日涨幅
                - volume: 昨日成交量
                - above_ma5: 昨日是否在5日线之上
                - above_ma10: 昨日是否在10日线之上

        Returns:
            弱转强评分 (0-100)
        """
        try:
            # 改进版：有有效多日窗口 → 连续乘性打分
            window = today_data.get('window_klines')
            if window and len(window) >= self.lookback_L:
                weak = self._weak_score(window)
                strong = self._strong_score(today_data, window)
                if weak is None or strong is None:
                    return 0.0   # 整侧不可算 → Fail-Loud 0
                return round(100.0 * weak * strong, 2)
            # 否则回落原两日逻辑（向后兼容）↓↓↓（保留下方原有代码不动）

            score = 0

            # 弱转强判断（昨日弱势 → 今日强势）
            yesterday_pct = yesterday_data.get('change_pct', 0)
            today_pct = today_data.get('change_pct', 0)

            was_weak = yesterday_pct < self.weak_threshold
            is_strong = today_pct > self.strong_threshold

            if was_weak and is_strong:
                base_score = 50  # 基础弱转强得分

                # 量价配合加分
                yesterday_vol = yesterday_data.get('volume', 0)
                today_vol = today_data.get('volume', 0)
                if yesterday_vol > 0:
                    volume_ratio = today_vol / yesterday_vol
                    if volume_ratio > self.volume_ratio_threshold:
                        base_score += 20  # 放量加分

                # 技术突破加分
                yesterday_ma5 = yesterday_data.get('above_ma5', False)
                today_ma5 = today_data.get('above_ma5', False)
                if not yesterday_ma5 and today_ma5:
                    base_score += 10  # 突破5日线加分

                yesterday_ma10 = yesterday_data.get('above_ma10', False)
                today_ma10 = today_data.get('above_ma10', False)
                if not yesterday_ma10 and today_ma10:
                    base_score += 10  # 突破10日线加分

                # 涨停加分
                if today_pct >= self.limit_up_threshold:
                    base_score += 10  # 涨停加分

                score = min(base_score, 100)

            return round(score, 2)

        except Exception as e:
            logger.warning(f"[错误] W2S01计算失败: {e}")
            return 0.0

    def calculate_W2S02(self, today_data: Dict, yesterday_data: Dict) -> float:
        """
        W2S02: 量价日线弱转强

        计算逻辑（2026-06-15 修：补昨弱前置门槛，名实相符）：
        - 昨日涨幅 < weak_threshold（弱势）—— 与 W2S01/W2S03 对齐的"弱转强"语义
        - 今日成交量 > 昨日成交量 * 1.5（放量）
        - 今日涨幅 > 3%
        - 连续评分（放量越大，得分越高）

        ⚠️ 修复背景：原实现仅校验"今放量大涨"而无"昨弱"，对任何放量大涨股普遍满分90-100，
        导致候选池 W2S 满分泛滥、无区分度（持续强势股被误当弱转强）。补昨弱门槛后，
        昨日已强、今日续强的票 W2S02 归 0，候选池恢复区分度。

        Args:
            today_data: 今日日线数据
            yesterday_data: 昨日日线数据

        Returns:
            量价弱转强评分 (0-100)
        """
        try:
            # 改进版:有量价字段 + 有效窗口 → 连续乘性打分(量价配合)
            window = today_data.get('window_klines')
            if window and len(window) >= self.lookback_L and today_data.get('open') is not None:
                vb = self._vol_burst(today_data, window)
                pc = self._price_confirm(today_data)
                if vb is None or pc is None:
                    return None   # 整侧不可算 → Fail-Loud None
                return round(100.0 * vb * pc, 2)
            # 否则回落原两日逻辑(向后兼容)↓↓↓(保留下方原有代码不动)

            score = 0

            today_pct = today_data.get('change_pct', 0)
            yesterday_pct = yesterday_data.get('change_pct', 0)
            yesterday_vol = yesterday_data.get('volume', 0)
            today_vol = today_data.get('volume', 0)

            # 昨弱今强：与 W2S01 一致，杜绝"持续强势"被误判为弱转强
            was_weak = yesterday_pct < self.weak_threshold

            if was_weak and yesterday_vol > 0 and today_pct > self.strong_threshold:
                volume_ratio = today_vol / yesterday_vol

                if volume_ratio > self.volume_ratio_threshold:
                    # 放量倍数映射到评分
                    # 1.5倍 = 60分, 2倍 = 80分, 3倍+ = 100分
                    ratio_score = min((volume_ratio - 1.0) * 40, 50)

                    # 涨幅映射到评分
                    # 3% = 30分, 5% = 40分, 涨停 = 50分
                    pct_score = min(today_pct * 5, 50)

                    score = ratio_score + pct_score

            return round(score, 2)

        except Exception as e:
            logger.warning(f"[错误] W2S02计算失败: {e}")
            return 0.0

    def calculate_W2S03(self, today_data: Dict, yesterday_data: Dict) -> float:
        """
        W2S03: 技术日线弱转强

        计算逻辑：
        - 收盘价突破5日/10日/20日均线的复合评分
        - 昨日未突破而今日突破则评分高

        Args:
            today_data: 今日日线数据
            yesterday_data: 昨日日线数据

        Returns:
            技术弱转强评分 (0-100)
        """
        try:
            # 改进版:有 ma 数值 → 连续乘性打分(均线趋势结构)
            ma5 = today_data.get('ma5'); ma10 = today_data.get('ma10'); ma20 = today_data.get('ma20')
            close = today_data.get('close')
            if ma5 is not None and ma10 is not None and ma20 is not None and close is not None:
                ta = self._trend_align(ma5, ma10, ma20)
                mp = self._ma_position(close, ma5, ma10, ma20)
                if ta is None or mp is None:
                    return None   # 整侧不可算 → Fail-Loud None
                return round(100.0 * ta * mp, 2)
            # 否则回落原 above_maX 二值逻辑(向后兼容)↓↓↓(保留下方原有代码不动)

            score = 0

            # 突破5日线
            yesterday_ma5 = yesterday_data.get('above_ma5', False)
            today_ma5 = today_data.get('above_ma5', False)
            if not yesterday_ma5 and today_ma5:
                score += 30

            # 突破10日线
            yesterday_ma10 = yesterday_data.get('above_ma10', False)
            today_ma10 = today_data.get('above_ma10', False)
            if not yesterday_ma10 and today_ma10:
                score += 25

            # 突破20日线
            yesterday_ma20 = yesterday_data.get('above_ma20', False)
            today_ma20 = today_data.get('above_ma20', False)
            if not yesterday_ma20 and today_ma20:
                score += 20

            # 多均线同时突破加分
            breakthroughs = sum([
                not yesterday_ma5 and today_ma5,
                not yesterday_ma10 and today_ma10,
                not yesterday_ma20 and today_ma20
            ])
            if breakthroughs >= 2:
                score += 15  # 多均线突破加分

            # 涨幅确认
            today_pct = today_data.get('change_pct', 0)
            if today_pct > 3:
                score += 10

            return round(min(score, 100), 2)

        except Exception as e:
            logger.warning(f"[错误] W2S03计算失败: {e}")
            return 0.0

    def calculate_W2S04(self, today_flow: float, yesterday_flow: float) -> float:
        """
        W2S04: 资金日线弱转强

        计算逻辑：
        - 主力资金从昨日净流出转为今日净流入
        - 变化幅度越大，评分越高

        Args:
            today_flow: 今日主力资金净流入（正为流入，负为流出）
            yesterday_flow: 昨日主力资金净流入

        Returns:
            资金弱转强评分 (0-100)
        """
        try:
            score = 0

            # 从流出转为流入
            if yesterday_flow < 0 and today_flow > 0:
                base_score = 50

                # 流入幅度加分
                # 流入金额越大，得分越高
                inflow_score = min(abs(today_flow) / 1e8 * 20, 30)
                base_score += inflow_score

                # 转换幅度加分（从大幅流出转为大幅流入）
                change = today_flow - yesterday_flow
                if change > 1e8:  # 转换超过1亿
                    base_score += 20

                score = min(base_score, 100)

            # 流出减少（也算弱转强的一种）
            elif yesterday_flow < 0 and today_flow < 0:
                if today_flow > yesterday_flow:  # 流出减少
                    reduction_ratio = (yesterday_flow - today_flow) / abs(yesterday_flow)
                    score = min(reduction_ratio * 50, 40)  # 最高40分

            return round(score, 2)

        except Exception as e:
            logger.warning(f"[错误] W2S04计算失败: {e}")
            return 0.0

    def calculate_W2S05(self, news_sentiment_change: float) -> float:
        """
        W2S05: 消息弱转强

        计算逻辑：
        - 利空消息转为利好消息
        - 市场情绪改善
        - 需要NLP情感分析支持

        Args:
            news_sentiment_change: 消息情感变化值（-1到1，正为改善）

        Returns:
            消息弱转强评分 (0-100)
        """
        try:
            # 情感变化映射到评分
            # 0 = 50分（中性）
            # +0.5 = 75分
            # +1.0 = 100分
            score = 50 + news_sentiment_change * 50

            return round(max(min(score, 100), 0), 2)

        except Exception as e:
            logger.warning(f"[错误] W2S05计算失败: {e}")
            return None  # Fail-Loud：计算异常=数据无效，返回 None 由上层剔除重归一化（不再伪装中性 50.0）

    def calculate_W2S06(self, today_sector_pct: float, yesterday_sector_pct: float) -> float:
        """
        W2S06: 板块日线弱转强

        计算逻辑：
        - 板块指数昨日涨幅 < 0（弱势）
        - 板块指数今日涨幅 > 2%（强势）
        - 板块整体弱转强带动个股

        ⚠️ 数据接入现状(2026-06-14)：本函数所需的"个股所属细分板块"昨/今涨跌幅，
           其中"板块涨跌幅"已可得(同花顺 stock_board_industry_summary_ths / index_ths)，
           但"个股→同花顺细分行业"映射缺失：
             - akshare 1.18.62 无 stock_board_industry_cons_ths（不存在）；
             - 本地 stock_info.sector 仅 19 个证监会粗门类(制造业等)且 52% 覆盖，太粗，
               用其做板块弱转强会是误导信号；
             - 逐股行业源 stock_individual_info_em 为东财(被封)。
           故主流程暂不喂 sector_data → W2S06 走默认/None，**不用粗门类伪造**。
           解锁路径：建 stock→细分行业映射层(pywencai 批量或解封 em)后接入。

        Args:
            today_sector_pct: 板块今日涨跌幅
            yesterday_sector_pct: 板块昨日涨跌幅

        Returns:
            板块弱转强评分 (0-100)
        """
        try:
            score = 0

            # 板块弱转强判断
            was_weak = yesterday_sector_pct < 0
            is_strong = today_sector_pct > 2

            if was_weak and is_strong:
                base_score = 50

                # 板块涨幅越大，得分越高
                sector_strength = min(today_sector_pct * 10, 30)
                base_score += sector_strength

                # 反转幅度加分
                reversal = today_sector_pct - yesterday_sector_pct
                if reversal > 3:
                    base_score += 20

                score = min(base_score, 100)

            return round(score, 2)

        except Exception as e:
            logger.warning(f"[错误] W2S06计算失败: {e}")
            return 0.0

    def calculate_all_factors(self, today_data: Dict, yesterday_data: Dict,
                               sector_data: Optional[Dict] = None,
                               flow_data: Optional[Dict] = None,
                               news_sentiment: Optional[float] = None) -> Dict[str, float]:
        """
        计算所有W2S因子

        Args:
            today_data: 今日日线数据
            yesterday_data: 昨日日线数据
            sector_data: 板块数据（可选）
            flow_data: 资金流向数据（可选）
            news_sentiment: 消息情感变化（可选）

        Returns:
            所有W2S因子字典
        """
        factors = {}

        # 核心因子：日线弱转强
        factors['W2S01'] = self.calculate_W2S01(today_data, yesterday_data)

        # 量价日线弱转强
        factors['W2S02'] = self.calculate_W2S02(today_data, yesterday_data)

        # 技术日线弱转强
        factors['W2S03'] = self.calculate_W2S03(today_data, yesterday_data)

        # 资金日线弱转强
        if flow_data:
            factors['W2S04'] = self.calculate_W2S04(
                flow_data.get('today_flow', 0),
                flow_data.get('yesterday_flow', 0)
            )
        else:
            factors['W2S04'] = None  # TODO: 缺少资金流向数据，返回 None 由上层处理

        # 消息弱转强
        if news_sentiment is not None:
            factors['W2S05'] = self.calculate_W2S05(news_sentiment)
        else:
            factors['W2S05'] = None  # TODO: 缺少消息情感数据，返回 None 由上层处理

        # 板块日线弱转强
        if sector_data:
            factors['W2S06'] = self.calculate_W2S06(
                sector_data.get('today_pct', 0),
                sector_data.get('yesterday_pct', 0)
            )
        else:
            factors['W2S06'] = None  # TODO: 缺少板块数据，返回 None 由上层处理

        return factors

    def get_w2s_signal_strength(self, factors: Dict[str, float]) -> Tuple[str, float]:
        """
        根据W2S因子综合判断信号强度

        Args:
            factors: W2S因子字典

        Returns:
            (信号强度等级, 综合评分)
        """
        # 核心因子权重（W2S01最重要）
        weights = {
            'W2S01': 0.35,  # 日线弱转强（核心）
            'W2S02': 0.20,  # 量价日线弱转强
            'W2S03': 0.15,  # 技术日线弱转强
            'W2S04': 0.10,  # 资金日线弱转强
            'W2S05': 0.10,  # 消息弱转强
            'W2S06': 0.10   # 板块日线弱转强
        }

        # 计算加权得分
        total_score = sum(factors.get(k, 0) * weights[k] for k in weights)

        # 判断信号强度
        if total_score >= 80:
            strength = '强信号'
        elif total_score >= 60:
            strength = '中等信号'
        elif total_score >= 40:
            strength = '弱信号'
        else:
            strength = '无信号'

        return strength, round(total_score, 2)


# ==================== 测试代码 ====================

def test_w2s_factors():
    """测试日线弱转强因子"""
    print("\n" + "="*70)
    print("日线弱转强因子测试")
    print("="*70)

    calculator = DailyW2SFactors()

    # 测试数据：昨日弱势 → 今日强势
    today_data = {
        'change_pct': 5.5,
        'volume': 1000000,
        'above_ma5': True,
        'above_ma10': True,
        'above_ma20': False
    }

    yesterday_data = {
        'change_pct': 1.0,  # 昨日涨幅<2%（弱势）
        'volume': 500000,
        'above_ma5': False,
        'above_ma10': False,
        'above_ma20': False
    }

    sector_data = {
        'today_pct': 3.5,
        'yesterday_pct': -1.2
    }

    flow_data = {
        'today_flow': 50000000,  # 今日净流入5000万
        'yesterday_flow': -30000000  # 昨日净流出3000万
    }

    # 计算所有因子
    factors = calculator.calculate_all_factors(
        today_data, yesterday_data,
        sector_data=sector_data,
        flow_data=flow_data,
        news_sentiment=0.3
    )

    print("\n因子计算结果:")
    for k, v in factors.items():
        print(f"  {k}: {v}")

    # 获取信号强度
    strength, total = calculator.get_w2s_signal_strength(factors)
    print(f"\n综合信号: {strength}, 评分: {total}")


if __name__ == '__main__':
    test_w2s_factors()