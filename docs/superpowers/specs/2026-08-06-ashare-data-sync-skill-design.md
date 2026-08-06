# 设计：ashare-data-sync 项目级 skill + 课题级 CLAUDE.md

- 日期：2026-08-06
- 状态：方案A与三节设计已获用户批准
- 来源：2026-08-04/05 夜间增量采集实战（6分片K线+问财串行线+分析师监督Agent裁决）流程固化

## 范围

仅**增量数据采集+分析师监督**（K线/情绪/龙虎榜/概念四类）。不含预测环节（留给人或其他流程触发）。skill 只放内层 `RF-2026-A-Stock-Selection-Model/.claude/skills/`，不做外层转发（外层可见性靠 memory 锚点指引）。

## 产物清单

```
_bmad-output/research-projects/RF-2026-A-Stock-Selection-Model/
├── CLAUDE.md                                  ← 新建（课题级，≤120行）
└── .claude/skills/ashare-data-sync/
    ├── SKILL.md                               ← 新建（≤150行）
    └── references/
        ├── agent-prompts.md                   ← 四类Agent完整prompt模板（参数化占位）
        ├── acceptance-checks.md               ← 验收SQL+判据+降级裁决先例
        └── incident-playbook.md               ← 限流画像/断点续传/熔断处置/脏数据
```

## SKILL.md 结构

frontmatter：`name: ashare-data-sync`；description 含触发词（同步/增量收集A股数据、K线更新、数据到最新交易日）。

正文六段：
1. **何时用/何时不用**：增量日更用；全量重建、依赖 eastmoney 的任务不用
2. **反爬红线（置顶）**：腾讯≤6并发；问财全局单线低频、连败即停冷却数小时；eastmoney 全系禁用；停牌缺口≠fail
3. **五阶段流程**（每阶段=指令+出口标准）：
   - 阶段0 准备：WAL checkpoint+备份三件套 → `sync_stock_info.py --force` 刷新清单（新IPO入库）→ 查库定缺口区间（各表 MAX(trade_date)）
   - 阶段1 扇出：分片数=`ceil(union总数/6)`；6个K线分片Agent（`sync_incremental_eastmoney.py --offset N --limit M`，caffeinate包裹）+ 1个问财串行线Agent（先龙虎榜逐日回补、后概念映射，顺序不可换=独占问财额度）
   - 阶段2（K线完成后）：情绪回填Agent（纯库内计算，零外部请求）
   - 阶段3：SQL验收（读 acceptance-checks.md），全部报告经分析师裁决
   - 阶段4：汇总 + 更新 memory 会话锚点
4. **分析师监督协议**：流程启动时即派出后台常驻分析师Agent；每份worker报告必须转发其裁决；裁决三态=通过/重跑/降级；权限边界=只读库与日志、禁止改库改码、唯一可写=其报告
5. **已知陷阱速查**（≤8条）：北交所92开头skip正常（源不支持、非可投域）；`cli.py --date`是数据基准日非目标日；`sync_stock_concept.py`无熔断须人工盯日志连败即杀；dragon_tiger表有历史列错位脏数据（按真实日期查询不受影响）；时序敏感裁决须在任务完成后查库（0804概念"未刷新"误判教训）；问财 NoneType 报错=限流信号；mac无timeout、长任务caffeinate；git提交src文件需 `git add -f`（_bmad-output被ignore）
6. **指针**：模板与手册→references/

## references/ 内容

- **agent-prompts.md**：分析师/分片/问财线/情绪回填四类完整prompt模板，占位符 `{OFFSET}` `{LIMIT}` `{缺口起}` `{缺口止}` `{日期}`。内容=0804/05实战验证版，含各自的红线、轮询方式、结构化报告格式要求
- **acceptance-checks.md**：验收SQL（kline MAX/覆盖数/当日行数合理性；emotion覆盖区间；dragon_tiger榜日行数；concept刷新时间戳）+ 正常/异常判据 + 先例：情绪口径偏离选A（真实值优于复刻bug）的理由、北交所skip归因SQL、降级记录格式
- **incident-playbook.md**：问财限流画像（~5-6次/短窗、累计~60次硬限流、`'NoneType' object has no attribute 'get'`=限流特征、5s→12s→20s递增间隔无效即停）；断点续传（`sync_stock_concept.py --offset N`）；补跑脚本（`backfill_dragon_tiger_enrich_retry.py`，`WENCAI_INTERVAL`调节奏）；dragon_tiger脏数据清洗建议；分片fail飙升/熔断→单流重跑决策树

## CLAUDE.md（课题级）内容

1. 课题一句话定位 + ⛔策略未盈利禁止实盘红线
2. 导航：第一入口=README.md；代码=`06-最终成果/模型原型/src`（代码级CLAUDE.md在其内）；改进建议=`07-改进建议/`
3. 数据源红线摘要：eastmoney被墙（*_em禁用）；腾讯proxy主源≤6并发；问财单线低频有封号风险
4. skill指针：数据日更→`.claude/skills/ashare-data-sync`
5. 状态锚点（静态快照+免责）：数据至20260804、分支feature/w2s01-gate、待办（概念断点213续传/龙虎榜4天净买额补跑/dragon_tiger脏数据清洗/concept脚本加熔断）；注明"最新状态以memory会话锚点为准，本文件不追日报"

## 验证方式

- SKILL.md/references 写后自查：frontmatter合规、占位符与模板一致、SQL可执行（在本库实际跑一遍验收SQL确认列名正确）
- CLAUDE.md 中路径全部真实存在（逐一 ls 验证）
- 不写自动化测试（文档型产物）；验收=结构完整+路径/SQL实证

## 收尾

- 产物提交 git（_bmad-output 被 ignore，需 `git add -f`，沿用既有惯例）
- memory：parallel-sync-speedup 等已有条目不动；在会话锚点补一句 skill 已固化指针
