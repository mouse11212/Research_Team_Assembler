# 验收 SQL 清单与判据

执行位置：`{SRC}` 下 `sqlite3 data/stock_history.db "<SQL>"`。`{GAP_START}`/`{GAP_END}`/`{TODAY}` 同 agent-prompts.md 约定。

## A. K线

```sql
-- A1 最新日期与覆盖
SELECT MAX(trade_date), COUNT(DISTINCT stock_code) FROM stock_kline;
-- A2 当日行数（与覆盖数同量级，差值=停牌/退市）
SELECT trade_date, COUNT(*) FROM stock_kline GROUP BY trade_date ORDER BY trade_date DESC LIMIT 3;
-- A3 缺口股归因（应全部为停牌/退市：max明显<GAP_END）
SELECT stock_code, MAX(trade_date) FROM stock_kline GROUP BY stock_code
 HAVING MAX(trade_date) < '{GAP_END}' ORDER BY 2 DESC LIMIT 20;
-- A4 未来日期脏数据排查（应为0行）
SELECT stock_code, MAX(trade_date) FROM stock_kline GROUP BY stock_code
 HAVING MAX(trade_date) > '{GAP_END}' LIMIT 20;
```

**判据**：MAX=GAP_END ✅；当日行数 ≈ 覆盖数（差值<1%且A3可解释）✅；A4>0行 → 脏数据，转分析师裁决。

## B. 市场情绪

```sql
SELECT trade_date, emotion_phase, position_multiplier, limit_up_count, limit_down_count, board_max
  FROM market_emotion WHERE trade_date > '{GAP_START}' AND trade_date <= '{GAP_END}' ORDER BY trade_date;
```

**判据**：区间每交易日一行 ✅；抽查2天 limit_up_count 与 K线实数一致：
```sql
SELECT COUNT(*) FROM stock_kline WHERE trade_date='{抽查日}' AND change_pct >= 9.9;
```
**口径注记**：2026-07-16 起 limit_up_count=全市场实数、board_max/sector_diffusion=真实计算；此前生产行=top50截断/TODO存0。跨边界做IC/回测对比须声明。bull_bear_type=None 是 Fail-Loud 正确行为（本地无指数数据），非缺陷。

## C. 龙虎榜

```sql
SELECT trade_date, COUNT(*), SUM(net_buy IS NOT NULL) FROM dragon_tiger
 WHERE trade_date > '{GAP_START}' AND trade_date <= '{GAP_END}' GROUP BY trade_date ORDER BY trade_date;
```

**判据**：有榜日均有行（50-120行/日为正常波动）✅；net_buy 为 NULL 的日期=问财降级日（须与 worker 报告的降级清单一致，NULL≠伪造）✅。已知：`dragon_tiger` 存在历史列错位脏数据（trade_date 存股票代码如 '920981'），按真实日期查询不受影响，清洗见 incident-playbook.md。

## D. 概念映射

```sql
SELECT COUNT(*), COUNT(DISTINCT stock_code), COUNT(DISTINCT concept_name) FROM stock_concept_map;
SELECT COUNT(*) FROM stock_concept_map WHERE updated_at > '{TODAY前一日}';
```

**判据**：今日刷新行数>0 ✅；若为0但 worker 称已刷新 → **worker误报或时序差**（先确认同步进程已结束再判），转分析师裁决。断点续传：`python3 data/sync_stock_concept.py --offset {断点}`。

## E. 降级裁决先例（判例库）

1. **情绪口径偏离选A（接受真实值）**：复刻已知bug（top50截断）换一致性是负资产；口径切换点明确可标注。前提=报告显式注明切换点。
2. **北交所333只skip**：92开头在 stock_info 但腾讯源无数据→skip；非可投域、非缺陷。归因SQL=A4 + `WHERE stock_code LIKE '92%'`。
3. **问财降级**：连败即停、net_buy=NULL（非0）、记断点、不阻塞主线；补跑留给冷却后。
4. **时序差误判（反例）**：概念同步启动前查库判"未刷新"=误判；裁决涉"是否生效"必须在进程结束后查库。
