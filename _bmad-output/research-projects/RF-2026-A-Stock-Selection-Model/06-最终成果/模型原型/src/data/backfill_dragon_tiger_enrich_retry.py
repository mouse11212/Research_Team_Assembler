"""龙虎榜富化补跑(第二轮): 为首轮问财降级的日期补净买额, 更慢节奏(>=12s/次)。

仅 UPDATE 已有行的 net_buy/buy_amount/sell_amount, 不新增行(新浪清单已落库)。
连续 2 次失败即中止(不硬闯), 已成功的日期保留。
用法: cd src && python3 data/backfill_dragon_tiger_enrich_retry.py 20260723 20260724 ...
"""

import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from data.source_adapters import PywencaiAdapter  # noqa: E402
from data.backfill_dragon_tiger_20260804 import fetch_wencai_enrich  # noqa: E402

DB_PATH = SRC_DIR / "data" / "stock_history.db"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("lhb_enrich_retry")


def main(dates):
    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.execute("PRAGMA busy_timeout=60000")
    interval = float(os.environ.get("WENCAI_INTERVAL", "12"))
    wc = PywencaiAdapter(min_interval=interval)  # 限频(默认12s, 可 env 调慢)

    consec_fail = 0
    done, failed = [], []
    for i, td in enumerate(dates):
        try:
            enrich = fetch_wencai_enrich(wc, td)
        except Exception as e:
            logger.warning(f"[wencai] {td} 异常: {e}")
            enrich = None
        if enrich is None or enrich.empty:
            consec_fail += 1
            failed.append(td)
            if consec_fail >= 2:
                logger.error(f"连续 {consec_fail} 次失败, 中止补跑(剩余日期保持降级)")
                failed.extend(dates[i + 1:])
                break
            continue
        consec_fail = 0
        n = 0
        for r in enrich.to_dict("records"):
            cur = conn.execute(
                "UPDATE dragon_tiger SET net_buy=?, buy_amount=?, sell_amount=? "
                "WHERE stock_code=? AND trade_date=?",
                (r["net_buy"], r["buy_amount"], r["sell_amount"],
                 r["stock_code"], td),
            )
            n += cur.rowcount
        conn.commit()
        done.append(td)
        logger.info(f"[{td}] 富化更新 {n} 行 [{i+1}/{len(dates)}]")
        if i < len(dates) - 1:
            time.sleep(3)  # 限频器保证 >=12s, 此处仅小幅缓冲

    logger.info(f"补跑完成: 成功 {len(done)} 天 {done}; 未补 {len(failed)} 天 {failed}")
    for td in dates:
        cnt, nb = conn.execute(
            "SELECT COUNT(*), SUM(net_buy IS NOT NULL) FROM dragon_tiger WHERE trade_date=?",
            (td,),
        ).fetchone()
        logger.info(f"  {td}: {cnt} 行 (含净买额 {nb or 0})")
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: backfill_dragon_tiger_enrich_retry.py YYYYMMDD ...")
        sys.exit(1)
    main(sys.argv[1:])
