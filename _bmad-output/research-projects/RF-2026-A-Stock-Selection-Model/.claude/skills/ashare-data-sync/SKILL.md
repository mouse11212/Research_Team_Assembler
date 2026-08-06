---
name: ashare-data-sync
description: 增量同步A股数据到最新交易日（K线/情绪/龙虎榜/概念四类，腾讯+新浪+问财多源，6分片并行+股票分析师Agent监督裁决）。当用户要求"同步/更新/增量收集A股数据""把数据更新到最新交易日""补K线"时使用。
---

# A股数据增量同步（分析师监督版）

流程来源：2026-08-04/05 实战（6分片K线0封禁、问财降级处置、分析师裁决抓出口径/时序问题）。

## 何时用 / 何时不用

- **用**：收盘后把 `stock_history.db` 增量更新到最新交易日（四类数据）。
- **不用**：全量重建；任何依赖 eastmoney 的任务（被墙，无解）；预测选股（本 skill 不含，数据齐后另行触发 `cli.py --date <基准日> --mode daily`）。

## 反爬红线（不可违反）

1. **eastmoney 全系禁用**（akshare `*_em`）——Clash fake-ip + IP限流双重封。
2. **腾讯 proxy ≤6 并发**（实测安全线）；分片 fail 飙升或出现「熔断」→ 该分片退回单流重跑（脚本幂等 INSERT OR REPLACE，重跑安全）。
3. **问财全局单线**：同一时刻只允许一个进程访问问财；概念与龙虎榜富化都打听财，必须合并在同一个串行线Agent内，禁止拆成并行。连败即停（限流特征=`'NoneType' object has no attribute 'get'`），冷却数小时。
4. 停牌股无数据=正常缺口，不计 fail。
5. mac 无 `timeout` 命令；长任务一律 `caffeinate -i`。

## 前置事实

- 规范库：`06-最终成果/模型原型/src/data/stock_history.db`（WAL；任何新连接 `PRAGMA busy_timeout=60000`）
- 所有命令工作目录=`06-最终成果/模型原型/src`
- 提交 `06-最终成果/模型原型/src` 内文件需 `git add -f`（`_bmad-output/` 被 gitignore）

## 五阶段流程

### 阶段0 准备（主线程串行）

1. 备份：`sqlite3 <库> "PRAGMA wal_checkpoint(TRUNCATE);"` 后 `cp` 为 `stock_history.db.bak-<YYYYMMDD>-presync`
2. 刷新股票清单：`caffeinate -i python3 data/sync_stock_info.py --force`（新IPO名称入 stock_info；行业源降级深市兜底属已知限制，不阻塞）
3. 定缺口：分别查 `stock_kline`/`market_emotion`/`dragon_tiger` 的 `MAX(trade_date)`；缺口止=最近交易日
4. 算分片：`M = ceil(union清单数/6)`，union=`SELECT stock_code FROM stock_kline UNION SELECT stock_code FROM stock_info`

**出口**：备份存在；缺口区间明确；M 与 6 个 offset 算好。

### 阶段1 并行扇出（后台Agent）

- 启动**分析师监督Agent**（后台常驻，见下节协议）
- 6个 K线分片Agent：`sync_incremental_eastmoney.py --offset {i*M} --limit {M}`（offset=0,M,…,5M）
- 1个 问财串行线Agent：先逐日回补龙虎榜、后概念映射（**顺序不可换**）
- prompt 模板：`references/agent-prompts.md`

**出口**：7个worker Agent全部返回结构化报告。

### 阶段2 情绪回填（K线6片全部完成后）

- 情绪回填Agent：复用生产 `MarketEnvironmentAnalyzer` 与 `save_market_emotion`，**纯库内计算，零外部请求**，Fail-Loud（算不出=None，禁中性值伪装）

**出口**：回填报告+至少2天抽查对账（LU/LD 与 K线实数一致）。

### 阶段3 验收

- 逐条执行 `references/acceptance-checks.md` 的 SQL
- **每份 worker 报告（含阶段1/2全部）必须转发分析师裁决**：通过/重跑/降级；降级须记录受影响因子

**出口**：分析师逐项裁决留痕；不达标项有补救或降级说明。

### 阶段4 收尾

- 汇总四类数据状态表；`git add -f` 提交新增脚本与报告
- 更新 memory 会话锚点：数据同步日期、断点（如概念 `--offset`）、降级欠账、待办

## 分析师监督协议

- **时机**：阶段1扇出前启动，后台常驻，全程复用同一实例（SendMessage 续话）
- **转发义务**：每份 worker 报告逐份转发，等裁决再推进；降级裁决不阻塞主线
- **裁决三态**：通过 / 重跑（指明分片或日期段）/ 降级（说明理由+受影响因子）
- **权限边界**：只读库与日志自查验证；禁止写库改码；唯一可写=其评审报告
- **必须对照的已知结论**：⛔策略未盈利禁实盘；样本外验证=beta非alpha；北交所不在可投域

## 已知陷阱速查

1. 北交所 92 开头 skip=正常（腾讯源不支持；非可投域）；归因SQL见 acceptance-checks.md
2. `cli.py --date` 是**数据基准日**非目标日（预测次日=传今天；传明天被交易日历拒）
3. `sync_stock_concept.py` **无熔断**：被限流时把失败标"成分为空"继续烧配额——问财线Agent必须盯日志、连败即杀、记 `--offset` 断点
4. `dragon_tiger` 表有历史列错位脏数据（trade_date 字段存股票代码）；按真实日期查询不受影响
5. **时序敏感裁决必须在任务完成后查库**（0804 教训：概念同步启动前查库误判"未刷新"）
6. stock_info 刷新后 union 多出新股→末段分片出现大量全量拉取与 skip 属预期（9字头排最后）
7. 情绪回填用真实全市场口径（2026-07-16 起），与历史生产行（top50截断/TODO存0）存在口径切换点，跨边界对比须声明
8. 预测run会用生产口径重算覆盖当日情绪回填行（`save_market_emotion`=INSERT OR REPLACE）

## references（按需加载）

- `references/agent-prompts.md` — 分析师/分片/问财线/情绪回填四类完整 prompt 模板
- `references/acceptance-checks.md` — 验收 SQL + 判据 + 降级裁决先例
- `references/incident-playbook.md` — 问财限流画像 / 断点续传 / 补跑脚本 / 处置决策树
