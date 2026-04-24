# 研究项目文件架构规范

## 概述
定义研究项目的标准文件结构， 确保研究可追溯、 状态可管理。

---

## 1. 顶层目录结构

```
_bmad-output/
└── research-projects/
    └── {project-id}/              # 每个研究课题独立目录
        ├── 00-meta/                # 元数据
        ├── 01-topic-definition/    # 课题定义
        ├── 02-literature-review/   # 文献综述
        ├── 03-research-design/     # 研究设计
        ├── 04-agent-outputs/       # Agent产出
        ├── 05-collaboration-logs/  # 协作记录
        └── 06-final-deliverables/  # 最终成果
```

---

## 2. 各目录详细结构

### 00-meta/ (元数据)
```
00-meta/
├── project-config.yaml      # 项目配置
├── framework-config.yaml    # 框架配置（Step-10输出）
├── agent-manifest.yaml      # Agent清单
└── status-tracker.yaml      # 状态追踪
```

### 01-topic-definition/ (课题定义)
```
01-topic-definition/
├── topic-brief.md           # 课题简介
├── constraints.md           # 约束条件
├── scope-definition.md      # 范围定义
└── keywords-analysis.md     # 关键词分析
```

### 02-literature-review/ (文献综述)
```
02-literature-review/
├── search-strategy.md       # 检索策略
├── literature-analysis.md   # 文献分析
├── research-gaps.md         # 研究空白
├── knowledge-extraction.yaml # 知识提取（用于Agent配置）
└── references.bib           # 参考文献库
```

### 03-research-design/ (研究设计)
```
03-research-design/
├── research-questions.md    # 研究问题
├── hypotheses.md            # 研究假设
├── methodology-plan.md      # 方法论计划
├── technical-approach.md    # 技术路线
├── validation-criteria.md   # 验证标准
├── risk-assessment.md       # 风险评估
└── timeline.md              # 时间线
```

### 04-agent-outputs/ (Agent产出)
```
04-agent-outputs/
├── {agent-id-1}/            # 每个Agent独立目录
│   ├── drafts/              # 草稿
│   │   └── *.md
│   ├── reports/             # 报告
│   │   └── *.md
│   ├── data/                # 数据
│   │   └── *.{json,yaml,csv}
│   └── status.yaml          # Agent状态
├── {agent-id-2}/
│   └── ...
└── agent-summary.md         # Agent产出汇总
```

### 05-collaboration-logs/ (协作记录)
```
05-collaboration-logs/
├── validation-records/      # 验证记录
│   ├── VR-{timestamp}-1.md
│   └── VR-{timestamp}-2.md
├── conflict-records/        # 冲突记录
│   ├── CR-{timestamp}-1.md
│   └── CR-{timestamp}-2.md
├── consensus-records/       # 共识记录
│   └── CS-{timestamp}-1.md
├── meeting-notes/           # 会议记录
│   └── MN-{timestamp}-1.md
└── collaboration-summary.md # 协作汇总
```

### 06-final-deliverables/ (最终成果)
```
06-final-deliverables/
├── research-proposal.md     # 研究计划书
├── final-report.md          # 最终报告（IMRAD格式）
├── executive-summary.md     # 执行摘要
├── appendices/              # 附录
│   ├── appendix-a.md
│   └── appendix-b.md
├── references.md            # 参考文献
└── archive/                 # 归档
    └── *.zip
```

---

## 3. 文件命名规范

| 文件类型 | 命名格式 | 示例 |
|---------|---------|------|
| 日期记录 | `{type}-{YYYYMMDD}-{seq}.md` | `VR-20260326-1.md` |
| Agent目录 | `{agent-role}-{domain}` | `domain-expert-physics` |
| 配置文件 | `{purpose}.yaml` | `project-config.yaml` |
| 报告文件 | `{purpose}.md` | `final-report.md` |

---

## 4. 状态追踪文件格式

```yaml
# status-tracker.yaml
project:
  id: "RF-{timestamp}"
  name: "{课题名称}"
  currentPhase: "{当前阶段}"
  overallStatus: "in_progress"  # in_progress/completed/on_hold

documents:
  - path: "01-topic-definition/topic-brief.md"
    status: "confirmed"
    lastUpdated: "{timestamp}"
    responsibleAgent: "coordinator"

  - path: "04-agent-outputs/{agent-id}/reports/analysis.md"
    status: "under_review"
    lastUpdated: "{timestamp}"
    responsibleAgent: "{agent-id}"

phases:
  - name: "课题定义"
    status: "completed"
    completionDate: "{date}"
  - name: "文献综述"
    status: "completed"
    completionDate: "{date}"
  - name: "研究设计"
    status: "in_progress"
    startDate: "{date}"
  - name: "独立研究"
    status: "pending"
  - name: "交叉验证"
    status: "pending"
  - name: "成果整合"
    status: "pending"
```

---

## 5. 研究项目隔离原则

### 隔离规则
1. **目录隔离**：每个研究课题在独立目录下
2. **配置隔离**：每个项目有独立的配置文件
3. **状态隔离**：每个项目有独立的状态追踪
4. **Agent隔离**：Agent产出按项目隔离

### 项目ID生成规则
```yaml
projectIdFormat:
  pattern: "RF-{YYYYMMDDHHMMSS}-{hash}"
  example: "RF-20260326143022-a1b2c3"
  components:
    - prefix: "RF"  # Research Framework
    - timestamp: "YYYYMMDDHHMMSS"
    - hash: "前6位MD5(课题名称)"
```
