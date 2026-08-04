"""回填 market_emotion 20260715(不含) -> 20260804(纯库内计算, 零网络请求)

动机: market_emotion 表仅存到 20260714, 0715->0804 缺 14 个交易日。
本脚本只读本地规范库表(stock_kline/stock_info), 复用生产计算函数落库。

字段口径(与生产 core/market_environment.py + main.py 对齐, 差异已注明):
  - limit_up_count / limit_down_count:
      stock_kline 当日 change_pct>=9.9 / <=-9.9 的**全市场**计数。
      阈值 9.9 与生产一致; 但生产 main._analyze_market_environment 经
      get_active_stocks(top_n=50) 截断(历史行 limit_up_count 封顶 50 即此因),
      本回填用全市场实数——更真实, 且与验证口径(K线 change_pct>=9.9 计数)对齐。
  - board_max: 当日起向前连续涨停(同一 9.9 规则)的最大连板数, 纯K线推算。
      (生产实跑此字段为 TODO 存默认 0; 回填给真实值。不区分 20cm/30cm 板块
      涨停阈值, 与生产 9.9 统一口径保持一致。)
  - sector_diffusion: stock_info.industry(申万一级, 当日覆盖率约56%)中
      行业均涨幅>0 的行业占比。生产此字段为 TODO(fallback 0.5 参与评分、存0),
      回填用可得的诚实值; 覆盖股票数<100 时置 None(Fail-Loud)。
  - turnover_momentum: 全市场日均换手率 5日均值/20日均值(生产定义"5日/20日比")。
      历史不足20个交易日时置 None(Fail-Loud)。
  - emotion_phase / position_multiplier:
      **复用** core.market_environment.MarketEnvironmentAnalyzer.analyze()
      (同一函数同一阈值), 输入为上述真实值 + 前一交易日实算值(退潮判断)。
  - bull_bear_type / bull_bear_confidence:
      本地无指数数据(external_market 空表, stock_kline 无指数代码),
      judge_bull_bear_market 无法诚实计算 -> 置 None 并记日志。
      (Fail-Loud: 禁止像生产实跑那样存 'neutral'/0 伪装。)

落库: 复用 core.optimized_database_manager.MarketDataStore.save_market_emotion
      (INSERT OR REPLACE 幂等); 连接池补 PRAGMA busy_timeout=60000。

用法: cd src && python3 data/backfill_market_emotion_20260804.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from core.market_environment import MarketEnvironmentAnalyzer  # noqa: E402
from core.optimized_database_manager import (  # noqa: E402
    MarketDataStore,
    OptimizedDatabaseConfig,
)

DB_PATH = SRC_DIR / "data" / "stock_history.db"
START_EXCLUSIVE = "20260715"  # 回填区间: (0715, 0804]
END_DATE = "20260804"
LOOKBACK_START = "20260601"  # 连板/换手动量需要约30个交易日前瞻窗口

LIMIT_UP_PCT = 9.9    # 与生产一致的涨停阈值
LIMIT_DOWN_PCT = -9.9
MIN_INDUSTRY_COVER = 100  # 行业覆盖率下限, 不足则 sector_diffusion=None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_market_emotion")


def load_kline_window(conn) -> pd.DataFrame:
    """读回看窗口内全市场K线(仅必需列), 并预算每票每日连续涨停 streak。"""
    df = pd.read_sql_query(
        "SELECT stock_code, trade_date, change_pct, turnover_rate "
        "FROM stock_kline WHERE trade_date >= ? AND trade_date <= ?",
        conn,
        params=(LOOKBACK_START, END_DATE),
    )
    df = df.sort_values(["stock_code", "trade_date"]).reset_index(drop=True)
    df["lu"] = df["change_pct"] >= LIMIT_UP_PCT
    # 连续涨停 streak: 每票内以"非涨停日"分段, 段内对 lu 累加
    seg = (~df["lu"]).groupby(df["stock_code"]).cumsum()
    df["streak"] = df.groupby([df["stock_code"], seg])["lu"].cumsum()
    return df


def day_metrics(day: pd.DataFrame, industry_map: dict) -> dict:
    """单日可纯K线计算的指标。算不出的字段给 None(Fail-Loud)。"""
    limit_up = int(day["lu"].sum())
    limit_down = int((day["change_pct"] <= LIMIT_DOWN_PCT).sum())
    board_max = int(day["streak"].max()) if limit_up > 0 else 0

    # 板块扩散度: 有行业标签的票按行业聚合, 行业均涨幅>0 的占比
    ind = day["stock_code"].map(industry_map)
    covered = ind.notna()
    sector_diffusion = None
    if int(covered.sum()) >= MIN_INDUSTRY_COVER:
        grp = day.loc[covered, "change_pct"].groupby(ind[covered]).mean()
        sector_diffusion = round(float((grp > 0).mean()), 4)
    else:
        logger.warning(
            f"  [Fail-Loud] 行业覆盖仅 {int(covered.sum())} 只 "
            f"(<{MIN_INDUSTRY_COVER}), sector_diffusion=None"
        )

    return {
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "total_stocks": int(len(day)),
        "board_max": board_max,
        "sector_diffusion": sector_diffusion,
    }


def main() -> int:
    read_conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    read_conn.execute("PRAGMA busy_timeout=60000")

    # 交易日清单: 权威日历 = stock_kline DISTINCT trade_date
    target_dates = [
        r[0]
        for r in read_conn.execute(
            "SELECT DISTINCT trade_date FROM stock_kline "
            "WHERE trade_date > ? AND trade_date <= ? ORDER BY trade_date",
            (START_EXCLUSIVE, END_DATE),
        ).fetchall()
    ]
    logger.info(f"待回填交易日 {len(target_dates)} 天: {target_dates[0]}..{target_dates[-1]}")

    df = load_kline_window(read_conn)
    all_dates = sorted(df["trade_date"].unique())
    logger.info(f"K线窗口 {all_dates[0]}..{all_dates[-1]} 共 {len(all_dates)} 个交易日, {len(df)} 行")

    # 全市场日均换手率序列(供 5日/20日动量)
    turnover_daily = df.groupby("trade_date")["turnover_rate"].mean()

    # 行业映射(申万一级, 快照表)
    industry_map = dict(
        read_conn.execute(
            "SELECT stock_code, industry FROM stock_info "
            "WHERE industry IS NOT NULL AND industry != ''"
        ).fetchall()
    )
    logger.info(f"行业标签覆盖 {len(industry_map)} 只股票")

    # 复用生产存储路径, 并给连接池补 busy_timeout=60000
    store = MarketDataStore(str(DB_PATH), OptimizedDatabaseConfig(db_path=str(DB_PATH)))
    store.pool.initialize()
    for c in store.pool._pool:
        c.execute("PRAGMA busy_timeout=60000")

    analyzer = MarketEnvironmentAnalyzer()
    by_day = {d: g for d, g in df.groupby("trade_date")}

    ok, fail = 0, 0
    summary = []
    for trade_date in target_dates:
        m = day_metrics(by_day[trade_date], industry_map)

        # 换手率动量: 当日及之前 5/20 个交易日
        idx = all_dates.index(trade_date)
        win5 = turnover_daily.iloc[max(0, idx - 4): idx + 1]
        win20 = turnover_daily.iloc[max(0, idx - 19): idx + 1]
        turnover_momentum = None
        if len(win20) >= 20 and win20.mean() > 0:
            turnover_momentum = round(float(win5.mean() / win20.mean()), 4)
        else:
            logger.warning(f"  [Fail-Loud] {trade_date} 换手历史不足20日, turnover_momentum=None")

        # 前一交易日实算值(退潮判断用); 0715 在窗口内, 必有
        prev_lu = prev_bm = None
        if idx > 0:
            prev_date = all_dates[idx - 1]
            pm = day_metrics(by_day[prev_date], industry_map)
            prev_lu, prev_bm = pm["limit_up_count"], pm["board_max"]

        # 情绪相位/仓位系数: 复用生产 analyzer; 关键输入缺失则整链 None(Fail-Loud)
        emotion_phase = position_multiplier = None
        if m["sector_diffusion"] is not None and turnover_momentum is not None:
            env = analyzer.analyze(
                limit_up_count=m["limit_up_count"],
                total_stocks=m["total_stocks"],
                consecutive_board_max=m["board_max"],
                sector_diffusion=m["sector_diffusion"],
                turnover_momentum=turnover_momentum,
                previous_limit_up_count=prev_lu,
                previous_board_max=prev_bm,
            )
            emotion_phase = env.emotion_phase.value
            position_multiplier = env.position_multiplier
        else:
            logger.warning(
                f"  [Fail-Loud] {trade_date} 情绪评分输入缺失, "
                f"emotion_phase/position_multiplier=None"
            )

        # 牛熊: 本地无指数数据, 无法诚实判断 -> None(禁止伪装 neutral/0)
        logger.warning(f"  [Fail-Loud] {trade_date} 无指数数据, bull_bear_type/confidence=None")

        data = {
            "emotion_phase": emotion_phase,
            "position_multiplier": position_multiplier,
            "limit_up_count": m["limit_up_count"],
            "limit_down_count": m["limit_down_count"],
            "board_max": m["board_max"],
            "sector_diffusion": m["sector_diffusion"],
            "bull_bear_type": None,
            "bull_bear_confidence": None,
        }
        if store.save_market_emotion(trade_date, data):
            ok += 1
        else:
            fail += 1
            logger.error(f"  [落库失败] {trade_date}")

        summary.append((trade_date, emotion_phase, position_multiplier,
                        m["limit_up_count"], m["limit_down_count"], m["board_max"],
                        m["sector_diffusion"], turnover_momentum))
        logger.info(
            f"  {trade_date}: phase={emotion_phase} mult={position_multiplier} "
            f"LU={m['limit_up_count']} LD={m['limit_down_count']} "
            f"board={m['board_max']} diff={m['sector_diffusion']} tm={turnover_momentum}"
        )

    read_conn.close()

    logger.info("=" * 70)
    logger.info(f"回填完成: 成功 {ok} 天, 失败 {fail} 天")
    logger.info(f"{'date':<10}{'phase':<9}{'mult':<6}{'LU':<5}{'LD':<5}{'board':<6}{'diff':<8}{'tm':<7}")
    for row in summary:
        logger.info("%-10s%-9s%-6s%-5s%-5s%-6s%-8s%-7s" % tuple(
            "-" if v is None else v for v in row))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
