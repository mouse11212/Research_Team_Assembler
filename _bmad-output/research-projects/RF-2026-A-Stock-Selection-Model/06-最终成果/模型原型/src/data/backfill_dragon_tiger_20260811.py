"""回补龙虎榜 20260805 -> 20260811(串行, 反爬安全)

数据源策略(canonical, 绕开被墙的 eastmoney):
  - 主源: akshare 新浪 stock_lhb_detail_daily_sina (上榜清单+原因+成交额, 支持历史日期)
  - 富化: pywencai 日期限定查询 "YYYY年M月D日龙虎榜" 补 净买额/买入额/卖出额
    * 校验: 返回列名必须带请求日期后缀(如 当日龙虎榜净额[20260805]),
      否则视为错日期数据, 丢弃富化(Fail-Loud, 禁止错数据入库)
    * 问财调用间隔 >= 5s (PywencaiAdapter(min_interval=5) 内建限频+缓存)
    * 连续 2 次失败/校验不过 -> 关闭富化, 后续日期降级为仅新浪清单
  - 日落库后 sleep 3-5s

交易日历: 从 stock_kline DISTINCT trade_date 取 ('20260804'<date<='20260811');
  若库中暂无该区间K线行(K线分片并行写入中), 回退到已知交易日序列
  0805/0806/0807/0810/0811。

落库: data/stock_history.db.dragon_tiger (WAL, busy_timeout=60000)
  列: stock_code, trade_date, net_buy, buy_amount, sell_amount, seats(NULL),
      has_hot_money(0), reason
  Fail-Loud: 缺 stock_code/name 的行丢弃并记日志, 不填中性值。

用法: cd src && python3 data/backfill_dragon_tiger_20260811.py
"""

import logging
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from data.data_normalizer import DataNormalizer  # noqa: E402
from data.source_adapters import AkshareSinaAdapter, PywencaiAdapter  # noqa: E402

DB_PATH = SRC_DIR / "data" / "stock_history.db"
START_DATE = "20260805"
END_DATE = "20260811"
# K线分片并行写入中, 若 stock_kline 暂无区间行则回退此已知交易日序列
FALLBACK_TRADE_DATES = ["20260805", "20260806", "20260807", "20260810", "20260811"]

WENCAI_MAX_CONSEC_FAIL = 2  # 连续失败次数上限, 超过则降级(关闭富化)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_lhb_0811")


def get_trade_dates(conn) -> list:
    """从规范库 stock_kline 取区间内的真实交易日(权威日历), 空则回退已知序列。"""
    rows = conn.execute(
        "SELECT DISTINCT trade_date FROM stock_kline "
        "WHERE trade_date >= ? AND trade_date <= ? ORDER BY trade_date",
        (START_DATE, END_DATE),
    ).fetchall()
    dates = [r[0] for r in rows]
    if not dates:
        logger.warning(
            f"stock_kline 暂无 {START_DATE}~{END_DATE} K线行(分片写入中?), "
            f"回退已知交易日序列 {FALLBACK_TRADE_DATES}")
        return list(FALLBACK_TRADE_DATES)
    return dates


def ensure_reason_column(conn):
    """dragon_tiger 老表缺 reason 列, 增补(幂等)。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(dragon_tiger)")]
    if "reason" not in cols:
        conn.execute("ALTER TABLE dragon_tiger ADD COLUMN reason TEXT")
        conn.commit()
        logger.info("[DDL] dragon_tiger 增补 reason 列")


def save_rows(conn, df: pd.DataFrame, trade_date: str) -> int:
    """canonical df -> dragon_tiger 表。同股多上榜原因合并为一行(UNIQUE 约束)。"""
    if df.empty:
        return 0
    # 同股多条(不同上榜原因)合并: reason 拼接, 数值列取首个非空
    df = df.copy()
    df["reason"] = df["reason"].fillna("")
    agg = (
        df.groupby("stock_code", as_index=False)
        .agg(
            name=("name", "first"),
            net_buy=("net_buy", "first"),
            buy_amount=("buy_amount", "first"),
            sell_amount=("sell_amount", "first"),
            reason=("reason", lambda s: ";".join(sorted({x for x in s if x}))),
        )
    )
    n = 0
    for r in agg.to_dict("records"):
        if not r["stock_code"] or not r["name"]:
            logger.warning(f"[Fail-Loud] {trade_date} 丢行(缺必填): {r}")
            continue
        conn.execute(
            "INSERT OR REPLACE INTO dragon_tiger "
            "(stock_code, trade_date, net_buy, buy_amount, sell_amount, "
            " seats, has_hot_money, reason) VALUES (?,?,?,?,?,?,?,?)",
            (
                r["stock_code"], trade_date, r["net_buy"], r["buy_amount"],
                r["sell_amount"], None, 0, r["reason"] or None,
            ),
        )
        n += 1
    conn.commit()
    return n


def fetch_wencai_enrich(wc: PywencaiAdapter, trade_date: str):
    """问财日期限定查询 -> enrichment df(stock_code, net_buy, buy_amount, sell_amount)。
    校验列名日期后缀==请求日期, 不通过返回 None(调用方计失败)。"""
    y, m, d = trade_date[:4], int(trade_date[4:6]), int(trade_date[6:8])
    query = f"{y}年{m}月{d}日龙虎榜"
    raw = wc._query(query, f"lhb_backfill_{trade_date}")
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        logger.warning(f"[wencai] {trade_date} 返回空/非表格")
        return None
    # 定位带日期后缀的金额列
    def _col(keyword):
        for c in raw.columns:
            mobj = re.match(rf".*{keyword}\[(\d{{8}})\]", str(c))
            if mobj:
                return c, mobj.group(1)
        return None, None

    net_col, net_date = _col("龙虎榜净额")
    buy_col, _ = _col("买入金额")
    sell_col, _ = _col("卖出金额")
    if net_col is None or net_date != trade_date:
        got = net_date if net_col else "无净额列"
        logger.warning(
            f"[wencai] {trade_date} 日期校验失败(列后缀={got}), 丢弃富化")
        return None
    code_col = "股票代码" if "股票代码" in raw.columns else "code"
    out = pd.DataFrame({
        "stock_code": raw[code_col].astype(str).str.extract(r"(\d{6})")[0],
        "net_buy": pd.to_numeric(raw[net_col], errors="coerce"),
        "buy_amount": pd.to_numeric(raw[buy_col], errors="coerce") if buy_col else None,
        "sell_amount": pd.to_numeric(raw[sell_col], errors="coerce") if sell_col else None,
    }).dropna(subset=["stock_code"]).drop_duplicates("stock_code")
    return out


def main():
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    ensure_reason_column(conn)

    dates = get_trade_dates(conn)
    logger.info(f"交易日历({START_DATE}~{END_DATE}): {len(dates)} 天 -> {dates}")

    sina = AkshareSinaAdapter()
    normalizer = DataNormalizer()
    wc = PywencaiAdapter(min_interval=5.0)  # 问财 >=5s 限频

    wc_disabled = False
    wc_consec_fail = 0
    degraded_dates = []   # 富化降级(仅新浪)日期
    empty_dates = []      # 源返回空(跳过)日期
    day_counts = {}

    for i, td in enumerate(dates):
        # ---- 1. 新浪主源 ----
        try:
            raw = sina.fetch_dragon_tiger(td)
        except Exception as e:
            logger.error(f"[sina] {td} 异常: {e}")
            raw = None
        if raw is None or raw.empty:
            logger.info(f"[{td}] 新浪返回空, 跳过(非交易日或无上榜)")
            empty_dates.append(td)
            day_counts[td] = 0
            continue
        base = normalizer.normalize_dragon_tiger(raw, sina.name, td)
        if base.empty:
            logger.warning(f"[{td}] 新浪 {len(raw)} 行归一化后全丢(缺必填)")
            day_counts[td] = 0
            continue

        # ---- 2. 问财富化(可降级) ----
        enriched = False
        if not wc_disabled:
            try:
                enrich = fetch_wencai_enrich(wc, td)
                if enrich is not None and not enrich.empty:
                    base = base.drop(
                        columns=["net_buy", "buy_amount", "sell_amount"],
                        errors="ignore",
                    ).merge(enrich, on="stock_code", how="left")
                    enriched = True
                    wc_consec_fail = 0
                else:
                    wc_consec_fail += 1
            except Exception as e:
                logger.warning(f"[wencai] {td} 异常: {e}")
                wc_consec_fail += 1
            if wc_consec_fail >= WENCAI_MAX_CONSEC_FAIL:
                wc_disabled = True
                logger.error(
                    f"[wencai] 连续 {wc_consec_fail} 次失败, 关闭富化, "
                    "后续日期降级为仅新浪清单")
        if not enriched:
            degraded_dates.append(td)

        # ---- 3. 落库 ----
        n = save_rows(conn, base, td)
        day_counts[td] = n
        nb = base["net_buy"].notna().sum() if "net_buy" in base.columns else 0
        logger.info(
            f"[{td}] 落库 {n} 行 (新浪 {len(base)} 行, 含净买额 {nb} 行, "
            f"{'已富化' if enriched else '仅新浪'}) [{i+1}/{len(dates)}]")

        if i < len(dates) - 1:
            time.sleep(3 + random.uniform(0, 2))  # 日间隔 3-5s

    # ---- 4. SQL 验证 ----
    logger.info("=" * 50)
    logger.info("SQL 验证: 每交易日落库行数")
    for td in dates:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM dragon_tiger WHERE trade_date=?", (td,)
        ).fetchone()[0]
        nb = conn.execute(
            "SELECT COUNT(*) FROM dragon_tiger WHERE trade_date=? AND net_buy IS NOT NULL",
            (td,),
        ).fetchone()[0]
        logger.info(f"  {td}: {cnt} 行 (含净买额 {nb})")
    total = conn.execute(
        "SELECT COUNT(*) FROM dragon_tiger WHERE trade_date BETWEEN ? AND ?",
        (START_DATE, END_DATE),
    ).fetchone()[0]
    logger.info(f"区间总落库: {total} 行")
    logger.info(f"富化降级日期(仅新浪): {degraded_dates}")
    logger.info(f"空数据跳过日期: {empty_dates}")
    logger.info(f"问财富化最终状态: {'已禁用(被封/连续失败)' if wc_disabled else '全程可用'}")

    conn.close()


if __name__ == "__main__":
    main()
