# RF-2026-A-Stock-Selection-Model · 课题指南

> A股短线龙头情绪动量策略量化研究（持仓1-3日，日频）。
> ⛔ **策略未盈利（回测盈亏比~0.83<1.5），禁止实盘。**

## 导航

- **第一入口**：`README.md`（课题进度总索引）
- **代码**：`06-最终成果/模型原型/src`（选股流水线；代码级 CLAUDE.md 在其内，改动代码前必读）
- **改进建议/设计文档**：`07-改进建议/`
- **本目录 skill**：`.claude/skills/ashare-data-sync` —— 增量同步A股数据到最新交易日（说"同步A股数据到最新"即触发）

## 数据源红线（违反=采集中断）

1. **eastmoney 全系被墙**（akshare `*_em` 禁用）：Clash fake-ip + IP限流双重封。
2. **腾讯 proxy = K线主源**，≤6 并发为实测安全线。
3. **问财(pywencai) 有封号风险**：全局单线低频；限流特征=`'NoneType' object has no attribute 'get'`，连败即停冷却数小时。
4. 规范库唯一真相源：`06-最终成果/模型原型/src/data/stock_history.db`（WAL，新连接 `PRAGMA busy_timeout=60000`）。

## 关键结论（分析必须对照）

- 样本外+蒙特卡洛验证：**盈利=beta非alpha**（因子选股与随机选股无统计差别，2026-06-25）。
- 主板可投域结构性不盈利；北交所不在可投域。
- 31因子体系实际仅少数因子参与排序（详见 `06-最终成果/模型原型/src/output/prediction_review_20260805.md`）。

## 状态锚点（2026-08-06 快照；最新状态以 memory 会话锚点为准，本文件不追日报）

- 数据同步至 **20260804**（K线/情绪/龙虎榜）；概念映射部分刷新，断点 `sync_stock_concept.py --offset 213` 待续传
- 分支：`feature/w2s01-gate`（W2S01≥50 准入门槛 + Top5主板配额≥3）
- 待办：概念断点续传；龙虎榜 0730/0731/0803/0804 净买额补跑（`backfill_dragon_tiger_enrich_retry.py`）；dragon_tiger 468行历史脏数据清洗；`sync_stock_concept.py` 加连续失败熔断
