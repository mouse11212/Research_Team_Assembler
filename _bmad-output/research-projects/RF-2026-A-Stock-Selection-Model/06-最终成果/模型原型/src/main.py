"""
A股龙头战法量化系统 v3.1 - 统一入口脚本
Stock Selection Pipeline with Dependency Injection

按照指导文档7层架构重构，使用依赖注入实现低耦合。

运行方式：
    python main.py                    # 默认今天
    python main.py --date 20240329    # 指定日期
    python main.py --mode backtest    # 回测模式

Version: 3.1.0
Author: Quantitative Analyst Agent
"""

import sys
import os
import json
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np

# 设置编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logging_config import get_logger
from utils.observability import RunMetrics

logger = get_logger(__name__)

# 导入接口
from interfaces import (
    DataSource,
    MarketAnalyzer,
    FactorCalculatorProtocol,
    SignalGeneratorProtocol,
    RiskManagerProtocol
)

# 导入现有实现（v4.0架构）
from data_fetcher_v3_integrated import IntegratedDataFetcher
from factors.factor_calculator_v4 import FactorCalculatorV4
from factors.signal_generator_v4 import SignalGeneratorV4, SignalV4
from core.market_environment import MarketEnvironmentAnalyzer, EmotionPhase
from core.daily_report_generator import DailyReportGenerator
from core.performance_tracker import PerformanceTracker
from core.system_health_monitor import SystemHealthMonitor
from core.position_manager import PositionManager
from core.risk_manager import RiskManager
from core.data_quality_layer import DataQualityLayer
from core.display_resolver import DisplayResolver


@dataclass
class PipelineResult:
    """流水线执行结果"""
    trade_date: str
    execution_time: str
    market_environment: Dict[str, Any]
    recommended_stocks: List[Dict[str, Any]]
    signals: List[Dict[str, Any]]
    report_path: str
    signal_path: str
    health_status: Dict[str, Any]


class StockSelectionPipeline:
    """
    选股流水线 - 依赖注入各层组件

    通过接口依赖各层，而非直接实例化，实现低耦合。
    可以轻松替换各层实现（如切换数据源）。

    执行7步流程：
    1. 市场环境分析
    2. 获取股票池
    3. 因子计算
    4. 信号生成
    5. 风控过滤
    6. 推荐输出
    7. 报告生成
    """

    def __init__(
        self,
        data_source: DataSource,
        market_analyzer: MarketAnalyzer,
        factor_calculator: FactorCalculatorProtocol,
        signal_generator: SignalGeneratorProtocol,
        position_manager: PositionManager,
        risk_manager: RiskManager,
        report_generator: DailyReportGenerator,
        health_monitor: SystemHealthMonitor,
        output_dir: str = './output',
        recommend_count: int = 3
    ):
        """
        初始化流水线

        Args:
            data_source: 数据源（Layer 1）
            market_analyzer: 市场分析器（Layer 2）
            factor_calculator: 因子计算器（Layer 3）
            signal_generator: 信号生成器（Layer 5）
            position_manager: 仓位管理器（Layer 7）
            risk_manager: 风控管理器（Layer 7）
            report_generator: 报告生成器（Layer 8）
            health_monitor: 健康监控器（Layer 8）
            output_dir: 输出目录
        """
        self.data_source = data_source
        self.market_analyzer = market_analyzer
        self.factor_calculator = factor_calculator
        self.signal_generator = signal_generator
        self.position_manager = position_manager
        self.risk_manager = risk_manager
        self.report_generator = report_generator
        self.health_monitor = health_monitor
        self.output_dir = output_dir
        # 次日推荐数量（策略参数，来自 config.signal.recommend_count；默认 3 向后兼容）
        self.recommend_count = recommend_count

        # 创建输出目录
        os.makedirs(os.path.join(output_dir, 'reports'), exist_ok=True)
        os.makedirs(os.path.join(output_dir, 'signals'), exist_ok=True)

    def run(self, trade_date: str = None, top_n: int = 100) -> PipelineResult:
        """
        执行选股流水线

        Args:
            trade_date: 交易日期（默认今天）
            top_n: 扫描股票数量

        Returns:
            PipelineResult对象
        """
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y%m%d')

        logger.info("=" * 70)
        logger.info("A股龙头战法量化系统 v3.1 - 架构分层版")
        logger.info("=" * 70)
        logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"交易日期: {trade_date}")
        logger.info("=" * 70)

        result = PipelineResult(
            trade_date=trade_date,
            execution_time=datetime.now().isoformat(),
            market_environment={},
            recommended_stocks=[],
            signals=[],
            report_path='',
            signal_path='',
            health_status={}
        )

        # 可观测/可度量：本次运行的度量收集器（每步打点 + 落盘 JSON）
        metrics = RunMetrics('daily', trade_date, logger)

        try:
            # ==================== Step 1: 市场环境分析 ====================
            logger.info("【Step 1】市场环境分析（Layer 2）")
            logger.info("-" * 50)

            market_env = self._analyze_market_environment(trade_date)
            result.market_environment = market_env

            logger.info(f"  - 情绪周期: {market_env['emotion_phase']}")
            logger.info(f"  - 仓位系数: {market_env['position_multiplier']:.2f}")
            logger.info(f"  - 牛熊判断: {market_env['bull_bear_type']}")
            metrics.mark('01_市场环境',
                         emotion_phase=market_env['emotion_phase'],
                         position_multiplier=round(market_env['position_multiplier'], 2),
                         limit_up_count=market_env.get('limit_up_count'),
                         bull_bear=market_env['bull_bear_type'])

            # ==================== Step 2: 获取股票池 ====================
            logger.info("【Step 2】获取股票池（Layer 1）")
            logger.info("-" * 50)

            active_stocks = self.data_source.get_active_stocks(
                trade_date, min_change_pct=5.0, top_n=top_n
            )

            if active_stocks is None or len(active_stocks) == 0:
                logger.warning("[警告] 未获取到活跃股票数据")
                metrics.mark('02_股票池', active_count=0, abort='no_active_stocks')
                metrics.finalize(recommended=0, status='aborted_no_active_stocks')
                metrics.dump(self.output_dir)
                return result

            stats = self.data_source.get_data_stats()
            total_records = stats.get('stock_data', {}).get('total_records', 0)
            logger.info(f"  - SQLite历史记录: {total_records}条")
            logger.info(f"  - 活跃股票数: {len(active_stocks)}")
            metrics.mark('02_股票池', active_count=len(active_stocks),
                         total_records=total_records)

            # ==================== Step 2b: 数据质量过滤 ====================
            logger.info("【Step 2b】数据质量过滤（Layer 1）")
            logger.info("-" * 50)

            quality_layer = DataQualityLayer()
            _pre_quality_count = len(active_stocks)
            active_stocks, quality_report = quality_layer.filter_stock_pool(active_stocks)
            quality_layer.print_report(quality_report)

            if active_stocks is None or len(active_stocks) == 0:
                logger.warning("[警告] 数据质量过滤后无剩余股票，跳过今日选股")
                metrics.mark('02b_质量过滤', kept=0, removed=_pre_quality_count,
                             abort='empty_after_quality_filter')
                metrics.finalize(recommended=0, status='aborted_empty_after_quality_filter')
                metrics.dump(self.output_dir)
                return result

            logger.info(f"  - 过滤后活跃股票数: {len(active_stocks)}")
            metrics.mark('02b_质量过滤', kept=len(active_stocks),
                         removed=_pre_quality_count - len(active_stocks))

            # ==================== Step 3: 因子计算 ====================
            logger.info("【Step 3】因子计算（Layer 3 - 31因子体系）")
            logger.info("-" * 50)

            factor_results = []
            factor_inputs = []  # SignalGeneratorV4.generate_signals 输入格式
            _kline_fail = 0     # 可度量：K线历史缺失/读取失败的股票数

            # 获取龙虎榜数据（一次获取，复用）——走适配层 canonical
            try:
                lhb_data = self.data_source.get_lhb_data(trade_date) if hasattr(self.data_source, 'get_lhb_data') else pd.DataFrame()
            except Exception:
                lhb_data = pd.DataFrame()

            # 获取涨停池（一次获取，复用）——走适配层 canonical，喂 L007 连板数等
            try:
                limit_up_data = self.data_source.get_limit_up_pool(trade_date) if hasattr(self.data_source, 'get_limit_up_pool') else pd.DataFrame()
            except Exception:
                limit_up_data = pd.DataFrame()
            logger.info(f"   - 龙虎榜 {len(lhb_data)} 行 / 涨停池 {len(limit_up_data)} 只（适配层）")

            # A001 涨停板效应：分子=市场级今日涨停数(market_env)，分母=本地DB市场级60日涨停历史。
            # 两者同为全市场口径(change_pct>=9.9)，纯本地、无新数据源、无前视(分母 trade_date < 当日)。
            try:
                limit_up_history = self.data_source.get_market_limit_up_history(trade_date, days=60) \
                    if hasattr(self.data_source, 'get_market_limit_up_history') else []
            except Exception:
                limit_up_history = []
            limit_up_today = market_env.get('limit_up_count') if isinstance(market_env, dict) else None

            # 修复 S2：此前 head(3) 在“评分之前”就把候选砍到 3 只 → 往往无一达到买入阈值 →
            # 候选池为空。应对整个活跃池评分，Top-3 择优交给 Step 6 的排序+相关性过滤。
            for idx, row in active_stocks.head(top_n).iterrows():
                stock_code = row.get('stock_code', '')
                stock_name = row.get('stock_name', '')
                sector = row.get('sector', 'unknown')
                change_pct = row.get('change_pct', 0)

                try:
                    # 构造 stock_data（当前股票行）
                    stock_data = pd.DataFrame([row.to_dict()])
                    stock_data['stock_code'] = stock_code

                    # 获取K线历史构造 today_data / yesterday_data
                    today_data = {}
                    yesterday_data = {}
                    try:
                        # 修复 S2/前视偏差：按 trade_date 截止读取K线（date-aware），而非"最新N天"。
                        # 此前 get_kline_history 用 ORDER BY trade_date DESC LIMIT N，历史日期会取到
                        # trade_date 之后的未来数据（前视偏差），且与 active_stocks 的日期错配，
                        # 是每日候选池为空的直接原因。get_kline_range 纯本地、按日期截止、规范列名。
                        if hasattr(self.data_source, 'stock_store'):
                            kline_df = self.data_source.stock_store.get_kline_range(stock_code, '', trade_date)
                            if kline_df is not None and len(kline_df) > 30:
                                kline_df = kline_df.tail(30)
                        else:
                            kline_df = pd.DataFrame()

                        if kline_df is not None and len(kline_df) >= 2:
                            kline_df = kline_df.sort_values('trade_date')
                            today_row = kline_df.iloc[-1]
                            yesterday_row = kline_df.iloc[-2]
                            today_data = {
                                'change_pct': float(today_row.get('change_pct', 0)),
                                'volume': float(today_row.get('volume', 0)),
                                'close': float(today_row.get('close_price', 0)),
                                'open': float(today_row.get('open_price', 0)),
                                'high': float(today_row.get('high_price', 0)),
                                'low': float(today_row.get('low_price', 0)),
                                'above_ma5': float(today_row.get('close_price', 0)) > float(today_row.get('ma5', 0)),
                                'above_ma10': float(today_row.get('close_price', 0)) > float(today_row.get('ma10', 0)),
                                'above_ma20': float(today_row.get('close_price', 0)) > float(today_row.get('ma20', 0)),
                                'ma5': float(today_row.get('ma5', 0) or 0),
                                'ma10': float(today_row.get('ma10', 0) or 0),
                                'ma20': float(today_row.get('ma20', 0) or 0),
                            }
                            yesterday_data = {
                                'change_pct': float(yesterday_row.get('change_pct', 0)),
                                'volume': float(yesterday_row.get('volume', 0)),
                                'close': float(yesterday_row.get('close_price', 0)),
                                'above_ma5': float(yesterday_row.get('close_price', 0)) > float(yesterday_row.get('ma5', 0)),
                                'above_ma10': float(yesterday_row.get('close_price', 0)) > float(yesterday_row.get('ma10', 0)),
                                'above_ma20': float(yesterday_row.get('close_price', 0)) > float(yesterday_row.get('ma20', 0)),
                            }
                            # 计划2：注入改进版W2S01多日窗口（kline_df 已 date-aware 截止 trade_date、升序）
                            _L = getattr(self.factor_calculator.w2s_calculator, 'lookback_L', 5)
                            if len(kline_df) >= _L + 1:
                                _win = kline_df.iloc[-(_L + 1):-1]  # 今日之前 L 日，oldest→newest
                                today_data['window_klines'] = [
                                    {'close': float(r.get('close_price', 0) or 0),
                                     'volume': float(r.get('volume', 0) or 0),
                                     'ma20': (float(r.get('ma20')) if r.get('ma20') else None)}
                                    for _, r in _win.iterrows()
                                ]
                        elif kline_df is not None and len(kline_df) == 1:
                            # 只有今天数据，用active_stocks中的change_pct补充
                            today_row = kline_df.iloc[0]
                            today_data = {
                                'change_pct': float(today_row.get('change_pct', change_pct)),
                                'volume': float(today_row.get('volume', 0)),
                                'close': float(today_row.get('close_price', 0)),
                                'open': float(today_row.get('open_price', 0)),
                                'high': float(today_row.get('high_price', 0)),
                                'low': float(today_row.get('low_price', 0)),
                                'above_ma5': False,
                                'above_ma10': False,
                                'above_ma20': False,
                            }
                    except Exception as e:
                        _kline_fail += 1
                        logger.warning(f"[警告] 获取K线历史失败 {stock_code}: {e}")

                    factors = self.factor_calculator.calculate_all_factors(
                        stock_code=stock_code,
                        trade_date=trade_date,
                        market_data=active_stocks,
                        stock_data=stock_data,
                        today_data=today_data,
                        yesterday_data=yesterday_data,
                        lhb_data=lhb_data,
                        limit_up_data=limit_up_data,
                        limit_up_history=limit_up_history,
                        limit_up_today=limit_up_today
                    )
                    if factors:
                        factor_results.append({
                            'code': stock_code,
                            'name': stock_name,
                            'sector': sector,
                            'factors': factors,
                            'change_pct': change_pct
                        })
                        factor_inputs.append({
                            'stock_code': stock_code,
                            'stock_name': stock_name,
                            'factors': factors
                        })

                        # 存储因子数据
                        self.data_source.save_factors(stock_code, trade_date, factors)

                except Exception as e:
                    warnings.warn(f"因子计算失败: {stock_code} - {e}")
                    continue

            logger.info(f"  - 因子计算完成: {len(factor_results)}只股票")
            metrics.mark('03_因子计算', scored=len(factor_results),
                         scanned=min(len(active_stocks), top_n), kline_fail=_kline_fail)

            # ==================== Step 4: 信号生成 ====================
            logger.info("【Step 4】信号生成（Layer 5）")
            logger.info("-" * 50)

            # 断点1接线：尝试启用 IC 加权（样本充足才启用，否则回落默认权重）。
            # ICIR 来自 ic_history（data/compute_ic_history.py 离线计算落库）。
            ic_enabled = False
            try:
                icir = self.data_source.get_latest_icir() \
                    if hasattr(self.data_source, 'get_latest_icir') else {}
                ic_enabled = self.signal_generator.enable_ic_weights(icir) \
                    if hasattr(self.signal_generator, 'enable_ic_weights') else False
            except Exception as e:
                warnings.warn(f"IC加权启用失败，回落默认权重: {e}")
            logger.info(f"  - IC加权: {'启用' if ic_enabled else '回落默认权重（样本不足/无ic_history）'}")
            metrics.mark('03b_IC加权', ic_enabled=ic_enabled)

            signals = []
            try:
                raw_signals = self.signal_generator.generate_signals(
                    factor_inputs, emotion_temperature=65
                )
                for signal in raw_signals:
                    # 从 factor_results 匹配 sector
                    fr = next((fr for fr in factor_results if fr['code'] == signal.stock_code), None)
                    sector = fr['sector'] if fr else 'unknown'
                    signals.append({
                        'code': signal.stock_code,
                        'name': signal.stock_name,
                        'sector': sector,
                        'signal_type': signal.signal_type,
                        'composite_score': signal.composite_score,
                        'position_suggestion': signal.position_suggestion,
                        'emotion_phase': signal.emotion_phase,
                        'factor_scores': signal.factors
                    })
            except Exception as e:
                warnings.warn(f"信号生成失败: {e}")

            logger.info(f"  - 原始信号数: {len(signals)}")
            metrics.mark('04_信号生成', raw_signals=len(signals))

            # ==================== Step 5: 风控过滤 ====================
            logger.info("【Step 5】风控过滤（Layer 7）")
            logger.info("-" * 50)

            # SignalGeneratorV4.generate_signals 已内部过滤（仅保留 buy/strong_buy）
            result.signals = signals

            logger.info(f"  - 过滤后信号数: {len(signals)}")
            metrics.mark('05_风控过滤', signals=len(signals))

            # ==================== Step 6: 推荐输出 ====================
            logger.info("【Step 6】推荐输出（Layer 7）")
            logger.info("-" * 50)

            # 按得分排序
            signals_sorted = sorted(signals, key=lambda x: x['composite_score'], reverse=True)

            # 同板块最多1只
            recommended = self.risk_manager.apply_correlation_filter(signals_sorted, max_per_sector=1)
            recommended = recommended[:self.recommend_count]

            result.recommended_stocks = recommended

            if recommended:
                logger.info("【推荐股票】")
                logger.info("=" * 50)
                for i, stock in enumerate(recommended, 1):
                    logger.info(f"推荐{i}: {stock['code']} {stock['name']}")
                    logger.info(f"  - 板块: {stock['sector']}")
                    logger.info(f"  - 信号类型: {stock['signal_type']}")
                    logger.info(f"  - 综合得分: {stock['composite_score']:.2f}")
                    logger.info(f"  - 建议仓位: {stock['position_suggestion']:.2f}%")
                    w2s_score = stock['factor_scores'].get('W2S01', 50) or 0
                    l_score = stock['factor_scores'].get('L001', 50) or 0
                    logger.info(f"  - 日线弱转强(W2S01): {w2s_score:.2f}")
                    logger.info(f"  - 龙头识别(L001): {l_score:.2f}")
            else:
                logger.info("【无推荐】今日未发现符合条件的股票")

            metrics.mark('06_推荐输出', recommended=len(recommended),
                         top_picks=[f"{s['code']}:{s['composite_score']:.1f}" for s in recommended])

            # ==================== Step 7: 报告生成 ====================
            logger.info("【Step 7】报告生成（Layer 8）")
            logger.info("-" * 50)

            # 存储市场情绪
            emotion_data = {
                'emotion_phase': market_env['emotion_phase'],
                'position_multiplier': market_env['position_multiplier'],
                'limit_up_count': market_env.get('limit_up_count', 50),
                'bull_bear_type': market_env['bull_bear_type']
            }
            self.data_source.save_market_emotion(trade_date, emotion_data)
            logger.info(f"  - 市场情绪数据已存入SQLite")

            # ===== 展示层 join：仅在最终呈现时，用本地表把 code → 名称/板块/概念 =====
            # 计算阶段全程用 code；此处只为人类可读展示富集，纯读本地、不联网。
            resolver = DisplayResolver()
            sig_stats = resolver.enrich(signals, code_key='code')
            rec_stats = resolver.enrich(recommended, code_key='code')
            metrics.mark('06b_展示层映射',
                         name_hit=f"{rec_stats['name_hit']}/{rec_stats['total']}",
                         sector_hit=f"{rec_stats['sector_hit']}/{rec_stats['total']}",
                         signals_named=f"{sig_stats['name_hit']}/{sig_stats['total']}")

            # 生成报告
            report_path = self.report_generator.generate_pre_market_report(
                trade_date, signals, market_env['emotion_phase'],
                {'market_type': market_env['bull_bear_type']},
                recommended
            )
            result.report_path = report_path
            logger.info(f"  - 盘前报告: {report_path}")

            # 保存信号记录（处理numpy类型序列化）
            def _convert_to_native(obj):
                if isinstance(obj, dict):
                    return {k: _convert_to_native(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_convert_to_native(v) for v in obj]
                elif hasattr(obj, 'item'):  # numpy类型
                    return obj.item()
                return obj

            signal_path = os.path.join(self.output_dir, 'signals', f'signals_{trade_date}.json')
            with open(signal_path, 'w', encoding='utf-8') as f:
                json.dump(_convert_to_native(signals), f, ensure_ascii=False, indent=2)
            result.signal_path = signal_path
            logger.info(f"  - 信号记录: {signal_path}")

            # 健康检查
            health_summary = self.health_monitor.get_system_health_summary()
            result.health_status = health_summary
            logger.info(f"  - 系统健康度: {health_summary['overall_health']:.2f}%")
            metrics.mark('07_报告生成', report=os.path.basename(report_path),
                         signals_saved=len(signals),
                         system_health=round(health_summary.get('overall_health', 0), 2))

            # 可观测/可度量：本次运行整体度量落盘（机器可读，可横向对比）
            metrics.finalize(recommended=len(recommended),
                             report=os.path.basename(report_path),
                             status='ok')
            metrics.dump(self.output_dir)

            # ==================== 输出汇总 ====================
            logger.info("=" * 70)
            logger.info("【执行完成】")
            logger.info("=" * 70)
            logger.info(f"交易日期: {trade_date}")
            logger.info(f"推荐股票: {len(recommended)}只")
            logger.info(f"报告路径: {report_path}")
            logger.info("=" * 70)

            return result

        except Exception as e:
            logger.error(f"[执行错误] {e}")
            import traceback
            traceback.print_exc()
            # 失败路径同样可观测/可追溯：记录错误并落盘度量
            try:
                metrics.mark('99_异常中止', error=type(e).__name__)
                metrics.finalize(recommended=0, status='error', error=str(e)[:200])
                metrics.dump(self.output_dir)
            except Exception:
                pass
            return result

    def _analyze_market_environment(self, trade_date: str) -> Dict[str, Any]:
        """
        分析市场环境

        Args:
            trade_date: 交易日期

        Returns:
            市场环境字典
        """
        # TODO: 从真实数据源获取市场数据（拒绝模拟数据）
        # 当前实现因缺少真实数据接口而返回 None，需接入 AKShare 实时行情
        try:
            spot_df = self.data_source.get_active_stocks(trade_date)
            if spot_df is not None and not spot_df.empty:
                limit_up_count = int((spot_df['change_pct'] >= 9.9).sum()) if 'change_pct' in spot_df.columns else None
                total_stocks = len(spot_df)
            else:
                limit_up_count = None
                total_stocks = None
        except Exception as e:
            logger.warning(f"[警告] 获取市场环境数据失败: {e}")
            limit_up_count = None
            total_stocks = None

        if limit_up_count is None:
            raise RuntimeError("无法获取真实市场环境数据：get_active_stocks 返回空，情绪周期、仓位系数等关键指标无法计算。")

        # TODO: 接入真实的连板高度、板块扩散度、换手率动量数据
        consecutive_board_max = None  # TODO: 需历史涨停数据计算
        sector_diffusion = None       # TODO: 需板块数据计算
        turnover_momentum = None      # TODO: 需历史换手率计算

        market_env = self.market_analyzer.analyze(
            limit_up_count=limit_up_count,
            total_stocks=total_stocks or 5000,
            consecutive_board_max=consecutive_board_max or 3,
            sector_diffusion=sector_diffusion or 0.5,
            turnover_momentum=turnover_momentum or 1.0
        )

        emotion_phase = market_env.emotion_phase
        position_multiplier = market_env.position_multiplier

        # TODO: 接入真实的指数数据和历史序列
        index_data = None
        limit_up_history = None
        sector_diffusion_history = None

        if index_data is None:
            bull_bear = {'market_type': 'neutral', 'confidence': 0}
        else:
            bull_bear = self.market_analyzer.judge_bull_bear_market(
                index_data, limit_up_history or [], sector_diffusion_history or []
            )

        return {
            'emotion_phase': emotion_phase.value,
            'position_multiplier': position_multiplier,
            'bull_bear_type': bull_bear.get('market_type', 'neutral'),
            'bull_bear_confidence': bull_bear.get('confidence', 0),
            'limit_up_count': limit_up_count,
            'consecutive_board_max': consecutive_board_max
        }

    def close(self) -> None:
        """关闭流水线资源"""
        if hasattr(self.data_source, 'close'):
            self.data_source.close()
        logger.info("[关闭] 流水线资源已释放")


def create_pipeline(output_dir: str = './output') -> StockSelectionPipeline:
    """
    工厂函数 - 组装各层实现

    通过此函数可以轻松切换各层实现：
    - 替换数据源（如从SQLite切换到PostgreSQL）
    - 替换因子计算器
    - 替换信号生成器

    Args:
        output_dir: 输出目录

    Returns:
        StockSelectionPipeline实例
    """
    # 数据库路径
    # 修复 RC-G（单一真相源）：此前指向 output_dir/data/stock_history.db（小的过期副本），
    # 与回测/规范库不一致，导致历史日期取不到数据而误触 akshare 并失败。
    # 统一指向规范库 src/data/stock_history.db（相对本文件定位，不受运行 cwd 影响）。
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'stock_history.db')

    # 读取策略参数：次日推荐数量（config.signal.recommend_count，默认 3 向后兼容）。
    # 注意：config.yaml 位于 src 的上级目录（模型原型/），用绝对路径精确定位，
    # 不依赖 load_config 的默认相对路径解析（其默认仅在 src/ 下找，会漏掉本文件）。
    try:
        from utils.config_loader import load_config
        _cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.yaml')
        _cfg = load_config(_cfg_path)
        recommend_count = int(_cfg.get('signal', {}).get('recommend_count', 3))
    except Exception:
        recommend_count = 3

    # 组装各层实现（v4.0）
    # A004 复活：FactorCalculatorV4 注入 data_source，使 get_turnover_momentum/get_sector_diffusion 可用。
    # 注意：get_turnover_momentum 基于"本地最新N日"换手率（实盘当日正确）；回测路径的
    # FactorCalculatorV4(config) 不注入（避免历史回测取到未来换手率的前视偏差）。
    data_source = IntegratedDataFetcher(db_path=db_path)
    return StockSelectionPipeline(
        data_source=data_source,                                  # Layer 1
        market_analyzer=MarketEnvironmentAnalyzer(),              # Layer 2
        factor_calculator=FactorCalculatorV4(data_fetcher=data_source),  # Layer 3（注入→A004本地复活）
        signal_generator=SignalGeneratorV4(),                     # Layer 5
        position_manager=PositionManager(),                       # Layer 7
        risk_manager=RiskManager(),                               # Layer 7
        report_generator=DailyReportGenerator(
            os.path.join(output_dir, 'reports'),
            recommend_count=recommend_count
        ),                                                        # Layer 8
        health_monitor=SystemHealthMonitor(
            os.path.join(output_dir, 'health.log')
        ),                                                        # Layer 8
        output_dir=output_dir,
        recommend_count=recommend_count
    )


# ==================== 主执行入口 ====================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='A股龙头战法选股系统')
    parser.add_argument('--date', default=datetime.now().strftime('%Y%m%d'),
                        help='交易日期 (YYYYMMDD)')
    parser.add_argument('--mode', choices=['daily', 'backtest', 'validate'],
                        default='daily', help='执行模式')
    parser.add_argument('--output', default='./output', help='输出目录')
    parser.add_argument('--top-n', type=int, default=100, help='扫描股票数量')

    args = parser.parse_args()

    # 创建流水线
    pipeline = create_pipeline(output_dir=args.output)

    # 执行选股
    result = pipeline.run(trade_date=args.date, top_n=args.top_n)

    # 关闭资源
    pipeline.close()

    # 输出最终结果
    logger.info("=" * 70)
    logger.info("【最终输出】")
    logger.info("=" * 70)

    if result.recommended_stocks:
        logger.info("推荐股票:")
        for stock in result.recommended_stocks:
            logger.info(f"  {stock['code']} {stock['name']} - 得分:{stock['composite_score']:.2f}")
    else:
        logger.info("今日无推荐股票")

    logger.info(f"报告路径: {result.report_path}")
    logger.info(f"信号路径: {result.signal_path}")
    logger.info("=" * 70)