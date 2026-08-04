# 设计：A股增量数据收集(0715→0804) + 分析师监督 + 0805预测

- 日期：2026-08-04
- 状态：用户已批准（"选择方案A" + "执行吧"），用户离线，自主执行
- 项目：`_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model/06-最终成果/模型原型/src`

## 背景

- `stock_kline` 最新 20260714（4591只），缺口 0715→0804 约15个交易日
- `market_emotion` 停在 0714；`dragon_tiger`、`stock_concept_map` 同有缺口
- eastmoney 被墙（Clash fake-ip+限流）；腾讯 proxy 实测 6 并发 0 封禁；问财有封号风险须单线低频
- 同步脚本 `data/sync_incremental_eastmoney.py` 已内建分片（--offset/--limit）、busy_timeout=60000、幂等 INSERT OR REPLACE

## 目标

1. 增量收集四类数据至 20260804 收盘：日K线、市场情绪、龙虎榜、概念映射
2. 覆盖新 IPO（先刷新股票清单）
3. 股票分析师 Agent 全程监督：判断各 worker 报告、决策 retry/降级、审查验收
4. 数据齐后运行 0805 预测（`cli.py --date 20260805 --mode daily`）
5. 分析师输出预测不足分析报告

## 架构

```
阶段0 主线程串行（~2min，无外部风险）
  ├─ DB备份：WAL checkpoint 后 cp db 三件套 → .bak-20260804-presync
  ├─ python data/sync_stock_info.py --force（akshare非东财：stock_info_a_code_name + 同花顺行业）
  └─ 改动 sync_incremental_eastmoney.py：codes 源 stock_kline → stock_kline ∪ stock_info
     （新IPO进同步范围的必要改动）+ 回归测试

阶段1 并行扇出（后台 Agent）
  ├─ Agent×6：K线分片（offset 六等分，腾讯主源，caffeinate 包裹）
  └─ Agent×1：问财串行线 = 龙虎榜(0715→0804, 新浪主+问财低频富化) → 概念映射(sync_stock_concept.py)
     ※ 两任务都打听财，合并单线避免双路并发封号

阶段2（K线完成后 pipeline 接续）
  └─ Agent×1：market_emotion 回填 0715→0804（纯库内计算，零外部请求）

阶段3 主线程 SQL 验收 → 分析师复核
阶段4 0805 预测
阶段5 分析师预测不足分析报告
```

## 监督机制

- 分析师 Agent（后台常驻，命名 `stock-analyst`）：拥有项目背景（策略未盈利禁实盘、beta非alpha结论、W2S01门槛等），接收主线程转发的 worker 报告，返回判断（通过/重跑/降级），并撰写最终不足分析
- 主线程负责编排与执行分析师的决策；分析师不直接操作数据库

## 反爬约束

- 腾讯：≤6 并发（实测安全线）；fail 飙升/熔断 → 该分片退回单流重跑（幂等安全）
- 问财：全局单线程低频（串行线 Agent 独占）；被封 → 记断点 --offset 续传、降级报告、不阻塞 K线主交付
- 停牌股无数据 = 正常缺口，不计 fail
- 长任务 `caffeinate -i` 防 mac 睡眠

## 验收标准（SQL 断言）

1. `stock_kline` MAX(trade_date)=20260804；覆盖 ≥4591+新股；当日行数合理(~4570±)
2. `market_emotion` 覆盖 0715→0804 全部交易日
3. `dragon_tiger` 0715→0804 有榜日均有行
4. `stock_concept_map` 今日刷新
5. 分片报告 fail=0 或全部可解释（停牌）

## 测试

- `sync_incremental_eastmoney.py` codes-union 改动：回归测试（构造含新股小库，断言新股进入同步清单）
- 采集本身不写假测试，验收靠真实 SQL 断言

## 预测与不足分析

- `python cli.py --date 20260805 --mode daily`（基于 0804 收盘数据）
- 分析师审查：Top5 可买性（涨停股次日难买入问题）、板块配额、分数分布、与历史问题（满分泛滥/板块偏差/beta非alpha）对照
- 报告落盘：`src/output/prediction_review_20260805.md`

## 收尾

- 更新 memory：session-state 锚点 → 数据同步至 20260804
