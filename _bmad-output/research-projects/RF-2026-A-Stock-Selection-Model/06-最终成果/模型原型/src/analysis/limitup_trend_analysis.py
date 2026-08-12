# -*- coding: utf-8 -*-
"""20260811 主板涨停股趋势分析（一次性分析脚本，设计见 docs/superpowers/specs/2026-08-11-limitup-trend-analysis-design.md）

筛选：主板(60/00) change_pct>=9.9% 涨停，剔除ST/*ST，总市值>=30亿（腾讯批量报价补全）。
形态：120日窗口横盘/下跌分类 + 近5日转升确认（均线多头/突破/量能/安全垫）→ 0-100打分。
红线：禁eastmoney、禁问财；腾讯单批请求；库连接 busy_timeout=60000。
"""
import os
import sqlite3
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(SRC, "data", "stock_history.db")
TRADE_DATE = sys.argv[1] if len(sys.argv) > 1 else None  # 缺省=库内最新交易日
MIN_CAP_YI = 30.0          # 总市值下限（亿）
WIN = 120                  # 形态窗口
VOL_RATIO_MIN = 1.2        # 量能阈值（分析师校准后）
VOL_MIN_SAMPLES = 40
REPORT = os.path.join(SRC, "output", f"limitup_trend_report_{TRADE_DATE}.md")
CHART_DIR = os.path.join(SRC, "output", f"limitup_charts_{TRADE_DATE}")


def db_conn():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def get_candidates(conn):
    """主板涨停，剔除ST（按名称；is_st字段未维护不可信）。"""
    df = pd.read_sql(
        """SELECT k.stock_code, k.change_pct, k.close_price, i.stock_name
           FROM stock_kline k LEFT JOIN stock_info i ON k.stock_code = i.stock_code
           WHERE k.trade_date = ? AND k.change_pct >= 9.9
             AND (k.stock_code LIKE '60%' OR k.stock_code LIKE '00%')
           ORDER BY k.change_pct DESC""",
        conn, params=(TRADE_DATE,))
    df["is_st"] = df["stock_name"].fillna("").str.contains("ST", case=False)
    return df


def fetch_market_caps(codes):
    """腾讯批量报价补总市值（field45，单位亿）。返回 {code: cap or None}。"""
    symbols = [("sh" if c.startswith("6") else "sz") + c for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(symbols)
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=15).read().decode("gbk", errors="replace")
            caps = {}
            for line in raw.strip().split(";"):
                if '="' not in line:
                    continue
                f = line.split('="')[1].split("~")
                if len(f) > 45:
                    try:
                        caps[f[2]] = float(f[45]) if f[45] else None
                    except ValueError:
                        caps[f[2]] = None
            return caps
        except Exception as e:
            print(f"[warn] 腾讯市值接口第{attempt}次失败: {e}", file=sys.stderr)
            time.sleep(2)
    return {c: None for c in codes}


def load_kline(conn, code, days=250):
    return pd.read_sql(
        """SELECT trade_date, open_price, close_price, high_price, low_price,
                  volume, amount, change_pct, ma5, ma10, ma20, ma60
           FROM stock_kline WHERE stock_code = ? AND trade_date <= ?
           ORDER BY trade_date DESC LIMIT ?""",
        conn, params=(code, TRADE_DATE, days)).iloc[::-1].reset_index(drop=True)


def analyze_stock(k):
    """按设计v2计算形态指标。返回指标dict（算不出=None，Fail-Loud）。"""
    r = {"days": len(k)}
    if len(k) < WIN:
        return r  # 历史不足，由上层归类
    w = k.iloc[-WIN:]
    close = w["close_price"].values.astype(float)
    today = k.iloc[-1]

    # 长期形态
    amp = (w["high_price"].max() - w["low_price"].min()) / np.median(close)
    x = np.arange(WIN)
    slope_pct = np.polyfit(x, close, 1)[0] / close.mean() * 100  # %/日
    ret = close[-1] / close[0] - 1
    r.update(amplitude=amp, slope_pct=slope_pct, ret120=ret)

    if amp < 0.55 and abs(ret) < 0.20 and abs(slope_pct) < 0.1:
        pattern = "横盘型"
    elif slope_pct < -0.1 or ret < -0.20:
        pattern = "下跌型"
    else:
        pattern = "不符合"
    r["pattern"] = pattern

    # 突破（箱体上轨=前115日高点，剔除近5日）
    box_top = w["high_price"].iloc[:-5].max()
    r["box_top"] = box_top
    if pattern == "横盘型":
        r["breakout"] = bool(close[-1] >= box_top * 0.98)
    elif pattern == "下跌型":
        r["breakout"] = bool(pd.notna(today["ma60"]) and close[-1] >= today["ma60"])
    else:
        r["breakout"] = False

    # 均线多头
    mas = [today["ma5"], today["ma10"], today["ma20"]]
    r["ma_bull"] = bool(all(pd.notna(m) for m in mas)
                        and close[-1] > mas[0] > mas[1] > mas[2])

    # 量能（amount口径，volume有单位污染禁用）
    a5 = k["amount"].iloc[-5:].dropna()
    a60 = k["amount"].iloc[-65:-5].dropna()
    if len(a5) >= 3 and len(a60) >= VOL_MIN_SAMPLES and a60.mean() > 0:
        r["vol_ratio"] = a5.mean() / a60.mean()
        r["vol_ok"] = bool(r["vol_ratio"] >= VOL_RATIO_MIN)
    else:
        r["vol_ratio"], r["vol_ok"] = None, None  # 样本不足标"—"

    # 安全垫（分形态口径）
    high120 = w["high_price"].max()
    high250 = k["high_price"].max()
    r["dd120"] = close[-1] / high120 - 1
    r["dd250"] = close[-1] / high250 - 1
    if pattern == "横盘型":
        r["cushion_ok"] = bool(r["dd250"] <= -0.15)
    elif pattern == "下跌型":
        r["cushion_ok"] = bool(r["dd120"] <= -0.15)
    else:
        r["cushion_ok"] = False

    # 近期涨幅（分析师终审追加：识别"伪低位"接力票）
    r["ret5"] = close[-1] / k["close_price"].iloc[-6] - 1 if len(k) >= 6 else None
    r["ret20"] = close[-1] / k["close_price"].iloc[-21] - 1 if len(k) >= 21 else None

    # 可买性：连板数 + 一字板 + 近20日已大幅反弹（追高接力风险）
    streak = 0
    for cp in k["change_pct"].iloc[::-1]:
        if cp >= 9.9:
            streak += 1
        else:
            break
    r["streak"] = streak
    o, h, l, c = (today["open_price"], today["high_price"],
                  today["low_price"], today["close_price"])
    r["one_word"] = bool(h == l or (o == h == c and today["change_pct"] >= 9.9))
    r["buy_risk"] = "高" if (streak >= 2 or r["one_word"]
                             or (r["ret20"] is not None and r["ret20"] >= 0.25)) else "低"

    # 评分
    score = 0
    score += 40 if pattern in ("横盘型", "下跌型") else 0
    score += 15 if r["ma_bull"] else 0
    score += 15 if r["breakout"] else 0
    score += 15 if r["vol_ok"] else 0
    score += 15 if r["cushion_ok"] else 0
    r["score"] = score
    return r


def fmt(v, pct=False, nd=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v*100:.{nd}f}%" if pct else f"{v:.{nd}f}"


def make_chart(code, name, k, out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["PingFang SC", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
        w = k.iloc[-120:]
        fig, ax = plt.subplots(figsize=(10, 4.5))
        xs = np.arange(len(w))
        ax.plot(xs, w["close_price"], lw=1.2, label="close")
        for m, c in (("ma20", "orange"), ("ma60", "green")):
            if w[m].notna().any():
                ax.plot(xs, w[m], lw=0.9, label=m, color=c)
        ax.axhline(w["high_price"].iloc[:-5].max(), ls="--", lw=0.8, color="red", label="box_top")
        ax.set_title(f"{code} {name} 120d")
        ax.legend(fontsize=8)
        step = max(1, len(w) // 8)
        ax.set_xticks(xs[::step])
        ax.set_xticklabels(w["trade_date"].iloc[::step], rotation=30, fontsize=7)
        fig.tight_layout()
        fig.savefig(out, dpi=110)
        plt.close(fig)
        return True
    except Exception as e:
        print(f"[warn] 出图失败 {code}: {e}", file=sys.stderr)
        return False


def main():
    global TRADE_DATE, REPORT, CHART_DIR
    conn = db_conn()
    if not TRADE_DATE:
        TRADE_DATE = conn.execute("SELECT MAX(trade_date) FROM stock_kline").fetchone()[0]
    REPORT = os.path.join(SRC, "output", f"limitup_trend_report_{TRADE_DATE}.md")
    CHART_DIR = os.path.join(SRC, "output", f"limitup_charts_{TRADE_DATE}")
    print(f"分析日期: {TRADE_DATE}")
    cand = get_candidates(conn)
    print(f"主板涨停(含ST): {len(cand)} 只")
    st_rows = cand[cand["is_st"]]
    cand = cand[~cand["is_st"]].copy()
    print(f"剔除ST: {len(st_rows)} 只 -> 候选 {len(cand)} 只")

    caps = fetch_market_caps(cand["stock_code"].tolist())
    cand["market_cap"] = cand["stock_code"].map(caps)
    cap_missing = cand[cand["market_cap"].isna()]
    small = cand[(cand["market_cap"].notna()) & (cand["market_cap"] < MIN_CAP_YI)]
    pool = cand[(cand["market_cap"].isna()) | (cand["market_cap"] >= MIN_CAP_YI)].copy()
    print(f"市值<{MIN_CAP_YI}亿剔除: {len(small)} 只; 市值缺失保留待标: {len(cap_missing)} 只; 入池 {len(pool)} 只")

    results, insufficient = [], []
    for _, row in pool.iterrows():
        k = load_kline(conn, row["stock_code"])
        m = analyze_stock(k)
        rec = {**row.to_dict(), **m}
        if m.get("days", 0) < WIN:
            insufficient.append(rec)
        else:
            results.append((rec, k))
    # 并列按近20日涨幅升序（越低位越前，分析师终审裁决）
    results.sort(key=lambda t: (-t[0]["score"], t[0]["ret20"] if t[0]["ret20"] is not None else 9))
    print(f"历史不足(<{WIN}日): {len(insufficient)} 只; 完成打分: {len(results)} 只")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    os.makedirs(CHART_DIR, exist_ok=True)
    CN = ["一", "二", "三", "四", "五", "六", "七"]
    lines = []
    a = lines.append
    a(f"# 主板涨停股趋势分析报告（{TRADE_DATE}）\n")
    a("> 筛选口径：沪深主板（60/00）涨停（change_pct≥9.9%）、剔除ST/*ST、总市值≥30亿；")
    a("> 形态：120日横盘/下跌 + 近5日转升确认。⛔本报告为数据筛选结果，不构成投资建议；策略样本外验证=beta非alpha。\n")
    a("## 一、筛选漏斗\n")
    a(f"| 环节 | 只数 |\n|---|---|\n| 主板涨停（含ST） | {len(cand)+len(st_rows)} |")
    a(f"| 剔除ST/*ST | -{len(st_rows)} |\n| 市值<30亿剔除 | -{len(small)} |")
    a(f"| 市值缺失（保留并标注） | {len(cap_missing)} |\n| K线历史不足120日 | -{len(insufficient)} |")
    a(f"| **入池打分** | **{len(results)}** |\n")
    a("## 二、入池股票评分总表\n")
    a("| 排名 | 代码 | 名称 | 市值(亿) | 形态 | 评分 | 近5日 | 近20日 | 振幅比 | 斜率(%/日) | 120日收益 | 量比(amount) | 突破 | 均线多头 | 安全垫 | 连板 | 一字板 | 买入风险 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, (r, _) in enumerate(results, 1):
        a(f"| {i} | {r['stock_code']} | {r['stock_name']} | {fmt(r['market_cap'], nd=1)} | "
          f"{r['pattern']} | {r['score']} | {fmt(r['ret5'], pct=True, nd=1)} | {fmt(r['ret20'], pct=True, nd=1)} | "
          f"{fmt(r['amplitude'])} | {fmt(r['slope_pct'])} | "
          f"{fmt(r['ret120'], pct=True, nd=1)} | {fmt(r['vol_ratio'])} | "
          f"{'✅' if r['breakout'] else '—'} | {'✅' if r['ma_bull'] else '—'} | "
          f"{'✅' if r['cushion_ok'] else '—'} | {r['streak']} | {'⚠️' if r['one_word'] else '—'} | {r['buy_risk']} |")
    a("")
    a(f"## {CN[2]}、Top10 逐只详析\n")
    sec = 3
    for i, (r, k) in enumerate(results[:10], 1):
        a(f"### {i}. {r['stock_code']} {r['stock_name']}（{r['pattern']}，{r['score']}分）\n")
        a(f"- 市值 {fmt(r['market_cap'], nd=1)} 亿；120日振幅比 {fmt(r['amplitude'])}，回归斜率 {fmt(r['slope_pct'])} %/日，区间收益 {fmt(r['ret120'], pct=True, nd=1)}")
        a(f"- 近期涨幅：近5日 {fmt(r['ret5'], pct=True, nd=1)}，近20日 {fmt(r['ret20'], pct=True, nd=1)}（≥25%标高风险=已反弹一段的接力票，非低位启动）")
        a(f"- 箱体上轨（前115日高点）{fmt(r['box_top'])}，今日收盘 {r['close_price']}；突破={'是' if r['breakout'] else '否'}")
        a(f"- 均线多头={'是' if r['ma_bull'] else '否'}；量比(amount口径)={fmt(r['vol_ratio'])}（阈值{VOL_RATIO_MIN}）；安全垫：距120日高点 {fmt(r['dd120'], pct=True, nd=1)} / 距250日高点 {fmt(r['dd250'], pct=True, nd=1)}")
        a(f"- 可买性：连板 {r['streak']} 天，一字板={'是' if r['one_word'] else '否'}，次日买入风险 **{r['buy_risk']}**\n")
        chart = os.path.join(CHART_DIR, f"{i:02d}_{r['stock_code']}.png")
        if make_chart(r["stock_code"], r["stock_name"], k, chart):
            a(f"![{r['stock_code']}]({os.path.relpath(chart, os.path.dirname(REPORT))})\n")
    if insufficient:
        a(f"## {CN[sec]}、K线历史不足120日（次新股，未打分）\n")
        sec += 1
        for r in insufficient:
            a(f"- {r['stock_code']} {r['stock_name']}（{r['days']}日数据，市值 {fmt(r['market_cap'], nd=1)} 亿）")
        a("")
    a(f"## {CN[sec]}、方法学与局限\n")
    sec += 1
    a("- 形态分类：横盘型=振幅比<0.55且|收益|<20%且|斜率|<0.1%/日；下跌型=斜率<-0.1%/日或收益<-20%（阈值经分析师用今日候选分布实测校准）。")
    a("- 量能用 amount（元）而非 volume：volume 在 20260518-0525 存在股→手单位切换污染；amount 近60日 NULL 率~8%，有效样本<40 标" + '"' + "—" + '"' + "。")
    a("- 箱体上轨=剔除近5日的前115日高点（避免突破与安全垫互斥）；安全垫横盘型看250日高点、下跌型看120日高点。")
    a("- 市值为腾讯实时快照（总市值，亿）；缺失者不剔除但标注。")
    a("- 复核SQL：`SELECT stock_code, trade_date, close_price, change_pct, amount, ma5, ma20, ma60 FROM stock_kline WHERE stock_code='<代码>' ORDER BY trade_date DESC LIMIT 125;`")
    a("- 可买性高风险触发：连板≥2、一字板、**近20日涨幅≥25%**（已反弹一段的接力票，非低位启动，0805教训）；同分并列按近20日涨幅升序（越低位越前）。")
    a("- 局限：单日快照，无盘中承接/封单数据；评分是形态初筛非买入信号；⛔策略未盈利禁实盘。\n")
    a(f"## {CN[sec]}、被过滤名单\n\n**ST剔除（{len(st_rows)}）**：{', '.join(st_rows['stock_code'] + ' ' + st_rows['stock_name']) if len(st_rows) else '无'}\n")
    if len(small):
        a(f"**市值<30亿剔除（{len(small)}）**：{', '.join(small['stock_code'] + ' ' + small['stock_name'] + '(' + small['market_cap'].map(lambda v: fmt(v, nd=1)) + '亿)')}\n")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"报告: {REPORT}")
    print(f"图表: {CHART_DIR} ({len(results[:10])} 张)")


if __name__ == "__main__":
    main()
