# ashare-data-sync Skill + 课题级 CLAUDE.md 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 2026-08-04/05 实战验证的"A股增量数据采集+分析师Agent监督"流程固化为项目级 skill，并为研究课题目录创建 CLAUDE.md。

**Architecture:** 文档型产物。SKILL.md 装流程与红线（每次必读），三类细节（prompt模板/验收SQL/故障手册）放 references 按需加载。CLAUDE.md 做课题级导航与红线摘要。

**Tech Stack:** Markdown、Claude Code 项目级 skill 约定（`.claude/skills/<name>/SKILL.md` + frontmatter）、sqlite3 验收。

**Spec:** `docs/superpowers/specs/2026-08-06-ashare-data-sync-skill-design.md`

## Global Constraints

- 根目录（下称 `$RP`）= `_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model`（相对仓库根 Research_Team_Assembler）
- 代码目录（下称 `$SRC`）= `$RP/06-最终成果/模型原型/src`
- SKILL.md ≤150 行；CLAUDE.md ≤120 行；中文撰写，代码标识符保持原文
- frontmatter 必须有 `name` 和 `description`（description 含触发词）
- `$RP` 在仓库 .gitignore 内（`_bmad-output/`），提交一律 `git add -f`（沿用 w2s 提交惯例）
- 不写自动化测试；验收=结构完整 + 路径/SQL 实证（本库真实跑通）

---

### Task 1: SKILL.md 主文件

**Files:**
- Create: `$RP/.claude/skills/ashare-data-sync/SKILL.md`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: skill 主入口；引用 `references/agent-prompts.md`、`references/acceptance-checks.md`、`references/incident-playbook.md`（Task 2-4 创建，文件名必须完全一致）

- [ ] **Step 1: 写文件**（完整内容如下）

````markdown
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

- 规范库：`<SRC>/data/stock_history.db`（WAL；任何新连接 `PRAGMA busy_timeout=60000`）
- 所有命令工作目录=`<SRC>`（= `06-最终成果/模型原型/src`）
- 提交 `<SRC>` 内文件需 `git add -f`（`_bmad-output/` 被 gitignore）

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
````

（注：正文中 `<SRC>` 字样在写文件时替换为字面路径 `06-最终成果/模型原型/src`。）

- [ ] **Step 2: 验证结构与行数**

```bash
RP="_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model"
head -4 "$RP/.claude/skills/ashare-data-sync/SKILL.md"   # 确认 frontmatter name/description 在
wc -l "$RP/.claude/skills/ashare-data-sync/SKILL.md"     # 预期 ≤150
```
预期：frontmatter 含 `name: ashare-data-sync` 与含触发词的 description；行数 ≤150。

- [ ] **Step 3: Commit**

```bash
git add -f "$RP/.claude/skills/ashare-data-sync/SKILL.md"
git commit -m "feat(skill): ashare-data-sync SKILL.md主文件(五阶段流程+分析师监督协议+反爬红线)"
```

---

### Task 2: references/agent-prompts.md（prompt 模板库）

**Files:**
- Create: `$RP/.claude/skills/ashare-data-sync/references/agent-prompts.md`

**Interfaces:**
- Consumes: Task 1 的引用路径
- Produces: 占位符约定 `{OFFSET}` `{LIMIT}` `{GAP_START}` `{GAP_END}` `{TODAY}`（YYYYMMDD 格式），Task 3/4 不引用本文件

- [ ] **Step 1: 写文件**（完整内容如下）

````markdown
# Agent Prompt 模板库

用法：复制模板 → 替换占位符（`{OFFSET}`/`{LIMIT}`/`{GAP_START}`/`{GAP_END}`/`{TODAY}`，均 YYYYMMDD）→ 以 general-purpose 后台 Agent 启动。`{SRC}` = 模型原型 src 绝对路径。所有 worker 的最终文本=给编排者的结构化报告。

## 1. 分析师监督Agent（全程常驻，SendMessage 续话）

```
你是「股票分析师」监督Agent（资深A股短线量化分析师+数据质量总监）。用户可能离线，你代表用户对数据收集作业做专业判断。主线程（编排者）会把各工作Agent的报告转发给你，你返回明确裁决。

## 项目背景
- 代码目录：{SRC}
- 策略：A股短线龙头情绪动量，31因子体系（W2S弱转强为核心）。⛔策略未盈利（盈亏比~0.83），禁止实盘。
- 关键认知：样本外+蒙特卡洛验证结论=「盈利是beta不是alpha」；主板可投域结构性不盈利。
- config.yaml 有路径bug，一切命令须在 src 目录下跑。

## 数据源约束（反爬红线）
- eastmoney 全系被墙，禁止建议任何 *_em 接口。
- 腾讯 proxy 6并发是实测安全上限；K线分片fail飙升或出现「熔断」应退回单流重跑（脚本幂等）。
- 问财(pywencai)有封号风险：全局只允许单线低频。若报告被封/失败飙升 → 裁决降级（记断点、保住已落库数据），不得建议加并发。
- 停牌股无数据=正常缺口，不算fail。北交所92开头腾讯源不支持=正常skip，非可投域。

## 本次作业
缺口区间 {GAP_START}→{GAP_END}。环节：6个K线分片 → 问财串行线（龙虎榜→概念）→ 情绪回填 → SQL验收。

## 你的职责与权限
- 裁决每份报告：通过 / 需重跑（指明分片或日期段）/ 降级接受（说明理由+受影响因子）。有疑虑时用只读SQL和读日志自行验证后再判断。**时序敏感裁决必须在任务完成后查库**（先查后判会误判进行中的任务）。
- 禁止写数据库、禁止改代码；唯一允许写的文件是你的评审报告。
- 每条回复以「裁决：通过/重跑/降级」开头，后跟简要理由（≤200字）。

先回复确认你已理解职责，并列出你打算重点盯防的3个风险点。
```

## 2. K线分片Agent（×6，offset=0/M/2M/3M/4M/5M）

```
你负责K线增量同步分片{i}。工作目录：{SRC}（先cd进去）。

执行：caffeinate -i python3 data/sync_incremental_eastmoney.py --offset {OFFSET} --limit {LIMIT} > output/sync_shards/shard_{i}.log 2>&1
用 run_in_background 启动，之后每30-60秒 tail 日志轮询，直到出现「完成」行（预计5-15分钟，末段分片含新股全量拉取会更慢）。

完成后检查：
1. tail 日志末行统计（ok/skip/fail/备源/新增行/用时）
2. grep -c "熔断" output/sync_shards/shard_{i}.log
3. 若 fail>0：grep 出失败代码行，区分「停牌/无数据」（正常）与真实网络错误；若有真实网络错误或熔断>0 → 原命令重跑一次（脚本幂等 INSERT OR REPLACE，重跑安全），再统计。
4. skip 较多时先想北交所（92开头腾讯源不支持=正常），不要误报。

约束：不得修改任何代码；不得跑其他同步命令；不得并发打探腾讯以外的源。
最终返回结构化文本：分片号、offset/limit、ok/skip/fail/备源/新增行、是否重跑及原因、异常清单（代码+原因）、日志路径。你的最终文本就是给编排者的报告，直接给数据。
```

## 3. 问财串行线Agent（独占问财额度，先龙虎榜后概念）

```
你是「问财串行线」采集Agent，独占全局问财(pywencai)调用额度——绝对禁止并发问财请求（封号风险）。工作目录：{SRC}（先cd进去）。规范库=data/stock_history.db（WAL；你自己写的连接必须 PRAGMA busy_timeout=60000，因为另有6个K线分片在并发写库）。

【任务1：回补龙虎榜 {GAP_START}→{GAP_END}】
项目已有P1数据源适配层——data/multi_source_fetcher.py 提供龙虎榜获取（新浪 stock_lhb_detail_daily_sina 主源按日拿清单 + 问财日期限定查询富化净买额，带降级）；落库 dragon_tiger 表走 DataNormalizer.normalize_dragon_tiger 的 canonical 路径。先读 data/multi_source_fetcher.py、data/source_adapters.py、data/data_normalizer.py 摸清正确调用方式；不要使用 dragon_tiger_collector.py 的老直连接口（走eastmoney=被墙）。参考实现可复用 data/backfill_dragon_tiger_20260804.py 的模式（串行、日间隔3-5s、问财≥5s限频、连续2败自动降级、Fail-Loud丢行记日志）。
写回补脚本 data/backfill_dragon_tiger_{TODAY}.py：交易日清单从 stock_kline 的 DISTINCT trade_date（{GAP_START}<date<={GAP_END}）取，逐日拉取落库。跑完后SQL验证每交易日行数与含净买额行数。
若问财段被限流（特征='NoneType' object has no attribute 'get'）：跳过富化只保新浪清单（降级，net_buy=NULL非伪造），记录受影响日期，连败即停不硬闯。另备补跑脚本（只UPDATE缺net_buy的行，WENCAI_INTERVAL环境变量调节奏）。

【任务2：概念映射刷新】（任务1完成后才启动）
caffeinate -i python3 data/sync_stock_concept.py > output/sync_shards/concept.log 2>&1（run_in_background+轮询）。⚠️该脚本无熔断——被限流时把失败标"成分为空"继续烧配额：你必须盯日志，连续失败/空结果即杀进程，记录断点offset，停止，降级报告，不要硬闯。支持 --offset N 断点续传。

【反爬红线】全程串行；不得并行任何问财/新浪调用；不得尝试eastmoney接口。
【返回】结构化报告：任务1各日落库行数/降级日期清单；任务2概念数/映射行数/断点offset；异常清单；新建脚本路径。你的最终文本就是给编排者的报告，直接给数据。
```

## 4. 情绪回填Agent（K线全部完成后启动）

```
你负责回填 market_emotion 表 {GAP_START}→{GAP_END}。工作目录：{SRC}（先cd进去）。规范库=data/stock_history.db（WAL；连接必须 PRAGMA busy_timeout=60000）。

步骤：
1. 先搞清计算与落库逻辑：读 core/optimized_database_manager.py 的 save_market_emotion、core/execution_chain.py 和 data_fetcher_v3_integrated.py 中 market_emotion 相关调用方，弄清字段口径。参考实现可复用 data/backfill_market_emotion_20260804.py 的模式。
2. 写回填脚本 data/backfill_market_emotion_{TODAY}.py：交易日清单从 stock_kline 的 DISTINCT trade_date（{GAP_START}<date<={GAP_END}）取，逐日**纯库内计算**（只允许读本地表，绝对禁止外部网络请求——问财额度被另一Agent独占，eastmoney被墙），复用第1步发现的生产计算函数（能import就import复用，不另写口径），save落库（幂等）。
3. SQL验证：区间每个交易日一行；抽查2天 limit_up_count/limit_down_count 与 stock_kline 里 change_pct>=9.9 / <=-9.9 的实数对账。
4. Fail-Loud：算不出的字段保持None并记日志，禁止填0/50等中性值伪装（如本地无指数数据时 bull_bear 字段=None）。
5. 口径注记：回填用全市场真实口径（2026-07-16口径切换点后的新口径），不复刻历史生产行的 top50 截断/TODO存0；报告中显式声明。

约束：不改任何现有代码文件（只新增回填脚本）。
返回结构化报告：回填天数、每日字段完整度、抽查对账结果、无法回填的字段及原因、脚本路径。你的最终文本就是给编排者的报告，直接给数据。
```
````

- [ ] **Step 2: 验证占位符一致**

```bash
RP="_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model"
grep -oE "\{[A-Z_]+\}" "$RP/.claude/skills/ashare-data-sync/references/agent-prompts.md" | sort -u
```
预期：仅 `{GAP_START}` `{GAP_END}` `{LIMIT}` `{OFFSET}` `{SRC}` `{TODAY}` `{i}` 七种，无其他未定义占位符。

- [ ] **Step 3: Commit**

```bash
git add -f "$RP/.claude/skills/ashare-data-sync/references/agent-prompts.md"
git commit -m "feat(skill): ashare-data-sync prompt模板库(分析师/分片/问财线/情绪回填)"
```

---

### Task 3: references/acceptance-checks.md（验收SQL与判据）

**Files:**
- Create: `$RP/.claude/skills/ashare-data-sync/references/acceptance-checks.md`

**Interfaces:**
- Consumes: 无
- Produces: 验收 SQL 清单（列名已对本库核实：stock_kline(stock_code,trade_date)、market_emotion(trade_date,emotion_phase,position_multiplier,limit_up_count,limit_down_count,board_max,sector_diffusion,bull_bear_type,bull_bear_confidence)、dragon_tiger(stock_code,trade_date,net_buy,reason)、stock_concept_map(stock_code,concept_name,concept_code,updated_at)）

- [ ] **Step 1: 写文件**（完整内容如下）

````markdown
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
````

- [ ] **Step 2: 实测 SQL 可执行**（对本库真跑，确认列名无误）

```bash
SRC="_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model/06-最终成果/模型原型/src"
sqlite3 "$SRC/data/stock_history.db" "SELECT MAX(trade_date), COUNT(DISTINCT stock_code) FROM stock_kline;"
sqlite3 "$SRC/data/stock_history.db" "SELECT trade_date, emotion_phase, position_multiplier, limit_up_count FROM market_emotion ORDER BY trade_date DESC LIMIT 2;"
sqlite3 "$SRC/data/stock_history.db" "SELECT trade_date, COUNT(*), SUM(net_buy IS NOT NULL) FROM dragon_tiger WHERE trade_date > '20260714' GROUP BY trade_date ORDER BY trade_date DESC LIMIT 2;"
sqlite3 "$SRC/data/stock_history.db" "SELECT COUNT(*), COUNT(DISTINCT stock_code), COUNT(DISTINCT concept_name) FROM stock_concept_map;"
```
预期：四条全部无 SQL 错误返回结果。

- [ ] **Step 3: Commit**

```bash
git add -f "$RP/.claude/skills/ashare-data-sync/references/acceptance-checks.md"
git commit -m "feat(skill): ashare-data-sync验收SQL清单+判据+降级判例库"
```

---

### Task 4: references/incident-playbook.md（故障手册）

**Files:**
- Create: `$RP/.claude/skills/ashare-data-sync/references/incident-playbook.md`

**Interfaces:**
- Consumes: 无
- Produces: 限流画像/续传命令/补跑脚本用法/处置决策树

- [ ] **Step 1: 写文件**（完整内容如下）

````markdown
# 故障手册（Incident Playbook）

## 1. 问财(pywencai)限流画像（2026-08-04 实测）

- 短窗约 **5-6 次成功**后被限流；冷却 ~10 分钟可再放行 ~5 次；累计 ~60 次成功后进入**硬限流**。
- 限流报错特征 = pywencai 内部 `'NoneType' object has no attribute 'get'`。
- 递增间隔（5s→12s→20s）对硬限流无效——连败即停，**冷却数小时**再试。
- 原则：降级保主链路（新浪清单先落库），净买额等富化字段留 NULL（非伪造），记断点。

## 2. 断点续传与补跑

```bash
cd 06-最终成果/模型原型/src
# 概念映射断点续传（断点=已尝试概念数，worker报告给出）
caffeinate -i python3 data/sync_stock_concept.py --offset {断点}
# 龙虎榜净买额补跑（只UPDATE缺net_buy的行；WENCAI_INTERVAL调节奏，默认≥5s；连续2败自中止）
WENCAI_INTERVAL=8 python3 data/backfill_dragon_tiger_enrich_retry.py {日期1} {日期2} ...
# 注意：backfill_dragon_tiger_enrich_retry.py 为 2026-08-04 会话所建；若缺口不同，参照
# data/backfill_dragon_tiger_20260804.py 模式新写（串行/限频/连败降级/Fail-Loud/busy_timeout=60000）。
```

## 3. 处置决策树

```
分片 fail 飙升或日志出现「熔断」?
├─ 是 → kill 该分片 → 同 offset/limit 单流重跑（幂等安全）→ 再失败则报告分析师裁决
└─ 否 → 完成行 fail=0?
        ├─ 是 → 通过（skip 先想北交所/停牌，勿误报）
        └─ 否 → 归因失败代码：停牌/无数据=正常；真实网络错误=重跑一次

问财线报错含 "NoneType ... 'get'"?
├─ 连续≥2次 → 立即停问财段，降级（新浪数据已落库），记断点offset与受影响日期
└─ 偶发 → 间隔拉长重试一次，仍败按连败处置

概念同步日志连续出现「成分为空」?
└─ 立即杀进程（脚本无熔断会烧光配额）→ 记断点 → 冷却数小时后 --offset 续传
```

## 4. 已知数据质量问题

- **dragon_tiger 468 行历史列错位脏数据**（trade_date 字段存股票代码如 '920981'）：按真实日期查询不受影响。清洗建议（先备份再执行，属一次性运维）：
  ```sql
  -- 候选识别（trade_date 不是8位日期）
  SELECT COUNT(*) FROM dragon_tiger WHERE trade_date NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]';
  ```
- **stock_info 行业覆盖不全**（东财行业源被墙→深市兜底，仅~2900只有行业）：已知限制，待 eastmoney 恢复后跑 `sync_market_meta.py`。
- **情绪相位规则敏感**（LU单日降幅>30%即fading，曾14天振荡7次）：评估仓位系数时注意；改进方向=连续2日确认或3日平滑（属策略层，不在本 skill 范围）。

## 5. 环境坑

- mac 无 `timeout`；长任务 `caffeinate -i` 防睡眠。
- `_bmad-output/` 被 gitignore：提交用 `git add -f`。
- akshare `_ths` 等 JS 解密接口依赖 `mini-racer==0.12.4`（arm64 .dylib）；若报 dlsym symbol not found：`pip uninstall -y py-mini-racer mini-racer && pip install mini-racer==0.12.4`。
````

- [ ] **Step 2: 验证引用的文件存在**

```bash
SRC="_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model/06-最终成果/模型原型/src"
ls "$SRC/data/backfill_dragon_tiger_20260804.py" "$SRC/data/backfill_dragon_tiger_enrich_retry.py" "$SRC/data/backfill_market_emotion_20260804.py" "$SRC/data/sync_stock_concept.py" "$SRC/data/sync_stock_info.py" "$SRC/data/sync_incremental_eastmoney.py"
```
预期：6个文件全部存在。

- [ ] **Step 3: Commit**

```bash
git add -f "$RP/.claude/skills/ashare-data-sync/references/incident-playbook.md"
git commit -m "feat(skill): ashare-data-sync故障手册(问财限流画像/断点续传/决策树)"
```

---

### Task 5: 课题级 CLAUDE.md

**Files:**
- Create: `$RP/CLAUDE.md`

**Interfaces:**
- Consumes: Task 1 的 skill 路径
- Produces: 课题级导航文件

- [ ] **Step 1: 写文件**（完整内容如下）

```markdown
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
```

- [ ] **Step 2: 验证引用路径全部存在**

```bash
RP="_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model"
ls "$RP/README.md" "$RP/06-最终成果/模型原型/src/CLAUDE.md" "$RP/07-改进建议" "$RP/.claude/skills/ashare-data-sync/SKILL.md" "$RP/06-最终成果/模型原型/src/output/prediction_review_20260805.md" "$RP/06-最终成果/模型原型/src/data/stock_history.db"
wc -l "$RP/CLAUDE.md"
```
预期：全部存在；CLAUDE.md ≤120行。

- [ ] **Step 3: Commit**

```bash
git add -f "$RP/CLAUDE.md"
git commit -m "docs: RF-2026课题级CLAUDE.md(导航+数据源红线+关键结论+状态锚点)"
```

---

### Task 6: 整体收尾（验证+memory更新）

**Files:**
- Modify: `~/.claude/projects/-Users-gourouhundun-Documents-01---------------Research-Team-Assembler/memory/session-state-2026-06.md`（最新段末尾加一句）
- Modify: 同上目录 `MEMORY.md`（索引行追加 skill 指针）

**Interfaces:**
- Consumes: Task 1-5 全部产物
- Produces: 无代码产出

- [ ] **Step 1: skill 目录结构总检查**

```bash
RP="_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model"
find "$RP/.claude" "$RP/CLAUDE.md" -type f | sort
```
预期恰好5个文件：CLAUDE.md、SKILL.md、references/三件。

- [ ] **Step 2: 交叉引用一致性检查**

```bash
RP="_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model"
grep -n "references/" "$RP/.claude/skills/ashare-data-sync/SKILL.md" | grep -vE "agent-prompts\.md|acceptance-checks\.md|incident-playbook\.md" && echo "发现失效引用" || echo "引用一致"
grep -n "ashare-data-sync" "$RP/CLAUDE.md"
```
预期：无失效引用；CLAUDE.md 含 skill 指针行。

- [ ] **Step 3: 更新 memory**

在 `session-state-2026-06.md` 最新段（2026-08-04/05）末尾追加：
"流程已固化为项目级 skill：`_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model/.claude/skills/ashare-data-sync`（含分析师监督协议+prompt模板+验收SQL+故障手册）；课题级 CLAUDE.md 已建。"

`MEMORY.md` 会话锚点行尾追加"；采集流程已固化skill(ashare-data-sync)"。

- [ ] **Step 4: 最终提交**

```bash
git add docs/superpowers/plans/2026-08-06-ashare-data-sync-skill.md
git commit -m "docs(plan): ashare-data-sync skill实施计划"
```
（memory 在 home 目录不入本仓库，无需提交。）
````

## Self-Review 记录

- Spec 覆盖：SKILL.md六段(Task 1) / references三件(Task 2-4) / CLAUDE.md(Task 5) / 验证方式与git add -f惯例(各Task验证步+Global Constraints) / memory收尾(Task 6) —— 全覆盖
- 占位符扫描：无 TBD/TODO；所有文件完整内容内联
- 一致性：占位符约定 `{GAP_START}`/`{GAP_END}`/`{TODAY}`/`{OFFSET}`/`{LIMIT}` 在 Task 2 定义、Task 3 沿用；references 文件名三处引用一致
