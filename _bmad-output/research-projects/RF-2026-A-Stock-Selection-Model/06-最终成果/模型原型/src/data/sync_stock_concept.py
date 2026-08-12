"""
股票概念板块同步（概念弹性层）—— 快变维度，建议每日/每周刷新。

权威背景与定位（见研究结论）：
- 概念板块由数据商自编（同花顺/东财/Wind），**无官方标准、一股属多个概念、随题材频繁增减**。
- 但它正是游资龙头/题材战法真正交易的单位（强势板块、板块轮动、题材龙头）。
- 因此独立成表 stock_concept_map（多对多），与稳定的 stock_info(行业) 分层维护。

数据模型：
    stock_concept_map(stock_code, concept_name, concept_code, updated_at)
    —— 一股多行（多对多）。

数据源（2026-06-15 改：绕开被封的 eastmoney，改走 P1 适配层）：
- 概念清单：MultiSourceDataFetcher.fetch_concept_catalog() = 同花顺 ths（`stock_board_concept_name_ths`，373 概念，列 name/code）。
- 概念成分：MultiSourceDataFetcher.fetch_concept_members(name) = pywencai「X概念成分股」方向，
  返回 canonical(stock_code/concept_name/concept_code/source)。pywencai adapter 内建限频+进程内缓存。
  ⚠️ 373 概念 = 373 次 pywencai 查询，有封号风险 → 概念间额外 sleep；支持 --offset 分块续传。

幂等/可续（2026-06-15 改）：**逐概念即时 upsert（INSERT OR REPLACE），不先 DELETE 整表** ——
中途封号/中断不丢已取数据、不清空旧表，可用 --offset 续传。整表全量重建用 --rebuild（先清表）。

用法：
    python data/sync_stock_concept.py                 # 全量刷新（373概念，逐个upsert）
    python data/sync_stock_concept.py --limit 5       # 仅前5个概念（验证/调试）
    python data/sync_stock_concept.py --offset 200    # 从第200个概念续传（封号后分块）
    python data/sync_stock_concept.py --rebuild       # 先清表再全量重建
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logging_config import get_logger, setup_logging

logger = get_logger(__name__)
CANONICAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stock_history.db')

# 概念间限频（pywencai adapter 已内建限频+缓存，这里再加保险，降低 373 次连发的封号风险）
CONCEPT_DELAY = 0.5


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_concept_map (
            stock_code   TEXT NOT NULL,
            concept_name TEXT NOT NULL,
            concept_code TEXT,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (stock_code, concept_name)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_concept_code ON stock_concept_map(stock_code)")
    conn.commit()


def fetch_concepts(multi_source, limit: int = 0, offset: int = 0):
    """返回 [(concept_name, concept_code), ...]。走 P1 适配层 ths 概念清单（绕开 eastmoney）。"""
    cat = multi_source.fetch_concept_catalog()
    if cat is None or len(cat) == 0:
        return []
    ncol = next((c for c in ['name', '概念名称', '板块名称', '概念'] if c in cat.columns), cat.columns[0])
    ccol = next((c for c in ['code', '概念代码', '板块代码', '代码'] if c in cat.columns), None)
    out = []
    for _, r in cat.iterrows():
        name = str(r[ncol]).strip()
        code = str(r[ccol]).strip() if ccol else None
        if name:
            out.append((name, code))
    if offset:
        out = out[offset:]
    return out[:limit] if limit else out


def main():
    parser = argparse.ArgumentParser(description='同步股票概念板块映射（多对多，快变层，P1适配层）')
    parser.add_argument('--limit', type=int, default=0, help='仅处理前N个概念（调试/验证）')
    parser.add_argument('--offset', type=int, default=0, help='跳过前N个概念（封号后分块续传）')
    parser.add_argument('--rebuild', action='store_true', help='先清空 stock_concept_map 再全量重建')
    parser.add_argument('--db', default=CANONICAL_DB)
    args = parser.parse_args()

    setup_logging({'level': 'INFO'})
    t0 = time.perf_counter()
    logger.info("=" * 60)
    logger.info("同步 stock_concept_map（概念弹性层 · P1适配层 ths+pywencai，绕开eastmoney）")

    # 装配 P1 适配层
    try:
        from data.multi_source_fetcher import MultiSourceDataFetcher
        multi_source = MultiSourceDataFetcher()
    except Exception as e:
        logger.error(f"  P1 适配层装配失败：{type(e).__name__}: {e}")
        return 4

    conn = sqlite3.connect(args.db)
    try:
        ensure_table(conn)

        try:
            concepts = fetch_concepts(multi_source, args.limit, args.offset)
        except Exception as e:
            logger.warning(f"  概念清单获取失败（{type(e).__name__}）。ths 需 mini-racer JS 解密，"
                           f"若 arm64 不兼容见 memory[data-source-alternatives] 修复。表已建好，本次无写入。")
            return 2

        if not concepts:
            logger.warning("  概念清单为空，无可处理概念。")
            return 2

        if args.rebuild and not args.offset:
            conn.execute("DELETE FROM stock_concept_map")
            conn.commit()
            logger.info("  [--rebuild] 已清空旧表，开始全量重建。")

        logger.info(f"  待处理概念 {len(concepts)} 个（offset={args.offset}），逐个取成分并即时落库…")
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        total_rows, ok, fail, empty = 0, 0, 0, 0
        # 问财限流熔断（2026-08-11 分析师裁决=阻塞项）：限流时失败被标"成分为空"继续烧配额，
        # 连续 5 个空/失败即中止并打印断点；成功即复位计数
        consec_bad, MAX_CONSEC = 0, 5

        for i, (name, ccode) in enumerate(concepts, 1):
            try:
                mem = multi_source.fetch_concept_members(name)
                if mem is None or len(mem) == 0:
                    empty += 1
                    consec_bad += 1
                    logger.warning(f"    概念 [{name}] 成分为空（跳过，不计失败；连续空/败 {consec_bad}/{MAX_CONSEC}）")
                    if consec_bad >= MAX_CONSEC:
                        logger.error(f"  ⛔ 连续 {consec_bad} 个概念空/失败，判定问财限流，熔断中止。"
                                     f"断点续传：--offset {args.offset + i - consec_bad}（从连败 streak 起点重查，烧掉的概念不丢）")
                        return 3
                    time.sleep(CONCEPT_DELAY)
                    continue
                # 即时 upsert：concept_code 用 ths catalog 的权威码覆盖 pywencai 的逐行码
                batch = [(str(r['stock_code']).zfill(6), name, ccode, now)
                         for _, r in mem.iterrows() if r.get('stock_code')]
                conn.executemany(
                    "INSERT OR REPLACE INTO stock_concept_map(stock_code,concept_name,concept_code,updated_at) "
                    "VALUES (?,?,?,?)", batch)
                conn.commit()
                total_rows += len(batch)
                ok += 1
                consec_bad = 0
                if i % 10 == 0 or args.limit:
                    logger.info(f"    进度 {i}/{len(concepts)}：[{name}] {len(batch)}行，累计 {total_rows} 行")
                time.sleep(CONCEPT_DELAY)
            except Exception as e:
                fail += 1
                consec_bad += 1
                logger.warning(f"    概念 [{name}] 取成分失败：{type(e).__name__}: {str(e)[:60]}（连续空/败 {consec_bad}/{MAX_CONSEC}）")
                if consec_bad >= MAX_CONSEC:
                    logger.error(f"  ⛔ 连续 {consec_bad} 个概念空/失败（末次 {type(e).__name__}），判定问财限流，熔断中止。"
                                 f"断点续传：--offset {args.offset + i - consec_bad}（从连败 streak 起点重查，烧掉的概念不丢）")
                    return 3
                time.sleep(CONCEPT_DELAY)

        distinct = conn.execute("SELECT COUNT(DISTINCT stock_code) FROM stock_concept_map").fetchone()[0]
        table_rows = conn.execute("SELECT COUNT(*) FROM stock_concept_map").fetchone()[0]
        logger.info("-" * 60)
        logger.info(f"  ✅ 概念成功 {ok}/{len(concepts)}（失败 {fail}，空 {empty}）| 本次写入 {total_rows} 行 | "
                    f"表内共 {table_rows} 行 / 覆盖 {distinct} 只股票 | 耗时 {time.perf_counter()-t0:.1f}s")
        logger.info("=" * 60)
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main() or 0)
