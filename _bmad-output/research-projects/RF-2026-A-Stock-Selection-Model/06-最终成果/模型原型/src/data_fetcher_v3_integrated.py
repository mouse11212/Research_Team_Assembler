"""
集成版数据获取器 v3.0 - A股龙头战法量化系统
Integrated Data Fetcher v3.0 - Dragon Leader Strategy

核心改进：
1. 集成优化SQLite数据库（WAL模式、64MB缓存、连接池）
2. 本地缓存优先策略（减少90%API调用）
3. 自动重试机制（3次重试，间隔递增）
4. 数据自动持久化（历史K线、因子、市场情绪）
5. 字段标准化：返回英文字段名，上层无感知

设计原则：
- 先查本地缓存，缓存未命中再调用API
- API获取的数据自动存入SQLite
- 支持批量获取和存储
- 数据过期自动刷新

Version: 3.0.0
Updated: 2026-04-29
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import time
import json
import threading
from pathlib import Path

# 导入日志配置
from utils.logging_config import get_logger

logger = get_logger(__name__)

# 导入优化版数据库管理器
from core.optimized_database_manager import (
    OptimizedDatabaseManager,
    OptimizedDatabaseConfig,
    StockDataStore,
    FactorDataStore,
    MarketDataStore
)

# 字段标准化（可选，如可用则启用）
try:
    from data.data_normalizer import DataNormalizer
    _HAS_NORMALIZER = True
except Exception:
    _HAS_NORMALIZER = False

# P1 多源适配层（可选）：涨停/龙虎榜/概念 走 canonical + 主备降级
try:
    from data.multi_source_fetcher import MultiSourceDataFetcher
    _HAS_MULTI_SOURCE = True
except Exception:
    _HAS_MULTI_SOURCE = False


class RetryHelper:
    """
    重试助手类

    提供带递增间隔的重试机制
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 0.5):
        """
        初始化重试助手

        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
        """
        self.max_retries = max_retries
        self.base_delay = base_delay

    def execute_with_retry(self, func, *args, **kwargs) -> Any:
        """
        执行函数并在失败时重试

        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果
        """
        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)  # 递增延迟
                    logger.warning(f"[重试] 第{attempt + 1}次失败: {e}, {delay}秒后重试...")
                    time.sleep(delay)
                else:
                    logger.error(f"[失败] 重试{self.max_retries}次后仍然失败: {e}")
                    raise e
        return None


class IntegratedDataFetcher:
    """
    集成版数据获取器

    数据获取策略：
    1. 检查本地SQLite缓存
    2. 如果缓存存在且未过期，直接返回
    3. 如果缓存不存在或过期，从AKShare获取
    4. 将新数据存入SQLite

    数据持久化：
    - K线历史数据（保留2年）
    - 因子数据（保留1年）
    - 市场情绪数据（保留1年）
    """

    # 数据过期时间配置
    CACHE_EXPIRY = {
        'kline_daily': 24 * 60 * 60,      # 日K线：24小时过期
        'kline_intraday': 60 * 60,         # 分时数据：1小时过期
        'lhb': 24 * 60 * 60,               # 龙虎榜：24小时过期
        'sector': 4 * 60 * 60,             # 板块数据：4小时过期
        'news': 30 * 60,                   # 新闻数据：30分钟过期
        'market_emotion': 4 * 60 * 60,     # 市场情绪：4小时过期
        'factor': 24 * 60 * 60,            # 因子数据：24小时过期
        'northbound': 4 * 60 * 60,         # 北向资金：4小时过期
    }

    def __init__(self, db_path: str = "./data/stock_history.db"):
        """
        初始化集成版数据获取器

        Args:
            db_path: SQLite数据库路径
        """
        # 初始化优化版数据库管理器
        db_config = OptimizedDatabaseConfig(
            db_path=db_path,
            cache_enabled=True,
            cache_ttl=3600,
            connection_pool_size=5
        )

        self.db_manager = OptimizedDatabaseManager(db_config)
        self.retry_helper = RetryHelper(max_retries=3, base_delay=0.5)

        # 数据存储引用
        self.stock_store = self.db_manager.stock_store
        self.factor_store = self.db_manager.factor_store
        self.market_store = self.db_manager.market_store
        self.cache = self.db_manager.cache

        # 弱转强准入门槛(spec 13):gate 配置化,实例复用改进版 W2S01
        import os
        self.w2s01_gate = float(os.environ.get('QSS_W2S01_GATE', '50'))
        from factors.w2s_daily_factors import DailyW2SFactors
        self._w2s_calc = DailyW2SFactors()

        # 字段标准化器
        if _HAS_NORMALIZER:
            self.normalizer = DataNormalizer()
        else:
            self.normalizer = None

        # P1 多源适配层（涨停/龙虎榜/概念 走 canonical + 主备降级）
        if _HAS_MULTI_SOURCE:
            self.multi_source = MultiSourceDataFetcher()
        else:
            self.multi_source = None

        # 请求频率控制
        self._request_lock = threading.Lock()
        self._last_request_time = 0
        self._min_request_interval = 0.2  # 最小请求间隔（秒）

        logger.info("=" * 60)
        logger.info("[OK] 集成版数据获取器初始化成功")
        logger.info("=" * 60)
        logger.info("   - 数据源: AKShare (东方财富)")
        logger.info("   - 本地缓存: SQLite (WAL模式优化)")
        logger.info("   - 重试机制: 3次重试，间隔递增")
        logger.info("   - 请求频率控制: 最小0.2秒间隔")
        logger.info("=" * 60)

    def _rate_limit(self):
        """
        请求频率控制

        确保请求间隔不低于最小值
        """
        with self._request_lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._min_request_interval:
                time.sleep(self._min_request_interval - elapsed)
            self._last_request_time = time.time()

    def _standardize_df(self, df: pd.DataFrame, source: str = "akshare_em") -> pd.DataFrame:
        """标准化DataFrame字段名"""
        if df is None or df.empty:
            return pd.DataFrame()
        if self.normalizer is not None:
            try:
                return self.normalizer.normalize_stock_info(df, source)
            except Exception:
                pass
        # 兜底：手动映射核心字段
        col_map = {
            '代码': 'stock_code',
            '名称': 'stock_name',
            '涨跌幅': 'change_pct',
            '板块': 'sector',
            '行业': 'sector',
        }
        df = df.copy()
        for cn, en in col_map.items():
            if cn in df.columns and en not in df.columns:
                df[en] = df[cn]
        return df

    # ==================== DataSource Protocol 实现 ====================

    def get_stock_data(self, stock_code: str, trade_date: str, **kwargs) -> Optional[pd.DataFrame]:
        """
        获取单只股票的日线数据

        Args:
            stock_code: 股票代码
            trade_date: 交易日期（YYYYMMDD）

        Returns:
            日线数据DataFrame
        """
        # 优先从本地获取
        df = self.stock_store.get_kline_history(stock_code, days=1)
        if df is not None and not df.empty:
            if str(df.iloc[0].get('trade_date', '')) == trade_date:
                return df

        # 从API获取
        self._rate_limit()
        try:
            df = self.retry_helper.execute_with_retry(
                ak.stock_zh_a_hist,
                symbol=stock_code,
                period="daily",
                start_date=trade_date,
                end_date=trade_date,
                adjust="qfq"
            )
            if df is not None and not df.empty:
                df = self._standardize_df(df, 'akshare_em')
                return df
        except Exception as e:
            logger.error(f"[错误] 获取股票数据失败 {stock_code} {trade_date}: {e}")
        return None

    def ensure_kline_history(self, stock_code: str, days: int = 5) -> pd.DataFrame:
        """
        确保SQLite中有指定天数的K线历史，不足时从AKShare补全

        Args:
            stock_code: 股票代码
            days: 需要保证的K线天数

        Returns:
            K线DataFrame（按trade_date升序）
        """
        # 1. 先查本地
        local_df = self.stock_store.get_kline_history(stock_code, days=days)
        local_count = len(local_df) if local_df is not None else 0

        if local_count >= days:
            return local_df.sort_values('trade_date')

        # 2. 本地不足，计算需要补充的日期范围
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime('%Y%m%d')

        logger.info(f"[数据补全] {stock_code} 本地K线仅{local_count}天，从AKShare补全 {start_date}-{end_date}")

        try:
            self._rate_limit()
            df = self.retry_helper.execute_with_retry(
                ak.stock_zh_a_hist,
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )

            if df is not None and not df.empty:
                # 标准化并保存到SQLite
                batch_data = []
                for _, row in df.iterrows():
                    batch_data.append({
                        'stock_code': stock_code,
                        'trade_date': str(row.get('日期', '')).replace('-', ''),
                        'open_price': row.get('开盘', 0),
                        'close_price': row.get('收盘', 0),
                        'high_price': row.get('最高', 0),
                        'low_price': row.get('最低', 0),
                        'volume': row.get('成交量', 0),
                        'amount': row.get('成交额', 0),
                        'change_pct': row.get('涨跌幅', 0),
                        'turnover_rate': row.get('换手率', 0),
                    })
                if batch_data:
                    self.stock_store.save_kline_batch(batch_data)

                # 重新查询本地（确保数据已写入）
                local_df = self.stock_store.get_kline_history(stock_code, days=days)
                if local_df is not None and len(local_df) >= 2:
                    return local_df.sort_values('trade_date')
        except Exception as e:
            logger.warning(f"[警告] 补全K线历史失败 {stock_code}: {e}")

        # 3. 返回本地已有数据（可能仍不足）
        if local_df is not None and not local_df.empty:
            return local_df.sort_values('trade_date')
        return pd.DataFrame()

    def get_active_stocks_from_history(self, trade_date: str, min_change_pct: float = 5.0,
                                       top_n: int = 50, **kwargs) -> Optional[pd.DataFrame]:
        """
        基于历史K线数据反推指定日期的活跃股票池

        实现逻辑：
        1. 优先检查本地SQLite缓存（stock_kline表）
        2. 本地不足时，批量请求AKShare历史K线（stock_zh_a_hist）
        3. 将结果写入本地SQLite，避免重复请求

        Args:
            trade_date: 交易日期（YYYYMMDD）
            min_change_pct: 最小涨幅阈值
            top_n: 最大返回数量

        Returns:
            活跃股票列表DataFrame
        """
        logger.info(f"[数据获取] 从历史K线反推活跃股票（日期={trade_date}）")

        # 1. 检查本地缓存
        local_df = self.stock_store.get_all_stocks_kline(trade_date)
        local_count = len(local_df) if local_df is not None else 0
        if local_df is not None and local_count >= 3000:
            logger.info(f"[缓存命中] 本地已有 {local_count} 只股票的 {trade_date} 数据")
            return self._filter_active_from_kline(local_df, trade_date, min_change_pct, top_n)

        # 2. 本地数据足够覆盖 top_n 时优先使用（降级策略）
        if local_count >= top_n:
            logger.info(f"[缓存命中] 本地有 {local_count} 只股票，满足 top_n={top_n}，直接使用")
            return self._filter_active_from_kline(local_df, trade_date, min_change_pct, top_n)

        # 3. 本地不足，从API批量获取
        logger.info(f"[API获取] 本地数据不足（{local_count} 只），开始批量请求AKShare")

        # 获取全市场代码列表
        self._rate_limit()
        try:
            spot_df = self.retry_helper.execute_with_retry(ak.stock_zh_a_spot_em)
        except Exception as e:
            logger.error(f"[错误] 获取全市场代码列表失败: {e}")
            # AKShare不可用时的降级：如果本地有任何数据，直接使用
            if local_count > 0:
                logger.warning(f"[降级] AKShare不可用，使用本地已有的 {local_count} 只股票数据")
                return self._filter_active_from_kline(local_df, trade_date, min_change_pct, top_n)
            return pd.DataFrame()

        if spot_df is None or spot_df.empty:
            return pd.DataFrame()

        # 提取代码列表
        code_col = '代码' if '代码' in spot_df.columns else 'stock_code'
        codes = spot_df[code_col].astype(str).tolist()
        logger.info(f"全市场共 {len(codes)} 只股票，开始批量获取 {trade_date} 历史K线（并发5线程，约0.2s/只）...")

        # 批量获取历史K线（线程池并发，遵守_rate_limit）
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def fetch_one(code: str) -> dict:
            try:
                self._rate_limit()
                df_hist = self.retry_helper.execute_with_retry(
                    ak.stock_zh_a_hist,
                    symbol=code,
                    period="daily",
                    start_date=trade_date,
                    end_date=trade_date,
                    adjust="qfq"
                )
                if df_hist is not None and not df_hist.empty:
                    row = df_hist.iloc[0]
                    return {
                        'stock_code': code,
                        'change_pct': float(row.get('涨跌幅', 0)),
                        'volume': int(row.get('成交量', 0)),
                    }
            except Exception:
                pass
            return None

        results = []
        max_workers = 5
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, code): code for code in codes}
            completed = 0
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                if result:
                    results.append(result)
                if completed % 500 == 0:
                    logger.info(f"  进度: {completed}/{len(codes)}，已获取 {len(results)} 条有效数据")

        if not results:
            logger.warning(f"[警告] 未获取到 {trade_date} 的任何历史K线数据")
            return pd.DataFrame()

        logger.info(f"[API完成] 共获取 {len(results)} 只股票的 {trade_date} 历史K线")

        # 3. 保存到本地SQLite
        batch_data = []
        for r in results:
            batch_data.append({
                'stock_code': r['stock_code'],
                'trade_date': trade_date,
                'change_pct': r['change_pct'],
                'volume': r['volume'],
                'open_price': 0,
                'close_price': 0,
                'high_price': 0,
                'low_price': 0,
                'amount': 0,
            })
        saved = self.stock_store.save_kline_batch(batch_data)
        logger.info(f"[持久化] 保存 {saved} 条 {trade_date} K线数据到SQLite")

        # 4. 筛选活跃股票
        df = pd.DataFrame(results)
        return self._filter_active_from_kline(df, trade_date, min_change_pct, top_n)

    def _filter_active_from_kline(self, df: pd.DataFrame, trade_date: str,
                                  min_change_pct: float, top_n: int) -> pd.DataFrame:
        """从K线DataFrame中筛选活跃股票"""
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()
        df['change_pct'] = pd.to_numeric(df.get('change_pct', 0), errors='coerce')
        df = df.dropna(subset=['change_pct'])

        # C-Lite（活跃池方案C-Lite，2026-06-18）：用"本地三维龙头强度"排序替代原"绝对涨幅"排序。
        # 原 sort_values('change_pct') 致 20% 涨停的创业板霸占 top_n、主板 10% 涨停永不入池
        # （见 07-改进建议/10）。三维 = 归一化涨幅(0.5) + 换手率(0.25) + 量比(0.25)，跨板块可比。
        candidates = df[df['change_pct'] >= min_change_pct].copy()
        if candidates.empty:
            return pd.DataFrame()
        # 弱转强准入门槛(spec 13):涨幅≥5% AND W2S01≥gate 才进入排序
        candidates = self._filter_by_w2s01_gate(candidates, trade_date, self.w2s01_gate)
        if candidates is None or candidates.empty:
            return pd.DataFrame()
        active_df = self._rank_by_leader_strength(candidates, trade_date).head(top_n)

        if 'stock_name' not in active_df.columns:
            active_df = active_df.copy()
            active_df['stock_name'] = active_df['stock_code']
        if 'sector' not in active_df.columns:
            active_df = active_df.copy()
            active_df['sector'] = 'unknown'

        logger.info(f"[成功] 找到 {len(active_df)} 只活跃股票（{trade_date}）")
        return active_df

    @staticmethod
    def _limit_cap(code: str) -> float:
        """按代码前缀判定单日涨停幅度上限（%）。用于归一化涨幅，使跨板块可比。"""
        c = str(code)
        if c.startswith(('8', '4')):
            return 30.0  # 北交所 ±30%
        if c.startswith(('300', '301', '688', '689')):
            return 20.0  # 创业板 / 科创板 ±20%
        return 10.0  # 主板 ±10%（ST ±5% 仅凭代码无法精确判定，保守按主板，宁可低估不误排）

    def _compute_volume_ratio(self, active_df: pd.DataFrame, trade_date: str) -> pd.Series:
        """量比 = 当日成交量 / 过去5日均量（不含当日）。纯本地查询；缺历史或缺量→1.0（中性）。"""
        import sqlite3
        db = getattr(self.stock_store, 'db_path', None) or getattr(self, 'db_path', None)
        today_vol = dict(zip(
            active_df['stock_code'],
            pd.to_numeric(active_df.get('volume', 0), errors='coerce').fillna(0)))
        ratios = {}
        if db:
            conn = sqlite3.connect(db)
            conn.execute('PRAGMA busy_timeout=8000')
            try:
                for code in active_df['stock_code']:
                    rows = conn.execute(
                        "SELECT volume FROM stock_kline WHERE stock_code=? AND trade_date<? "
                        "ORDER BY trade_date DESC LIMIT 5", (code, trade_date)).fetchall()
                    vols = [r[0] for r in rows if r[0]]
                    tv = today_vol.get(code, 0)
                    ratios[code] = (tv / (sum(vols) / len(vols))) if (vols and tv) else 1.0
            finally:
                conn.close()
        return active_df['stock_code'].map(lambda c: ratios.get(c, 1.0))

    def _filter_by_w2s01_gate(self, candidates, trade_date, gate):
        """弱转强准入门槛:保留 W2S01>=gate 的候选(保序)。
        窗口不足(<L+1)/ W2S01 为 None / 单票查询失败 → 剔除;整库无路径 → 跳过门槛。
        仿 _compute_volume_ratio 的 sqlite 直连逐票取数。"""
        import sqlite3
        if candidates is None or len(candidates) == 0:
            return candidates
        L = self._w2s_calc.lookback_L
        db = getattr(self.stock_store, 'db_path', None) or getattr(self, 'db_path', None)
        if not db:
            logger.warning("[W2S01门槛] 无数据库路径,跳过门槛")
            return candidates
        keep = []
        conn = sqlite3.connect(db)
        conn.execute('PRAGMA busy_timeout=8000')
        try:
            for code in candidates['stock_code']:
                try:
                    rows = conn.execute(
                        "SELECT close_price,volume,ma20,ma5,change_pct FROM stock_kline "
                        "WHERE stock_code=? AND trade_date<=? ORDER BY trade_date DESC LIMIT ?",
                        (code, trade_date, L + 1)).fetchall()
                except Exception:
                    continue  # 单票查询失败 → 剔除
                if len(rows) < L + 1:
                    continue  # 窗口不足 → 剔除
                rows = rows[::-1]  # oldest→newest
                today = rows[-1]
                window = [{'close': r[0], 'volume': r[1], 'ma20': r[2]} for r in rows[:-1]]
                td = {'change_pct': today[4], 'volume': today[1], 'close': today[0],
                      'ma5': today[3], 'window_klines': window}
                w = self._w2s_calc.calculate_W2S01(td, {})
                if w is not None and w >= gate:
                    keep.append(code)
        finally:
            conn.close()
        before = len(candidates)
        out = candidates[candidates['stock_code'].isin(keep)].copy()
        logger.info(f"[W2S01门槛] gate={gate} 候选 {before}→{len(out)} 只(剔除非弱转强 {before - len(out)})")
        if len(out) == 0:
            logger.warning(f"[W2S01门槛] {trade_date} 门槛后无候选(无 W2S01≥{gate} 的弱转强票)")
        return out

    def _rank_by_leader_strength(self, active_df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
        """
        C-Lite 本地三维龙头强度排序（方案C-Lite，2026-06-18）。

        综合分 = 0.5×归一化涨幅 + 0.25×换手率 + 0.25×量比（后两维截面 min-max 归一化使可比）。
        归一化涨幅 = change_pct / 板块涨停上限 → 主板+10%一字板(=1.0) 与创业板+20%(=1.0) 等价竞争，
        从根上消除"按绝对涨幅 top_n 致创业板垄断"。换手率/量比提供跨板块量能区分度。
        降级：API 路径无 turnover_rate 时该维退化为 0（_mm 全0），不报错。
        """
        a = active_df.copy()
        # ① 归一化涨幅（0-1，封顶1）—— 主导维度
        a['_norm_chg'] = (pd.to_numeric(a['change_pct'], errors='coerce')
                          / a['stock_code'].map(self._limit_cap)).clip(upper=1.0).fillna(0)
        # ② 换手率（本地，截面 min-max）
        tr = pd.to_numeric(a.get('turnover_rate', 0), errors='coerce').fillna(0)
        # ③ 量比（当日量/过去5日均量，截面 min-max）
        vr = pd.to_numeric(self._compute_volume_ratio(a, trade_date), errors='coerce').fillna(1.0)

        def _mm(s: pd.Series) -> pd.Series:
            rng = s.max() - s.min()
            return (s - s.min()) / rng if rng > 0 else pd.Series(0.0, index=s.index)

        # 三维权重可配（环境变量）。默认 0.6/0.2/0.2 —— 经三区间调参寻优(2026-06-18)确定：
        # 跨 0101-0331/0401-0531/1101-0615 要么更优要么持平，长区间(71笔)盈亏比 2.37→2.66、夏普 1.67→1.94。
        import os
        w_chg = float(os.environ.get('QSS_LEADER_W_CHG', 0.6))
        w_tr = float(os.environ.get('QSS_LEADER_W_TR', 0.2))
        w_vr = float(os.environ.get('QSS_LEADER_W_VR', 0.2))
        a['_leader_score'] = w_chg * a['_norm_chg'] + w_tr * _mm(tr) + w_vr * _mm(vr)

        # 板块偏好（资金门槛适配，2026-06-18）：账户达不到创业板10万/科创板·北交所50万门槛时，
        # 选股优先沪深主板、创业板降权"保持关注"、科创板(688/689)与北交所(8/4)剔除（买不了，
        # 选入会高估可执行收益）。系数可配(环境变量)，资金门槛达标后调高即可放开。
        pref_main = float(os.environ.get('QSS_BOARD_MAIN', 1.0))     # 沪深主板(60/00) 优先
        pref_cnext = float(os.environ.get('QSS_BOARD_CHINEXT', 0.5))  # 创业板(30/31) 降权保持关注
        pref_star = float(os.environ.get('QSS_BOARD_STAR', 0.0))     # 科创板(688/689) 50万门槛→剔除
        pref_bse = float(os.environ.get('QSS_BOARD_BSE', 0.0))       # 北交所(8/4) 50万门槛→剔除

        def _board_pref(code: str) -> float:
            c = str(code)
            if c.startswith(('300', '301')):
                return pref_cnext
            if c.startswith(('688', '689')):
                return pref_star
            if c.startswith(('8', '4')):
                return pref_bse
            return pref_main

        bp = a['stock_code'].map(_board_pref)
        a['_leader_score'] = a['_leader_score'] * bp
        a = a[bp > 0]  # 系数为0的板块（达不到资金门槛、买不了）直接剔除
        return a.sort_values('_leader_score', ascending=False)

    def get_active_stocks(self, trade_date: str, min_change_pct: float = 5.0,
                          top_n: int = 50, **kwargs) -> Optional[pd.DataFrame]:
        """
        获取活跃股票池（涨幅超过阈值的股票）

        支持实时数据与历史日期反推：
        - trade_date == today：使用 stock_zh_a_spot_em() 获取实时数据
        - trade_date != today：使用 get_active_stocks_from_history() 基于历史K线反推

        Args:
            trade_date: 交易日期
            min_change_pct: 最小涨幅阈值（默认5%）
            top_n: 最大返回数量

        Returns:
            活跃股票列表DataFrame，包含 stock_code, stock_name, change_pct 等英文字段
        """
        logger.info(f"[数据获取] 开始扫描活跃股票（涨幅>{min_change_pct}%）")

        today = datetime.now().strftime('%Y%m%d')
        if trade_date and trade_date != today:
            return self.get_active_stocks_from_history(trade_date, min_change_pct, top_n, **kwargs)

        # 获取全市场数据
        self._rate_limit()
        try:
            df = self.retry_helper.execute_with_retry(ak.stock_zh_a_spot_em)
        except Exception as e:
            logger.error(f"[错误] 获取全市场数据失败: {e}")
            # AKShare不可用时的降级：尝试使用本地今日数据
            local_df = self.stock_store.get_all_stocks_kline(today)
            if local_df is not None and len(local_df) > 0:
                logger.warning(f"[降级] AKShare不可用，使用本地已有的 {len(local_df)} 只今日数据")
                return self._filter_active_from_kline(local_df, trade_date, min_change_pct, top_n)
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # 字段标准化
        df = self._standardize_df(df, 'akshare_em')

        # 确保 change_pct 是数值类型
        if 'change_pct' not in df.columns:
            logger.warning("[警告] change_pct 列缺失，返回空结果")
            return pd.DataFrame()
        df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')
        df = df.dropna(subset=['change_pct'])

        # 筛选活跃股票
        active_df = df[df['change_pct'] >= min_change_pct].head(top_n)

        # 补充 sector 字段（如果缺失）
        if 'sector' not in active_df.columns:
            active_df = active_df.copy()
            active_df['sector'] = 'unknown'

        # 将今日实时数据保存到 stock_kline，供后续因子计算使用
        try:
            batch_data = []
            for _, row in df.iterrows():
                code = str(row.get('stock_code', ''))
                if not code:
                    continue
                batch_data.append({
                    'stock_code': code,
                    'trade_date': today,
                    'open_price': row.get('open', row.get('今开', 0)),
                    'close_price': row.get('close', row.get('最新价', 0)),
                    'high_price': row.get('high', row.get('最高', 0)),
                    'low_price': row.get('low', row.get('最低', 0)),
                    'volume': row.get('volume', row.get('成交量', 0)),
                    'amount': row.get('amount', row.get('成交额', 0)),
                    'change_pct': row.get('change_pct', 0),
                    'turnover_rate': row.get('turnover_rate', row.get('换手率', 0)),
                })
            if batch_data:
                saved = self.stock_store.save_kline_batch(batch_data)
                logger.info(f"[持久化] 保存{saved}条今日K线到SQLite")
        except Exception as e:
            logger.warning(f"[警告] 保存今日K线失败: {e}")

        logger.info(f"[成功] 找到{len(active_df)}只活跃股票")
        return active_df

    def get_market_data(self, trade_date: str, **kwargs) -> Dict[str, Any]:
        """
        获取市场整体数据（指数、板块等）

        Args:
            trade_date: 交易日期

        Returns:
            市场数据字典
        """
        return {
            'trade_date': trade_date,
            'index_change': 0.0,
            'limit_up_count': 50,
        }

    def save_stock_data(self, stock_code: str, trade_date: str,
                        data: pd.DataFrame, **kwargs) -> bool:
        """
        存储股票数据到本地

        Args:
            stock_code: 股票代码
            trade_date: 交易日期
            data: 日线数据

        Returns:
            是否存储成功
        """
        if data is None or data.empty:
            return False
        try:
            batch_data = []
            for _, row in data.iterrows():
                batch_data.append({
                    'stock_code': stock_code,
                    'trade_date': trade_date,
                    'open_price': row.get('open', row.get('open_price', 0)),
                    'close_price': row.get('close', row.get('close_price', 0)),
                    'high_price': row.get('high', row.get('high_price', 0)),
                    'low_price': row.get('low', row.get('low_price', 0)),
                    'volume': row.get('volume', 0),
                    'amount': row.get('amount', 0),
                    'change_pct': row.get('change_pct', 0),
                })
            saved = self.stock_store.save_kline_batch(batch_data)
            return saved > 0
        except Exception as e:
            logger.error(f"[错误] 保存股票数据失败: {e}")
            return False

    def save_factors(self, stock_code: str, trade_date: str,
                     factors: Dict[str, float], **kwargs) -> bool:
        """
        保存因子计算结果

        Args:
            stock_code: 股票代码
            trade_date: 交易日期
            factors: 因子字典（31因子）

        Returns:
            是否存储成功
        """
        # 1. 存入内存缓存
        if self.cache:
            self.cache.set_factor_cache(stock_code, trade_date, factors)

        # 2. 存入SQLite
        success = self.factor_store.save_stock_factors(stock_code, trade_date, factors)

        if success:
            logger.info(f"[持久化] {stock_code} {trade_date} 因子数据已保存")

        return success

    def get_factors_history(self, stock_code: str, days: int = 60,
                            **kwargs) -> Optional[pd.DataFrame]:
        """
        获取因子历史数据

        Args:
            stock_code: 股票代码
            days: 回溯天数

        Returns:
            因子历史DataFrame
        """
        try:
            # 获取所有因子历史（通过 factor_store 的 get_all_factors_by_date 不够细粒度，
            # 这里返回一个综合 DataFrame）
            all_factors = {}
            for i in range(1, 7):
                for prefix in ['A', 'L', 'W2S', 'S2W', 'G']:
                    if prefix == 'L' and i > 7:
                        continue
                    factor_id = f"{prefix}{str(i).zfill(3)}"
                    if prefix == 'W2S' or prefix == 'S2W':
                        factor_id = f"{prefix}{str(i).zfill(2)}"
                    elif prefix in ['A', 'L', 'G']:
                        factor_id = f"{prefix}{str(i).zfill(3)}"
                    # 简化：只查几个核心因子
                    if factor_id in ['A001', 'L001', 'W2S01', 'S2W01', 'G001']:
                        df = self.factor_store.get_factor_history(stock_code, factor_id, days)
                        if not df.empty:
                            all_factors[factor_id] = df
            if all_factors:
                return pd.concat(all_factors.values(), ignore_index=True)
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"[错误] 获取因子历史失败: {e}")
            return None

    def get_latest_icir(self) -> Dict[str, float]:
        """
        读 ic_history 最新交易日的 {factor_id: icir_value}（断点1接线：IC加权守卫用）。

        由 data/compute_ic_history.py 离线计算落库。signal_generator 据此判断是否启用 IC 加权
        （样本不足时回落默认权重）。纯本地读，无前视（IC 基于历史因子值×已实现未来收益）。
        """
        try:
            import sqlite3
            db = getattr(self.stock_store, 'db_path', None) or getattr(self, 'db_path', None)
            if not db:
                return {}
            conn = sqlite3.connect(db)
            try:
                row = conn.execute("SELECT MAX(trade_date) FROM ic_history").fetchone()
                if not row or not row[0]:
                    return {}
                latest = row[0]
                rows = conn.execute(
                    "SELECT factor_id, icir_value FROM ic_history WHERE trade_date=?", (latest,)
                ).fetchall()
                return {r[0]: r[1] for r in rows if r[1] is not None}
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[IC] 读取 ic_history 失败: {e}")
            return {}

    def save_market_emotion(self, trade_date: str, emotion_data: Dict[str, Any],
                            **kwargs) -> bool:
        """
        存储市场情绪数据

        Args:
            trade_date: 交易日期
            emotion_data: 情绪数据字典

        Returns:
            是否存储成功
        """
        success = self.market_store.save_market_emotion(trade_date, emotion_data)

        if success:
            logger.info(f"[持久化] {trade_date} 市场情绪数据已保存")

        return success

    def get_data_stats(self) -> Dict[str, Any]:
        """
        获取数据统计信息

        Returns:
            统计信息字典（缓存命中率、数据量等）
        """
        return self.db_manager.get_database_stats()

    def close(self) -> None:
        """
        关闭数据源连接

        释放资源，关闭数据库连接等
        """
        self.db_manager.close()
        logger.info("[关闭] 数据库连接已关闭")

    # ==================== 扩展方法（兼容旧调用） ====================

    def get_stock_kline(self, stock_code: str, trade_date: str,
                        force_refresh: bool = False) -> Dict:
        """
        获取股票K线数据（本地缓存优先）

        Args:
            stock_code: 股票代码
            trade_date: 交易日期
            force_refresh: 是否强制刷新

        Returns:
            K线数据字典
        """
        df = self.get_stock_data(stock_code, trade_date)
        if df is not None and not df.empty:
            row = df.iloc[-1]
            return {
                'stock_code': stock_code,
                'trade_date': trade_date,
                'open': row.get('open', row.get('open_price', 0)),
                'close': row.get('close', row.get('close_price', 0)),
                'high': row.get('high', row.get('high_price', 0)),
                'low': row.get('low', row.get('low_price', 0)),
                'volume': row.get('volume', 0),
                'amount': row.get('amount', 0),
                'change_pct': row.get('change_pct', 0),
                'source': 'api' if force_refresh else 'cache'
            }
        return {}

    def get_stock_kline_history(self, stock_code: str, days: int = 60,
                                 force_refresh: bool = False) -> pd.DataFrame:
        """
        获取股票K线历史数据（本地缓存优先）

        Args:
            stock_code: 股票代码
            days: 回溯天数
            force_refresh: 是否强制刷新

        Returns:
            K线历史DataFrame
        """
        # 1. 检查本地缓存
        if not force_refresh:
            kline_df = self.stock_store.get_kline_history(stock_code, days)
            if len(kline_df) >= days * 0.8:  # 允许80%覆盖率
                logger.info(f"[缓存命中] {stock_code} {len(kline_df)}条K线历史")
                return kline_df

        # 2. 从AKShare获取历史数据
        logger.info(f"[API获取] {stock_code} {days}天K线历史")
        self._rate_limit()

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime('%Y%m%d')

        try:
            df = self.retry_helper.execute_with_retry(
                ak.stock_zh_a_hist,
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )

            if df is not None and len(df) > 0:
                # 计算均线
                close_col = '收盘' if '收盘' in df.columns else 'close'
                df['ma5'] = df[close_col].rolling(5).mean()
                df['ma10'] = df[close_col].rolling(10).mean()
                df['ma20'] = df[close_col].rolling(20).mean()
                df['ma60'] = df[close_col].rolling(60).mean()

                # 3. 批量存入SQLite
                batch_data = []
                for _, row in df.iterrows():
                    date_val = row.get('日期', row.get('trade_date', ''))
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y%m%d')
                    else:
                        date_str = str(date_val).replace('-', '')

                    batch_data.append({
                        'stock_code': stock_code,
                        'trade_date': date_str,
                        'open_price': row.get('开盘', row.get('open', 0)),
                        'close_price': row.get('收盘', row.get('close', 0)),
                        'high_price': row.get('最高', row.get('high', 0)),
                        'low_price': row.get('最低', row.get('low', 0)),
                        'volume': row.get('成交量', row.get('volume', 0)),
                        'amount': row.get('成交额', row.get('amount', 0)),
                        'change_pct': row.get('涨跌幅', row.get('change_pct', 0)),
                        'ma5': row.get('ma5', 0),
                        'ma10': row.get('ma10', 0),
                        'ma20': row.get('ma20', 0),
                        'ma60': row.get('ma60', 0)
                    })

                saved = self.stock_store.save_kline_batch(batch_data)
                logger.info(f"[持久化] 保存{saved}条K线数据到SQLite")

                return df.tail(days)

        except Exception as e:
            logger.error(f"[错误] 获取K线历史失败: {e}")

        return pd.DataFrame()

    def get_all_stocks_daily_kline(self, trade_date: str,
                                    force_refresh: bool = False) -> pd.DataFrame:
        """
        获取所有股票的日线数据

        Args:
            trade_date: 交易日期
            force_refresh: 是否强制刷新

        Returns:
            所有股票K线DataFrame
        """
        # 1. 检查本地缓存
        if not force_refresh:
            df = self.stock_store.get_all_stocks_kline(trade_date)
            if len(df) > 100:
                logger.info(f"[缓存命中] {trade_date} {len(df)}只股票K线")
                return df

        # 2. 从AKShare获取全市场数据
        logger.info(f"[API获取] {trade_date} 全市场股票数据")
        self._rate_limit()

        try:
            df = self.retry_helper.execute_with_retry(
                ak.stock_zh_a_spot_em
            )

            if df is not None and len(df) > 0:
                # 标准化字段
                df = self._standardize_df(df, 'akshare_em')

                # 3. 批量存入SQLite
                batch_data = []
                for _, row in df.iterrows():
                    stock_code = str(row.get('stock_code', ''))
                    if not stock_code:
                        continue

                    batch_data.append({
                        'stock_code': stock_code,
                        'trade_date': trade_date,
                        'open_price': row.get('open', row.get('今开', 0)),
                        'close_price': row.get('close', row.get('最新价', 0)),
                        'high_price': row.get('high', row.get('最高', 0)),
                        'low_price': row.get('low', row.get('最低', 0)),
                        'volume': row.get('volume', row.get('成交量', 0)),
                        'amount': row.get('amount', row.get('成交额', 0)),
                        'change_pct': row.get('change_pct', row.get('涨跌幅', 0)),
                    })

                saved = self.stock_store.save_kline_batch(batch_data)
                logger.info(f"[持久化] 保存{saved}条股票数据到SQLite")

                return df

        except Exception as e:
            logger.error(f"[错误] 获取全市场数据失败: {e}")

        return pd.DataFrame()

    def get_lhb_data(self, trade_date: str,
                     force_refresh: bool = False) -> pd.DataFrame:
        """
        获取龙虎榜数据（本地缓存优先）

        Args:
            trade_date: 交易日期
            force_refresh: 是否强制刷新

        Returns:
            龙虎榜DataFrame
        """
        logger.info(f"[API获取] 龙虎榜数据 {trade_date}")

        # 优先走 P1 适配层：新浪(上榜清单)为主 + 问财(买卖额)富化，绕开被封的 eastmoney
        if self.multi_source is not None:
            try:
                canon = self.multi_source.fetch_dragon_tiger_with_fallback(trade_date)
                if canon is not None and len(canon) > 0:
                    # 契约兼容：补 stock_name 别名(旧上层可能读 stock_name)
                    if 'stock_name' not in canon.columns and 'name' in canon.columns:
                        canon['stock_name'] = canon['name']
                    logger.info(f"[成功] 龙虎榜(适配层) {len(canon)}条，来源={self.multi_source.p1_stats.get('dragon_tiger')}")
                    return canon
                logger.info("[适配层] 龙虎榜空，回退 eastmoney 兜底")
            except Exception as e:
                logger.warning(f"[适配层] 龙虎榜失败，回退 eastmoney: {e}")

        # 兜底：原 eastmoney 路径（封锁期通常失败，保留以兼容解封后）
        self._rate_limit()
        try:
            df = self.retry_helper.execute_with_retry(
                ak.stock_lhb_detail_em,
                start_date=trade_date,
                end_date=trade_date
            )
            if df is not None and len(df) > 0:
                logger.info(f"[成功] 获取到{len(df)}条龙虎榜数据(eastmoney)")
                if '代码' in df.columns and 'stock_code' not in df.columns:
                    df['stock_code'] = df['代码'].astype(str)
                if '名称' in df.columns and 'stock_name' not in df.columns:
                    df['stock_name'] = df['名称']
                if '买入额' in df.columns and '卖出额' in df.columns:
                    df['net_buy'] = df['买入额'] - df['卖出额']
                return df
        except Exception as e:
            logger.warning(f"[警告] 龙虎榜 eastmoney 兜底也失败（可能是非交易日/封锁）: {e}")

        return pd.DataFrame()

    def get_limit_up_pool(self, trade_date: str) -> pd.DataFrame:
        """获取涨停池(canonical)——P1 新增，补 A001/A002/A004 因子。

        走适配层：pywencai 主源(今日涨停)，腾讯兜底(占位)。绕开被封的 eastmoney。
        返回 canonical(StandardLimitUp 列)，绝不伪造缺失字段(Fail-Loud)。
        """
        logger.info(f"[API获取] 涨停池 {trade_date}")
        if self.multi_source is not None:
            try:
                canon = self.multi_source.fetch_limit_up_with_fallback(trade_date)
                if canon is not None and len(canon) > 0:
                    logger.info(f"[成功] 涨停池(适配层) {len(canon)}只，来源={self.multi_source.p1_stats.get('limit_up')}")
                    return canon
            except Exception as e:
                logger.warning(f"[适配层] 涨停池失败: {e}")
        return pd.DataFrame()

    def get_concept_members(self, concept_name: str) -> pd.DataFrame:
        """获取单个概念的成分股(canonical membership)——P1 新增，补 W2S06。

        走适配层：pywencai '概念→成分股' 方向。返回 (stock_code, concept_name, source) 多对多行。
        概念清单可由 self.multi_source.fetch_concept_catalog() 取(同花顺 ths)。
        """
        if self.multi_source is not None:
            try:
                return self.multi_source.fetch_concept_members(concept_name)
            except Exception as e:
                logger.warning(f"[适配层] 概念成分 {concept_name} 失败: {e}")
        return pd.DataFrame()

    def get_market_limit_up_history(self, end_date: str, days: int = 60) -> List[float]:
        """获取市场级"每日涨停家数"历史(用于 A001 分母)——纯本地 DB，无新数据源。

        口径与 market_env 一致(change_pct >= 9.9)；返回 end_date 之前 days 个交易日的
        涨停家数列表(按日期倒序)。注意：9.9 阈值会把创业板/科创板未达20%涨停的高涨幅股
        也计入，属与 market_env 一致的已知近似。
        """
        import sqlite3
        try:
            conn = sqlite3.connect(self.stock_store.db_path)
            try:
                rows = conn.execute(
                    "SELECT trade_date, COUNT(*) AS n FROM stock_kline "
                    "WHERE change_pct >= 9.9 AND trade_date < ? "
                    "GROUP BY trade_date ORDER BY trade_date DESC LIMIT ?",
                    (str(end_date), int(days))
                ).fetchall()
            finally:
                conn.close()
            counts = [float(r[1]) for r in rows]
            logger.info(f"[数据获取] 市场涨停历史(<{end_date}, {len(counts)}日): "
                        f"均值{(sum(counts)/len(counts)):.1f}" if counts else
                        f"[数据获取] 市场涨停历史(<{end_date}): 空")
            return counts
        except Exception as e:
            logger.warning(f"[警告] 市场涨停历史查询失败: {e}")
            return []

    def get_sector_activity(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        获取板块活跃度

        Args:
            force_refresh: 是否强制刷新

        Returns:
            板块活跃度DataFrame
        """
        logger.info(f"[数据获取] 开始获取板块数据")

        # P1：优先用同花顺行业概览(1次调用拿~90个行业的涨跌幅，绕开被封的 eastmoney
        # 及其逐板块 30 次调用)。供 A002 板块扩散度。
        try:
            s = self.retry_helper.execute_with_retry(ak.stock_board_industry_summary_ths)
            if s is not None and len(s) > 0 and '涨跌幅' in s.columns:
                name_col = '板块' if '板块' in s.columns else s.columns[1]
                out = pd.DataFrame({
                    'sector': s[name_col].astype(str),
                    'change_pct': pd.to_numeric(s['涨跌幅'], errors='coerce'),
                }).dropna(subset=['change_pct'])
                if len(out) > 0:
                    logger.info(f"[数据获取] 板块概览(同花顺) {len(out)}个行业")
                    return out
        except Exception as e:
            logger.warning(f"[适配层] 同花顺板块概览失败，回退 eastmoney: {e}")

        # 兜底：原 eastmoney 路径（封锁期通常失败，保留以兼容解封后）
        self._rate_limit()

        try:
            df = self.retry_helper.execute_with_retry(
                ak.stock_board_industry_name_em
            )

            if df is None or len(df) == 0:
                return pd.DataFrame()

            # 获取板块涨跌幅（只取前30个）
            sector_data = []
            for _, row in df.head(30).iterrows():
                try:
                    sector_name = row['板块名称']
                    self._rate_limit()

                    sector_df = self.retry_helper.execute_with_retry(
                        ak.stock_board_industry_spot_em,
                        symbol=sector_name
                    )

                    if sector_df is not None and len(sector_df) > 0:
                        latest = sector_df.iloc[0]
                        sector_data.append({
                            'sector': sector_name,
                            'change_pct': latest.get('涨跌幅', 0),
                            'turnover': latest.get('总市值', 0),
                            'leading_stock': latest.get('领涨股', ''),
                            'leading_change': latest.get('领涨股-涨跌幅', 0)
                        })

                except Exception as e:
                    continue

            result = pd.DataFrame(sector_data)
            result = result.sort_values('change_pct', ascending=False)

            logger.info(f"[成功] 获取到{len(result)}个板块数据")

            return result

        except Exception as e:
            logger.error(f"[错误] 获取板块数据失败: {e}")

        return pd.DataFrame()

    def get_northbound_flow(self, days: int = 5) -> pd.DataFrame:
        """
        获取北向资金数据

        Args:
            days: 回溯天数

        Returns:
            北向资金DataFrame
        """
        logger.info(f"[API获取] 北向资金数据")
        self._rate_limit()

        try:
            df = self.retry_helper.execute_with_retry(
                ak.stock_hsgt_north_net_flow_in_em
            )

            if df is not None and len(df) > 0:
                logger.info(f"[成功] 获取到北向资金数据")

                # 存入SQLite
                for _, row in df.tail(days).iterrows():
                    date_str = str(row.get('日期', '')).replace('-', '')
                    self.market_store.save_northbound_flow(date_str, {
                        'net_inflow': row.get('当日净流入', 0)
                    })

                return df.tail(days)

        except Exception as e:
            logger.warning(f"[警告] 北向资金数据获取失败: {e}")

        return pd.DataFrame()

    def get_sector_diffusion(self) -> Optional[float]:
        """
        获取板块扩散度（上涨板块数 / 总板块数）

        Returns:
            板块扩散度得分（0-100），None表示获取失败
        """
        try:
            df = self.get_sector_activity()
            if df is not None and not df.empty:
                total = len(df)
                rising = int((df.get('change_pct', 0) > 0).sum())
                if total > 0:
                    score = (rising / total) * 100
                    logger.info(f"[数据获取] 板块扩散度: {score:.1f} ({rising}/{total})")
                    return score
        except Exception as e:
            logger.warning(f"[警告] 获取板块扩散度失败: {e}")
        return None

    def get_turnover_momentum(self, stock_code: str, trade_date: str) -> Optional[float]:
        """
        获取换手率动量（5日均换手率 / 20日均换手率）

        Args:
            stock_code: 股票代码
            trade_date: 交易日期（用于日志，实际基于SQLite最新数据）

        Returns:
            换手率动量得分（0-100），None表示数据不足
        """
        try:
            df = self.stock_store.get_kline_history(stock_code, days=25)
            if df is not None and len(df) >= 20:
                df = df.sort_values('trade_date', ascending=False)
                avg5 = df.head(5)['turnover_rate'].mean()
                avg20 = df.head(20)['turnover_rate'].mean()
                if pd.notna(avg5) and pd.notna(avg20) and avg20 > 0:
                    ratio = avg5 / avg20
                    score = min(ratio * 50, 100)
                    logger.info(f"[数据获取] {stock_code} 换手率动量: {score:.1f} (5日{avg5:.2f}% / 20日{avg20:.2f}%)")
                    return score
        except Exception as e:
            logger.warning(f"[警告] 获取换手率动量失败 {stock_code}: {e}")
        return None

    def get_policy_news_sentiment(self, trade_date: str) -> Optional[float]:
        """
        获取政策新闻情绪评分

        Args:
            trade_date: 交易日期

        Returns:
            情绪得分（0-100），None表示获取失败
        """
        try:
            self._rate_limit()
            df = self.retry_helper.execute_with_retry(
                ak.stock_news_em,
                symbol="A股"
            )
            if df is not None and not df.empty:
                logger.info(f"[数据获取] 获取到{len(df)}条新闻，使用简化情绪评分")
                return 50.0
        except Exception as e:
            logger.warning(f"[警告] 获取政策新闻情绪失败: {e}")
        return None

    def get_fx_rate(self) -> Optional[float]:
        """
        获取汇率风险评分（美元/人民币波动）

        Returns:
            汇率风险得分（0-100），None表示获取失败
        """
        try:
            self._rate_limit()
            df = self.retry_helper.execute_with_retry(
                ak.currency_boc_safe,
                symbol="USD/CNH"
            )
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                change_pct = float(latest.get('涨跌幅', 0))
                score = max(0, min(100, 50 - change_pct * 10))
                logger.info(f"[数据获取] 汇率风险评分: {score:.1f}")
                return score
        except Exception as e:
            logger.warning(f"[警告] 获取汇率数据失败: {e}")
        return None

    def get_index_pe(self, index_code: str = '000300') -> Optional[float]:
        """
        获取指数PE分位数评分

        Args:
            index_code: 指数代码（默认沪深300）

        Returns:
            PE评分（0-100），低PE=高分，None表示获取失败
        """
        try:
            self._rate_limit()
            df = self.retry_helper.execute_with_retry(
                ak.index_value_hist_funddb,
                symbol=index_code
            )
            if df is not None and not df.empty:
                pe_col = '市盈率' if '市盈率' in df.columns else 'pe'
                pe_values = pd.to_numeric(df[pe_col], errors='coerce').dropna()
                if len(pe_values) > 0:
                    current_pe = pe_values.iloc[-1]
                    median_pe = pe_values.median()
                    if median_pe > 0:
                        score = max(0, min(100, (median_pe - current_pe) / median_pe * 50 + 50))
                        logger.info(f"[数据获取] 指数PE评分 ({index_code}): {score:.1f} (当前PE:{current_pe:.1f}, 中位数:{median_pe:.1f})")
                        return score
        except Exception as e:
            logger.warning(f"[警告] 获取指数PE失败: {e}")
        return None

    def cleanup_old_data(self, days_to_keep: int = 365):
        """
        清理过期数据

        Args:
            days_to_keep: 保留天数
        """
        self.stock_store.cleanup_old_data(days_to_keep)


# ==================== 测试代码 ====================

if __name__ == '__main__':
    import os

    # 创建测试目录
    os.makedirs("./test_data", exist_ok=True)

    # 初始化集成版数据获取器
    fetcher = IntegratedDataFetcher(db_path="./test_data/test_stock.db")

    logger.info("=" * 60)
    logger.info("集成版数据获取器测试")
    print("=" * 60)

    # 测试获取K线历史
    trade_date = datetime.now().strftime('%Y%m%d')

    # 测试1: 获取单只股票K线历史
    logger.info("[测试1] 获取单只股票K线历史")
    kline_history = fetcher.get_stock_kline_history('000001', days=30)
    logger.info(f"获取到{len(kline_history)}条K线数据")

    # 测试2: 获取活跃股票
    logger.info("[测试2] 获取活跃股票")
    active_stocks = fetcher.get_active_stocks(trade_date, min_change_pct=5.0, top_n=20)
    logger.info(f"获取到{len(active_stocks)}只活跃股票")
    if not active_stocks.empty:
        logger.info(f"字段: {list(active_stocks.columns)}")
        logger.info(f"\n{active_stocks.head(3)[['stock_code', 'stock_name', 'change_pct']].to_string(index=False)}")

    # 测试3: 保存因子数据
    logger.info("[测试3] 保存因子数据")
    test_factors = {
        'A001': 75.0,
        'L001': 60.0,
        'W2S01': 85.0,
        'S2W01': 20.0
    }
    fetcher.save_factors('000001', trade_date, test_factors)

    # 测试4: 获取数据统计
    logger.info("[测试4] 数据统计")
    stats = fetcher.get_data_stats()
    logger.info(f"数据库统计: {stats}")

    # 关闭
    fetcher.close()

    logger.info("=" * 60)
    logger.info("测试完成")
    print("=" * 60)
