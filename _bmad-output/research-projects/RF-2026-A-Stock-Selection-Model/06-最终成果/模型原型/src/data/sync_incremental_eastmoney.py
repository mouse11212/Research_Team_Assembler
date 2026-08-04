"""
增量K线同步（canonical schema） —— 腾讯proxy为主、eastmoney为备

数据源诊断结论（2026-06-11 本环境实测）：
- akshare 的东财系函数被本地沙箱/WAF 阻断（RemoteDisconnected）。
- eastmoney push2his 直连可用但易触发 IP 限流（突发请求后封禁数十分钟）。
- akshare 腾讯函数按年循环取全量(~28请求/股, 13s)，过慢。
- ★ 腾讯 proxy 区间接口 proxy.finance.qq.com 直连：0.2s/股、字段全（含成交额/换手率）、未被封 → 选为主源。

字段契约（写入 canonical stock_kline，上层因子/回测无感知数据来自哪个源）：
  open_price/close_price/high_price/low_price + volume + amount + change_pct + turnover_rate + ma5/10/20/60

腾讯 proxy 行格式：[date, open, close, high, low, volume(手), {}, turnover_rate(%), amount(万元), '']
  amount = 第8项 * 10000（万元→元）；change_pct 由相邻收盘价自算。

反爬：渐进提速（慢启动→连续成功加速→失败指数退避→连续失败熔断暂停）+ 随机抖动 + 浏览器头。
增量：per-stock floor（各股从自身最后日期续传），INSERT OR REPLACE 幂等可重跑续传。

用法：
  python sync_incremental_eastmoney.py                  # 全量增量
  python sync_incremental_eastmoney.py --limit 30       # 验证
  python sync_incremental_eastmoney.py --offset 1500    # 分块续传
"""

import argparse
import random
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

DB_PATH = Path(__file__).parent / "stock_history.db"

TX_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
EM_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_UT = "fa5fd1943c7b386f172d6893dbfba10b"
EM_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://gu.qq.com/",
    "Accept": "*/*",
}

# ---- 反爬节流（自适应渐进提速）----
START_DELAY = 0.45
MIN_DELAY = 0.12
MAX_DELAY = 6.0
SPEEDUP = 0.93
BACKOFF = 2.0
JITTER = 0.12
RETRY = 3
REQ_TIMEOUT = 8
CIRCUIT_FAILS = 10
CIRCUIT_PAUSE = 25


def tx_symbol(code):
    return ("sh" if code.startswith("6") else "sz") + code


def to_secid(code):
    return f"1.{code}" if code.startswith("6") else f"0.{code}"


def _safe_float(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def fetch_tencent(session, code, floor, end):
    """腾讯 proxy 区间日K（前复权）。返回 canonical dict 列表（含自算 change_pct）。
    取整年区间以获得 floor 前一日收盘，用于计算 change_pct。"""
    sym = tx_symbol(code)
    year_start = floor[:4] + "-01-01"
    end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:]}"
    params = {"param": f"{sym},day,{year_start},{end_fmt},640,qfq"}
    r = session.get(TX_URL, params=params, headers=HEADERS, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if d.get("code") != 0 or not d.get("data"):
        return []
    node = d["data"].get(sym, {})
    raw = node.get("qfqday") or node.get("day") or []
    out = []
    prev_close = None
    for row in raw:
        if len(row) < 6:
            continue
        ymd = str(row[0]).replace("-", "")
        close = _safe_float(row[2])
        chg = None
        if prev_close not in (None, 0) and close is not None:
            chg = (close - prev_close) / prev_close * 100
        prev_close = close if close is not None else prev_close
        amount = _safe_float(row[8]) if len(row) > 8 else None
        if amount is not None:
            amount *= 10000.0  # 万元 → 元
        out.append({
            "trade_date": ymd,
            "open_price": _safe_float(row[1]),
            "close_price": close,
            "high_price": _safe_float(row[3]),
            "low_price": _safe_float(row[4]),
            "volume": _safe_float(row[5]),
            "amount": amount,
            "change_pct": chg,
            "turnover_rate": _safe_float(row[7]) if len(row) > 7 else None,
        })
    return out


def fetch_eastmoney(session, code, floor, end):
    """备源：eastmoney push2his（字段全，但易限流）。"""
    params = {
        "secid": to_secid(code), "ut": EM_UT,
        "fields1": "f1,f2,f3,f4,f5,f6", "fields2": EM_FIELDS2,
        "klt": "101", "fqt": "1", "beg": floor, "end": end, "lmt": "260",
    }
    r = session.get(EM_URL, params=params, headers=HEADERS, timeout=REQ_TIMEOUT)
    r.raise_for_status()
    data = r.json().get("data")
    if not data:
        return []
    out = []
    for line in data.get("klines") or []:
        p = line.split(",")
        if len(p) < 11:
            continue
        out.append({
            "trade_date": p[0].replace("-", ""),
            "open_price": _safe_float(p[1]), "close_price": _safe_float(p[2]),
            "high_price": _safe_float(p[3]), "low_price": _safe_float(p[4]),
            "volume": _safe_float(p[5]), "amount": _safe_float(p[6]),
            "change_pct": _safe_float(p[8]), "turnover_rate": _safe_float(p[10]),
        })
    return out


UPSERT = """
INSERT OR REPLACE INTO stock_kline
  (stock_code, trade_date, open_price, close_price, high_price, low_price,
   volume, amount, change_pct, turnover_rate, ma5, ma10, ma20, ma60, created_at)
VALUES (:stock_code, :trade_date, :open_price, :close_price, :high_price, :low_price,
   :volume, :amount, :change_pct, :turnover_rate, NULL, NULL, NULL, NULL, :created_at)
"""


def save_rows(conn, code, rows):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for rec in rows:
        rec["stock_code"] = code
        rec["created_at"] = now
    conn.executemany(UPSERT, rows)
    conn.commit()
    return len(rows)


def recompute_ma(conn, affected):
    """对受影响股票按全 close 序列重算 MA，仅回写新增日期"""
    updated = 0
    for code, new_dates in affected.items():
        series = conn.execute(
            "SELECT trade_date, close_price FROM stock_kline "
            "WHERE stock_code=? ORDER BY trade_date", (code,)).fetchall()
        closes = [r[1] for r in series]
        for i, (td, _) in enumerate(series):
            if td not in new_dates:
                continue

            def ma(n):
                if i + 1 < n:
                    return None
                w = closes[i + 1 - n:i + 1]
                return None if any(v is None for v in w) else sum(w) / n
            conn.execute(
                "UPDATE stock_kline SET ma5=?,ma10=?,ma20=?,ma60=? "
                "WHERE stock_code=? AND trade_date=?",
                (ma(5), ma(10), ma(20), ma(60), code, td))
            updated += 1
    conn.commit()
    return updated


def load_sync_codes(conn):
    """同步清单 = 已有K线的股票 ∪ stock_info 全市场清单。

    新IPO经 sync_stock_info 入库后自动纳入同步范围（无历史→按默认floor全量拉取）。
    """
    return [r[0] for r in conn.execute(
        "SELECT stock_code FROM stock_kline UNION SELECT stock_code FROM stock_info "
        "ORDER BY stock_code")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--start", default="", help="强制统一起点 YYYYMMDD")
    ap.add_argument("--end", default="", help="结束 YYYYMMDD（默认今天）")
    ap.add_argument("--source", choices=["tencent", "eastmoney"], default="tencent")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    # 支持多分片并行同步：写锁等待最多60s而非立即失败(避免并发写"database is locked")
    conn.execute("PRAGMA busy_timeout=60000")

    end = args.end or datetime.now().strftime("%Y%m%d")
    db_max = conn.execute("SELECT MAX(trade_date) FROM stock_kline").fetchone()[0]
    stock_max = {r[0]: r[1] for r in conn.execute(
        "SELECT stock_code, MAX(trade_date) FROM stock_kline GROUP BY stock_code")}

    codes = load_sync_codes(conn)
    codes = codes[args.offset:]
    if args.limit:
        codes = codes[:args.limit]

    primary = fetch_tencent if args.source == "tencent" else fetch_eastmoney
    secondary = fetch_eastmoney if args.source == "tencent" else fetch_tencent

    print(f"[同步] 全局DB最新={db_max} 结束={end} 待处理={len(codes)}只 "
          f"主源={args.source} 起步={START_DELAY}s→{MIN_DELAY}s (per-stock增量)")

    session = requests.Session()
    delay = START_DELAY
    affected, consec_fail = {}, 0
    stats = {"ok": 0, "skip": 0, "fail": 0, "rows": 0, "fb": 0}
    t0 = time.time()

    for i, code in enumerate(codes):
        floor = args.start or stock_max.get(code, "20250101")
        if floor > end:
            stats["skip"] += 1
            continue

        rows, used_fb = None, False
        for attempt in range(RETRY):
            try:
                rows = primary(session, code, floor, end)
                break
            except Exception:
                if attempt < RETRY - 1:
                    time.sleep(delay * BACKOFF + random.uniform(0, JITTER))
                    delay = min(MAX_DELAY, delay * BACKOFF)
        if rows is None:  # 主源失败 → 备源
            try:
                rows = secondary(session, code, floor, end)
                used_fb = True
                stats["fb"] += 1
            except Exception:
                rows = None

        if rows is None:
            stats["fail"] += 1
            consec_fail += 1
            if consec_fail >= CIRCUIT_FAILS:
                print(f"  [熔断] 连续失败{consec_fail}，暂停{CIRCUIT_PAUSE}s")
                time.sleep(CIRCUIT_PAUSE)
                delay, consec_fail = START_DELAY, 0
            continue

        consec_fail = 0
        new_rows = [r for r in rows if r["trade_date"] >= floor and r["close_price"]]
        if new_rows:
            save_rows(conn, code, new_rows)
            affected[code] = {r["trade_date"] for r in new_rows}
            stats["ok"] += 1
            stats["rows"] += len(new_rows)
        else:
            stats["skip"] += 1

        if not used_fb:
            delay = max(MIN_DELAY, delay * SPEEDUP)
        time.sleep(delay + random.uniform(0, JITTER))

        if (i + 1) % 200 == 0:
            print(f"  [{i+1}/{len(codes)}] ok={stats['ok']} skip={stats['skip']} "
                  f"fail={stats['fail']} 备源={stats['fb']} 行={stats['rows']} "
                  f"delay={delay:.2f}s 用时={time.time()-t0:.0f}s")

    print("[MA] 重算受影响股票均线…")
    ma_updated = recompute_ma(conn, affected)

    new_max = conn.execute("SELECT MAX(trade_date) FROM stock_kline").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM stock_kline").fetchone()[0]
    covered = conn.execute(
        "SELECT COUNT(DISTINCT stock_code) FROM stock_kline WHERE trade_date=?",
        (new_max,)).fetchone()[0]
    print("=" * 60)
    print(f"完成 ok={stats['ok']} skip={stats['skip']} fail={stats['fail']} "
          f"备源={stats['fb']} 新增行={stats['rows']} MA更新={ma_updated}")
    print(f"DB最新={new_max}（覆盖{covered}只）总行={total} 用时={time.time()-t0:.0f}s")
    conn.close()


if __name__ == "__main__":
    main()
