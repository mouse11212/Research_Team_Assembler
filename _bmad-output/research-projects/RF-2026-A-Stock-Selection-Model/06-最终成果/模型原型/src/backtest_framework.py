"""
回测框架 - A股龙头战法选股模型v4.0
Backtest Framework - Dragon Leader Strategy v4.0

完整重构：
- T+1交易循环消除前视偏差
- 接入SignalGeneratorV4 + FactorCalculatorV4
- 接入MarketEnvironmentAnalyzer情绪周期
- A股交易规则模拟（T+1、涨跌停、滑点、手续费）
- 风险指标修复（年化夏普、正确最大回撤）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json

from factors.signal_generator_v4 import SignalGeneratorV4, SignalV4
from factors.factor_calculator_v4 import FactorCalculatorV4
from core.market_environment import MarketEnvironmentAnalyzer, EmotionPhase, MarketEnvironment
from core.position_manager import PositionManager, PositionDecision
from data_fetcher_v3_integrated import IntegratedDataFetcher
from core.optimized_database_manager import OptimizedDatabaseManager
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Trade:
    """交易记录"""
    trade_id: str
    stock_code: str
    stock_name: str
    signal_type: str  # 'buy', 'sell'
    price: float
    shares: int
    amount: float
    timestamp: datetime
    signal_score: float
    signal_date: str  # 信号生成日期（用于验证T+1）
    slippage: float = 0.0
    commission: float = 0.0
    tax: float = 0.0


@dataclass
class Position:
    """持仓记录"""
    stock_code: str
    stock_name: str
    shares: int
    cost_price: float
    current_price: float
    position_value: float
    profit_loss: float
    profit_loss_pct: float
    open_date: datetime
    buy_date: str  # 买入日期（YYYYMMDD），用于T+1卖出限制


@dataclass
class PortfolioSnapshot:
    """组合快照"""
    date: datetime
    total_value: float
    cash: float
    positions: List[Position]
    daily_return: float
    cumulative_return: float
    emotion_phase: str = ''


class BacktestEngine:
    """
    回测引擎 v4.0

    T+1交易循环设计：
    - T日收盘后：计算因子 → 生成信号
    - T+1日开盘：执行交易（开盘价成交）
    """

    # 交易费用参数
    COMMISSION_RATE = 0.00025  # 佣金万2.5
    STAMP_TAX_RATE = 0.001     # 印花税千1（仅卖出）
    SLIPPAGE_RATE = 0.001      # 滑点0.1%

    # 退出规则（S1：让回测产生完整买卖配对，使胜率/盈亏比真实；参数后续由 S5 优化）
    MAX_HOLD_DAYS = 5          # 最长持有自然日（对应1-3个交易日 + 周末缓冲）
    STOP_LOSS_PCT = 7.0        # 止损线 -7%
    TAKE_PROFIT_PCT = 12.0     # 止盈线 +12%（盈亏比≈1.7，对齐宏观目标≥1.5）

    def __init__(self, initial_capital: float = 100000, config: Optional[Dict] = None,
                 db_path: str = "./data/stock_history.db"):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.config = config or {}

        # 初始化v4.0组件
        # 修复 RC-A：改用 IntegratedDataFetcher（指向规范化的真实数据库 data/stock_history.db），
        # 其内部 db_manager 即数据访问层。此前 OptimizedDatabaseManager() 默认指向空的
        # dragon_leader_optimized.db，导致回测读不到任何历史数据 → 0 交易。
        self.fetcher = IntegratedDataFetcher(db_path=db_path)
        self.signal_generator = SignalGeneratorV4(config)
        self.factor_calculator = FactorCalculatorV4(config)
        self.market_analyzer = MarketEnvironmentAnalyzer()
        self.position_manager = PositionManager()
        self.db = self.fetcher.db_manager

        # 回测数据
        self.trades: List[Trade] = []
        self.positions: Dict[str, Position] = {}
        self.snapshots: List[PortfolioSnapshot] = []

        # 统计数据
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

        logger.info(f"[OK] 回测引擎v4.0初始化成功")
        logger.info(f"   - 初始资金: {initial_capital:,.0f}元")
        logger.info(f"   - 佣金率: {self.COMMISSION_RATE*10000:.0f}万分")
        logger.info(f"   - 印花税率: {self.STAMP_TAX_RATE*1000:.0f}千分")
        logger.info(f"   - 滑点: {self.SLIPPAGE_RATE*100:.2f}%")

    def run_backtest(self, start_date: str, end_date: str) -> Dict:
        """
        运行回测（T+1交易循环）

        Args:
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)

        Returns:
            回测结果字典
        """
        logger.info(f"开始回测: {start_date} - {end_date}")

        try:
            trade_dates = self._generate_trade_dates(start_date, end_date)
            if len(trade_dates) < 2:
                logger.error("[错误] 回测区间至少需要2个交易日")
                return {}

            logger.info(f"[信息] 回测天数: {len(trade_dates)}天")

            # T+1循环：最后一天只更新持仓，不生成新信号
            for i in range(len(trade_dates) - 1):
                t_date = trade_dates[i]
                t1_date = trade_dates[i + 1]

                logger.info(f"[进度] {i+1}/{len(trade_dates)-1} | T日={t_date} | T+1日={t1_date}")

                # === T日收盘后 ===
                # 1. 更新持仓价格（用T日收盘价）
                self._update_positions(t_date)

                # 2. 分析市场环境
                market_env = self._analyze_market(t_date)
                if market_env is None:
                    logger.warning(f"  [跳过] {t_date} 市场环境数据缺失，跳过当日交易")
                    continue

                # 3. 计算因子并生成信号（基于T日收盘数据）
                signals = self._generate_signals_v4(t_date, market_env)

                # === T+1日开盘前 ===
                # 4a. 检查持仓退出（止损/止盈/持有到期），先平仓释放资金
                self._check_exit_conditions(t1_date)
                # 4b. 执行新买入信号（用T+1日开盘价成交）
                self._execute_signals_t1(signals, t1_date, market_env)

                # 5. 记录T+1日快照
                self._take_snapshot(t1_date, market_env)

            # 6. 计算最终结果
            results = self._calculate_results()

            logger.info(f"回测完成")

            return results

        except Exception as e:
            logger.error(f"[错误] 回测失败: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _generate_trade_dates(self, start_date: str, end_date: str) -> List[str]:
        """生成交易日期列表（接入真实A股交易日历）"""
        from utils.trade_calendar import get_trade_dates_between
        dates = get_trade_dates_between(start_date, end_date)
        if not dates:
            # 交易日历未加载时的降级：仅跳过周末
            logger.warning("[警告] 交易日历未加载，降级为仅跳过周末")
            start = datetime.strptime(start_date, '%Y%m%d')
            end = datetime.strptime(end_date, '%Y%m%d')
            dates = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    dates.append(current.strftime('%Y%m%d'))
                current += timedelta(days=1)
        return dates

    def _analyze_market(self, trade_date: str) -> MarketEnvironment:
        """分析市场环境（基于本地数据库当日全市场截面）"""
        try:
            # 修复 RC-D：从本地规范库读取当日全市场截面，而非 akshare 实时快照
            # （实时快照无法服务历史日期，是此前每日被跳过、0 交易的直接原因之一）
            spot_df = self.db.get_all_stocks_kline(trade_date)

            if spot_df is None or len(spot_df) == 0:
                logger.warning(f"[警告] {trade_date} 本地无全市场截面数据，无法分析市场环境")
                return None

            # 计算市场指标
            limit_up_count = int((spot_df['change_pct'] >= 9.9).sum()) if 'change_pct' in spot_df.columns else None
            total_stocks = len(spot_df)
            # TODO: 以下指标需接入真实历史数据计算，当前为简化默认值
            consecutive_board_max = 3  # TODO: 需历史涨停数据计算连板高度
            sector_diffusion = 0.5     # TODO: 需板块数据计算扩散度
            turnover_momentum = 1.0    # TODO: 需历史换手率计算动量

            market_env = self.market_analyzer.analyze(
                limit_up_count=limit_up_count,
                total_stocks=total_stocks,
                consecutive_board_max=consecutive_board_max,
                sector_diffusion=sector_diffusion,
                turnover_momentum=turnover_momentum
            )

            logger.info(f"  [市场环境] 情绪: {market_env.emotion_phase.value}, 评分: {market_env.emotion_score:.1f}, 仓位系数: {market_env.position_multiplier:.2f}")
            return market_env

        except Exception as e:
            logger.warning(f"  [警告] 市场环境分析失败: {e}")
            # TODO: 异常时返回 None，禁止返回硬编码默认值
            return None

    def _generate_signals_v4(self, trade_date: str, market_env: MarketEnvironment) -> List[SignalV4]:
        """生成v4.0信号（基于T日收盘数据）"""
        try:
            # 获取当日活跃股票池（从本地规范库读取全市场截面）
            spot_df = self.db.get_all_stocks_kline(trade_date)
            if spot_df is None or len(spot_df) == 0:
                # 回退：基于历史K线反推活跃股池（仍走本地库）
                spot_df = self.fetcher.get_active_stocks(trade_date)
            if spot_df is None or len(spot_df) == 0:
                return []

            # C-Lite（2026-06-18）：与当日选股统一用"三维龙头强度"排序（归一化涨幅+换手率+量比），
            # 替代原"绝对涨幅"排序。消除两处问题：① 回测/选股活跃池逻辑分叉（违背单一内核）；
            # ② 按绝对涨幅 top100 致创业板 20% 涨停垄断、主板 10% 涨停永不入池（见 07-改进建议/10）。
            # 先筛 change_pct>=5% 活跃候选，再三维排序取前100；无候选则回退绝对涨幅（极端弱市兜底）。
            if 'change_pct' in spot_df.columns:
                _chg = pd.to_numeric(spot_df['change_pct'], errors='coerce')
                cand = spot_df[_chg >= 5.0].copy()
                if not cand.empty:
                    # 弱转强准入门槛(spec 13):与选股路径统一,回测也经门槛(否则回测/选股活跃池逻辑分叉)
                    cand = self.fetcher._filter_by_w2s01_gate(cand, trade_date, self.fetcher.w2s01_gate)
                if cand is not None and not cand.empty:
                    spot_df = self.fetcher._rank_by_leader_strength(cand, trade_date).head(100)
                else:
                    spot_df = spot_df.sort_values('change_pct', ascending=False).head(100)

            stock_pool = spot_df['stock_code'].dropna().unique().tolist() if 'stock_code' in spot_df.columns else []
            if not stock_pool:
                return []

            logger.info(f"  [信号生成] 股票池: {len(stock_pool)}只")

            # 逐只计算因子
            factor_results = []
            for stock_code in stock_pool[:30]:  # 限制30只以控制计算量
                try:
                    # 从SQLite获取最近5天K线
                    kline_df = self.db.get_kline_range(stock_code, '', trade_date)
                    if kline_df is None or len(kline_df) < 2:
                        continue

                    # 构造today_data和yesterday_data
                    # 修复 RC-F：get_kline_range 不返回 stock_code 列，而 L 类因子需按
                    # stock_data['stock_code'] 过滤，缺列会抛 KeyError 并被静默吞掉 → 0 信号。
                    kline_df = kline_df.sort_values('trade_date').copy()
                    kline_df['stock_code'] = stock_code
                    today_row = kline_df.iloc[-1]
                    yesterday_row = kline_df.iloc[-2] if len(kline_df) >= 2 else today_row

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

                    # 计划2：注入改进版W2S01多日窗口（kline_df 已按 trade_date 升序、截止当日）
                    _L = getattr(self.factor_calculator.w2s_calculator, 'lookback_L', 5)
                    if len(kline_df) >= _L + 1:
                        _win = kline_df.iloc[-(_L + 1):-1]  # 今日之前 L 日，oldest→newest
                        today_data['window_klines'] = [
                            {'close': float(r.get('close_price', 0) or 0),
                             'volume': float(r.get('volume', 0) or 0),
                             'ma20': (float(r.get('ma20')) if r.get('ma20') else None)}
                            for _, r in _win.iterrows()
                        ]

                    # 计算因子
                    # 修复 RC-E：必须传入 market_data(全市场截面) 与 stock_data(单股K线)，
                    # 否则 calculate_all_factors 因二者为空而直接返回 {} → 0 信号。
                    factors = self.factor_calculator.calculate_all_factors(
                        stock_code=stock_code,
                        trade_date=trade_date,
                        market_data=spot_df,
                        stock_data=kline_df,
                        today_data=today_data,
                        yesterday_data=yesterday_data
                    )

                    stock_name = spot_df[spot_df['stock_code'] == stock_code]['stock_name'].iloc[0] if 'stock_name' in spot_df.columns else stock_code

                    factor_results.append({
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'factors': factors
                    })

                except Exception as e:
                    continue

            if not factor_results:
                return []

            # 生成信号
            signals = self.signal_generator.generate_signals(
                factor_results,
                emotion_temperature=market_env.emotion_score
            )

            logger.info(f"  [信号生成] 买入信号: {len(signals)}个")
            return signals

        except Exception as e:
            logger.error(f"  [错误] 信号生成失败: {e}")
            return []

    def _execute_signals_t1(self, signals: List[SignalV4], t1_date: str, market_env: MarketEnvironment):
        """T+1日执行交易"""
        if not signals:
            return

        # 1. 先处理卖出信号
        sell_signals = [s for s in signals if s.signal_type in ['sell', 'strong_sell']]
        for signal in sell_signals:
            if signal.stock_code in self.positions:
                self._sell_position_t1(signal, t1_date)

        # 2. 再处理买入信号
        buy_signals = [s for s in signals if s.signal_type in ['strong_buy', 'buy']]

        for signal in buy_signals:
            # 检查是否已有持仓
            if signal.stock_code in self.positions:
                continue

            self._buy_position_t1(signal, t1_date, market_env)

    def _check_exit_conditions(self, t1_date: str):
        """检查持仓退出条件（止损/止盈/持有到期），以 T+1 开盘价平仓。

        修复 S1 正确性缺陷：generate_signals 仅产出 buy 信号、回测循环原本无退出机制，
        持仓永不平仓 → 胜率/盈亏比不可信。此处补上基础退出，使买卖配对完整。
        """
        for stock_code in list(self.positions.keys()):
            position = self.positions[stock_code]
            df = self.db.get_kline_range(stock_code, t1_date, t1_date)
            if df is None or len(df) == 0:
                continue
            row = df.iloc[0]
            open_price = float(row.get('open_price', 0))
            change_pct = float(row.get('change_pct', 0))
            if open_price <= 0:
                continue

            hold_days = (datetime.strptime(t1_date, '%Y%m%d') - position.open_date).days
            if hold_days < 1:
                continue  # T+1 限制：买入当日不可卖
            if change_pct <= -9.9:
                continue  # 跌停无法卖出

            gain_pct = ((open_price - position.cost_price) / position.cost_price * 100
                        if position.cost_price > 0 else 0)
            reason = None
            if gain_pct <= -self.STOP_LOSS_PCT:
                reason = 'stop_loss'
            elif gain_pct >= self.TAKE_PROFIT_PCT:
                reason = 'take_profit'
            elif hold_days >= self.MAX_HOLD_DAYS:
                reason = 'max_hold'

            if reason:
                self._close_position(stock_code, t1_date, open_price, reason)

    def _close_position(self, stock_code: str, t1_date: str, open_price: float, reason: str):
        """以给定开盘价平仓并记账（含滑点、佣金、印花税），供退出条件调用"""
        position = self.positions.get(stock_code)
        if not position:
            return

        executed_price = open_price * (1 - self.SLIPPAGE_RATE)
        actual_amount = position.shares * executed_price
        commission = actual_amount * self.COMMISSION_RATE
        tax = actual_amount * self.STAMP_TAX_RATE
        total_revenue = actual_amount - commission - tax
        self.cash += total_revenue

        cost = position.shares * position.cost_price
        profit_loss = total_revenue - cost
        profit_loss_pct = (profit_loss / cost * 100) if cost > 0 else 0

        trade = Trade(
            trade_id=f"{t1_date}_{stock_code}_SELL",
            stock_code=stock_code,
            stock_name=position.stock_name,
            signal_type='sell',
            price=executed_price,
            shares=position.shares,
            amount=actual_amount,
            timestamp=datetime.strptime(t1_date, '%Y%m%d'),
            signal_score=0.0,
            signal_date=t1_date,
            slippage=self.SLIPPAGE_RATE,
            commission=commission,
            tax=tax
        )
        self.trades.append(trade)
        self.total_trades += 1
        if profit_loss > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        logger.info(f"    [平仓-{reason}] {stock_code} {position.shares}股 @ {executed_price:.2f}元 "
                    f"({profit_loss_pct:+.2f}%)")
        del self.positions[stock_code]

    def _buy_position_t1(self, signal: SignalV4, t1_date: str, market_env: MarketEnvironment):
        """T+1日买入（开盘价成交）"""
        try:
            # 获取T+1日数据
            t1_df = self.db.get_kline_range(signal.stock_code, t1_date, t1_date)
            if t1_df is None or len(t1_df) == 0:
                logger.warning(f"    [跳过] {signal.stock_code} T+1日无数据")
                return

            t1_row = t1_df.iloc[0]
            open_price = float(t1_row.get('open_price', 0))
            high_price = float(t1_row.get('high_price', 0))
            low_price = float(t1_row.get('low_price', 0))
            close_price = float(t1_row.get('close_price', 0))
            change_pct = float(t1_row.get('change_pct', 0))

            if open_price <= 0:
                return

            # 检查涨停：T+1日涨停无法买入
            if change_pct >= 9.9:
                logger.warning(f"    [跳过] {signal.stock_code} T+1日涨停，无法买入")
                return

            # 计算仓位（接入PositionManager）
            stock_name = signal.stock_name
            sector = 'unknown'
            position_decision = self.position_manager.calculate_position_for_stock(
                stock_code=signal.stock_code,
                stock_name=stock_name,
                sector=sector,
                emotion_phase=market_env.emotion_phase,
                total_capital=self.cash,
                signal_score=signal.composite_score,
                existing_positions=[
                    {'stock_code': p.stock_code, 'sector': sector}
                    for p in self.positions.values()
                ]
            )

            # 情绪冰点限制仓位
            max_position_ratio = market_env.position_multiplier * 0.33
            position_ratio = min(position_decision.recommended_position, max_position_ratio)

            # 计算买入金额
            buy_amount = self.cash * position_ratio

            if buy_amount <= 0:
                return

            # 计算买入股数（100股为一手）
            shares = int(buy_amount / open_price / 100) * 100
            if shares == 0:
                return

            # 实际买入金额（含滑点）
            executed_price = open_price * (1 + self.SLIPPAGE_RATE)
            actual_amount = shares * executed_price
            commission = actual_amount * self.COMMISSION_RATE
            total_cost = actual_amount + commission

            if total_cost > self.cash:
                logger.warning(f"    [跳过] {signal.stock_code} 资金不足: 需要{total_cost:,.0f}, 剩余{self.cash:,.0f}")
                return

            # 更新资金
            self.cash -= total_cost

            # 创建持仓
            position = Position(
                stock_code=signal.stock_code,
                stock_name=stock_name,
                shares=shares,
                cost_price=executed_price,
                current_price=executed_price,
                position_value=actual_amount,
                profit_loss=0.0,
                profit_loss_pct=0.0,
                open_date=datetime.strptime(t1_date, '%Y%m%d'),
                buy_date=t1_date
            )
            self.positions[signal.stock_code] = position

            # 记录交易
            trade = Trade(
                trade_id=f"{t1_date}_{signal.stock_code}_BUY",
                stock_code=signal.stock_code,
                stock_name=stock_name,
                signal_type='buy',
                price=executed_price,
                shares=shares,
                amount=actual_amount,
                timestamp=datetime.strptime(t1_date, '%Y%m%d'),
                signal_score=signal.composite_score,
                signal_date=t1_date,
                slippage=self.SLIPPAGE_RATE,
                commission=commission,
                tax=0.0
            )
            self.trades.append(trade)
            self.total_trades += 1

            logger.info(f"    [买入] {signal.stock_code} {shares}股 @ {executed_price:.2f}元 = {actual_amount:,.0f}元 (佣金:{commission:.0f})")

        except Exception as e:
            logger.error(f"    [错误] 买入失败 {signal.stock_code}: {e}")

    def _sell_position_t1(self, signal: SignalV4, t1_date: str):
        """T+1日卖出（开盘价成交）"""
        try:
            position = self.positions.get(signal.stock_code)
            if not position:
                return

            # T+1卖出限制：买入后至少持有1天
            buy_dt = datetime.strptime(position.buy_date, '%Y%m%d')
            sell_dt = datetime.strptime(t1_date, '%Y%m%d')
            hold_days = (sell_dt - buy_dt).days
            if hold_days < 1:
                logger.warning(f"    [跳过] {signal.stock_code} T+1限制，持有{hold_days}天不足1天")
                return

            # 获取T+1日数据
            t1_df = self.db.get_kline_range(signal.stock_code, t1_date, t1_date)
            if t1_df is None or len(t1_df) == 0:
                logger.warning(f"    [跳过] {signal.stock_code} T+1日无数据，无法卖出")
                return

            t1_row = t1_df.iloc[0]
            open_price = float(t1_row.get('open_price', 0))
            low_price = float(t1_row.get('low_price', 0))
            close_price = float(t1_row.get('close_price', 0))
            change_pct = float(t1_row.get('change_pct', 0))

            if open_price <= 0:
                return

            # 检查跌停：T+1日跌停无法卖出
            if change_pct <= -9.9:
                logger.warning(f"    [跳过] {signal.stock_code} T+1日跌停，无法卖出")
                return

            # 实际卖出金额（含滑点）
            executed_price = open_price * (1 - self.SLIPPAGE_RATE)
            actual_amount = position.shares * executed_price
            commission = actual_amount * self.COMMISSION_RATE
            tax = actual_amount * self.STAMP_TAX_RATE
            total_revenue = actual_amount - commission - tax

            # 更新资金
            self.cash += total_revenue

            # 计算盈亏
            profit_loss = total_revenue - (position.shares * position.cost_price)
            profit_loss_pct = (profit_loss / (position.shares * position.cost_price)) * 100 if position.cost_price > 0 else 0

            # 记录交易
            trade = Trade(
                trade_id=f"{t1_date}_{signal.stock_code}_SELL",
                stock_code=signal.stock_code,
                stock_name=position.stock_name,
                signal_type='sell',
                price=executed_price,
                shares=position.shares,
                amount=actual_amount,
                timestamp=datetime.strptime(t1_date, '%Y%m%d'),
                signal_score=signal.composite_score,
                signal_date=t1_date,
                slippage=self.SLIPPAGE_RATE,
                commission=commission,
                tax=tax
            )
            self.trades.append(trade)
            self.total_trades += 1

            # 统计盈亏
            if profit_loss > 0:
                self.winning_trades += 1
                result = "盈利"
            else:
                self.losing_trades += 1
                result = "亏损"

            logger.info(f"    [卖出] {signal.stock_code} {position.shares}股 @ {executed_price:.2f}元 = {actual_amount:,.0f}元 ({result}:{profit_loss_pct:.2f}%) 佣金:{commission:.0f} 印花税:{tax:.0f}")

            # 删除持仓
            del self.positions[signal.stock_code]

        except Exception as e:
            logger.error(f"    [错误] 卖出失败 {signal.stock_code}: {e}")

    def _update_positions(self, trade_date: str):
        """更新持仓价格（用当日收盘价）"""
        if not self.positions:
            return

        for stock_code, position in self.positions.items():
            try:
                df = self.db.get_kline_range(stock_code, trade_date, trade_date)
                if df is not None and len(df) > 0:
                    close_price = float(df.iloc[0].get('close_price', 0))
                    if close_price > 0:
                        position.current_price = close_price
                        position.position_value = position.shares * close_price
                        cost = position.shares * position.cost_price
                        position.profit_loss = position.position_value - cost
                        position.profit_loss_pct = (position.profit_loss / cost) * 100 if cost > 0 else 0
            except Exception:
                continue

    def _take_snapshot(self, trade_date: str, market_env: MarketEnvironment):
        """记录组合快照"""
        try:
            positions_value = sum(p.position_value for p in self.positions.values())
            total_value = self.cash + positions_value
            cumulative_return = ((total_value - self.initial_capital) / self.initial_capital) * 100

            daily_return = 0.0
            if self.snapshots:
                prev_value = self.snapshots[-1].total_value
                daily_return = ((total_value - prev_value) / prev_value) * 100 if prev_value > 0 else 0

            snapshot = PortfolioSnapshot(
                date=datetime.strptime(trade_date, '%Y%m%d'),
                total_value=total_value,
                cash=self.cash,
                positions=[Position(
                    stock_code=p.stock_code,
                    stock_name=p.stock_name,
                    shares=p.shares,
                    cost_price=p.cost_price,
                    current_price=p.current_price,
                    position_value=p.position_value,
                    profit_loss=p.profit_loss,
                    profit_loss_pct=p.profit_loss_pct,
                    open_date=p.open_date,
                    buy_date=p.buy_date
                ) for p in self.positions.values()],
                daily_return=daily_return,
                cumulative_return=cumulative_return,
                emotion_phase=market_env.emotion_phase.value if market_env else ''
            )
            self.snapshots.append(snapshot)
        except Exception as e:
            logger.warning(f"  [警告] 记录快照失败: {e}")

    def _calculate_results(self) -> Dict:
        """计算回测结果（修复版）"""
        if not self.snapshots:
            return {}

        final_snapshot = self.snapshots[-1]
        final_value = final_snapshot.total_value
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        # 日收益率序列
        returns = [s.daily_return for s in self.snapshots]

        # 最大回撤（修复：从净值序列正确计算）
        max_drawdown = self._calculate_max_drawdown()

        # 夏普比率（修复：年化处理 sqrt(252)）
        risk_free_rate = 3.0  # 年化无风险利率3%
        daily_risk_free = risk_free_rate / 252
        avg_daily_return = np.mean(returns)
        std_daily_return = np.std(returns)

        if std_daily_return > 0:
            sharpe_ratio = ((avg_daily_return - daily_risk_free) / std_daily_return) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0

        # 胜率（按完成的买卖配对统计，分母为已平仓交易数，而非买入+卖出总笔数）
        closed_trades = self.winning_trades + self.losing_trades
        win_rate = (self.winning_trades / closed_trades * 100) if closed_trades > 0 else 0

        # 平均盈亏（修复：正确配对计算）
        trade_profits = []
        for trade in self.trades:
            if trade.signal_type == 'sell':
                profit = self._get_trade_profit(trade)
                trade_profits.append(profit)

        winning_amounts = [p for p in trade_profits if p > 0]
        losing_amounts = [p for p in trade_profits if p < 0]

        avg_win = np.mean(winning_amounts) if winning_amounts else 0
        avg_loss = np.mean(losing_amounts) if losing_amounts else 0
        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 1.0

        return {
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'avg_daily_return': avg_daily_return,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_loss_ratio': profit_loss_ratio,
            'total_days': len(self.snapshots),
            'trades': len(self.trades),
            'snapshots': self.snapshots
        }

    def _get_trade_profit(self, trade: Trade) -> float:
        """获取交易盈亏（修复：正确配对买卖计算）"""
        if trade.signal_type != 'sell':
            return 0.0

        # 查找对应的买入交易
        buy_trade = None
        for t in reversed(self.trades):
            if t.stock_code == trade.stock_code and t.signal_type == 'buy':
                buy_trade = t
                break

        if buy_trade:
            return (trade.price - buy_trade.price) * trade.shares - trade.commission - trade.tax - buy_trade.commission
        return 0.0

    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤（修复：从净值序列正确计算）"""
        if not self.snapshots:
            return 0.0

        values = [s.total_value for s in self.snapshots]
        max_value = values[0]
        max_drawdown = 0.0

        for value in values:
            if value > max_value:
                max_value = value
            drawdown = (max_value - value) / max_value * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return max_drawdown


class BacktestReporter:
    """回测报告生成器"""

    @staticmethod
    def generate_report(results: Dict, output_file: str = 'backtest_report.md'):
        if not results:
            logger.error("[错误] 无回测结果")
            return

        report = f"""# 回测报告 - A股龙头战法选股模型v4.0

## 回测时间
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 一、总体表现

### 1.1 收益情况

| 指标 | 数值 |
|------|------|
| **初始资金** | {results.get('initial_capital', 0):,.0f}元 |
| **最终资金** | {results.get('final_value', 0):,.0f}元 |
| **总收益率** | **{results.get('total_return', 0):.2f}%** |
| **回测天数** | {results.get('total_days', 0)}天 |

### 1.2 交易统计

| 指标 | 数值 |
|------|------|
| **总交易次数** | {results.get('total_trades', 0)}次 |
| **盈利次数** | {results.get('winning_trades', 0)}次 |
| **亏损次数** | {results.get('losing_trades', 0)}次 |
| **胜率** | **{results.get('win_rate', 0):.2f}%** |

---

## 二、风险指标

### 2.1 风险控制

| 指标 | 数值 | 评级 |
|------|------|------|
| **最大回撤** | {results.get('max_drawdown', 0):.2f}% | {'优秀' if results.get('max_drawdown', 100) < 10 else '良好' if results.get('max_drawdown', 100) < 20 else '一般'} |
| **夏普比率** | {results.get('sharpe_ratio', 0):.2f} | {'优秀' if results.get('sharpe_ratio', 0) > 2 else '良好' if results.get('sharpe_ratio', 0) > 1 else '一般'} |
| **日收益波动** | {results.get('avg_daily_return', 0):.2f}% | - |

### 2.2 盈亏分析

| 指标 | 数值 |
|------|------|
| **平均盈利** | {results.get('avg_win', 0):,.0f}元 |
| **平均亏损** | {results.get('avg_loss', 0):,.0f}元 |
| **盈亏比** | {results.get('profit_loss_ratio', 0):.2f} |

---

**报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"[成功] 报告已保存到: {output_file}")
        except Exception as e:
            logger.error(f"[错误] 保存报告失败: {e}")


# ==================== 测试代码 ====================

def test_backtest():
    """测试回测框架v4.0"""
    print("\n" + "="*70)
    print("回测框架v4.0测试")
    print("="*70)

    engine = BacktestEngine(initial_capital=100000)

    # 注意：运行前需先用run_backtest.py准备历史数据
    results = engine.run_backtest('20240101', '20240131')

    if results:
        BacktestReporter.generate_report(results, 'backtest_report_v4.md')
        print(f"\n关键指标:")
        print(f"  总收益率: {results.get('total_return', 0):.2f}%")
        print(f"  胜率: {results.get('win_rate', 0):.2f}%")
        print(f"  最大回撤: {results.get('max_drawdown', 0):.2f}%")
        print(f"  夏普比率: {results.get('sharpe_ratio', 0):.2f}")
    else:
        print("\n[警告] 回测未产生结果（可能需要先运行数据准备）")


if __name__ == '__main__':
    test_backtest()
