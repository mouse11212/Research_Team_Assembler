# Step 06: 研究框架设计

## 目标
设计完整的研究框架结构，包括文件目录、研究流程、 协作节点等。

## 输入
- 团队配置方案（Step-05输出）

## 输出
- 研究框架文档
- 文件目录结构定义
- 研究流程图

---

## 框架设计要素

### 1. 文件目录结构

```yaml
fileStructure:
  root: "research-projects/{project-id}/"
  structure:
    # 01 - 课题定义
    01-topic-definition/:
      - topic-brief.md          # 课题简介
      - constraints.md         # 约束条件
      - scope-definition.md    # 范围定义

    # 02 - 文献综述
    02-literature-review/:
      - search-strategy.md    # 检索策略
      - literature-analysis.md # 文献分析
      - research-gaps.md      # 研究空白

    # 03 - 研究设计
    03-research-design/:
      - research-questions.md # 研究问题
      - hypotheses.md         # 研究假设
      - methodology-plan.md   # 方法论计划
      - validation-criteria.md # 验证标准

    # 04 - Agent产出
    04-agent-outputs/:
      - {agent-id-1}/:
        - drafts/              # 草稿
        - reports/             # 报告
        - data/                # 数据
      - {agent-id-2}/:
        - drafts/
        - reports/
        - data/

    # 05 - 协作记录
    05-collaboration-logs/:
      - validation-records/   # 验证记录
      - conflict-records/     # 冲突记录
      - consensus-records/    # 共识记录
      - meeting-notes/        # 会议记录

    # 06 - 最终成果
    06-final-deliverables/:
      - research-proposal.md  # 研究计划书
      - final-report.md      # 最终报告
      - appendices/          # 附录
      - references.md        # 参考文献
```

### 2. 研究流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    研究框架流程                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │ 课题定义  │ -> │ 文献综述  │ -> │ 研究设计  │             │
│  └──────────┘    └──────────┘    └──────────┘             │
│        │              │              │                      │
│        v              v              v                      │
│  ┌──────────────────────────────────────────────┐         │
│  │              Agent团队组建                      │         │
│  └──────────────────────────────────────────────┘         │
│                       │                                     │
│                       v                                     │
│  ┌──────────────────────────────────────────────┐         │
│  │              独立研究阶段                      │         │
│  │  - 各Agent独立执行任务                        │         │
│  │  - 产出草稿文档                              │         │
│  └──────────────────────────────────────────────┘         │
│                       │                                     │
│                       v                                     │
│  ┌──────────────────────────────────────────────┐         │
│  │              互相印证阶段                      │         │
│  │  - 交叉验证研究成果                          │         │
│  │  - 记录共识与分歧                            │         │
│  └──────────────────────────────────────────────┘         │
│                       │                                     │
│          ┌────────────┴────────────┐                       │
│          v                         v                        │
│  ┌──────────────┐          ┌──────────────┐               │
│  │   达成共识    │          │   存在分歧    │               │
│  └──────────────┘          └──────────────┘               │
│          │                         │                        │
│          v                         v                        │
│  ┌──────────────┐          ┌──────────────┐               │
│  │   进入下一    │          │   冲突复盘    │               │
│  │   研究阶段    │          │   重新研究    │               │
│  └──────────────┘          └──────────────┘               │
│                                    │                        │
│                                    v                        │
│                            ┌──────────────┐               │
│                            │   达成共识    │               │
│                            └──────────────┘               │
│                                                             │
│  ┌──────────────────────────────────────────────┐         │
│  │              成果整合阶段                      │         │
│  │  - 综合各Agent研究成果                       │         │
│  │  - 生成最终报告                              │         │
│  └──────────────────────────────────────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. 协作节点定义

```yaml
collaborationNodes:
  # 里程碑节点
  milestones:
    - id: "M1"
      name: "课题定义完成"
      deliverables: ["topic-brief.md", "constraints.md"]
      next: "M2"

    - id: "M2"
      name: "文献综述完成"
      deliverables: ["literature-analysis.md", "research-gaps.md"]
      next: "M3"

    - id: "M3"
      name: "研究设计完成"
      deliverables: ["research-questions.md", "methodology-plan.md"]
      next: "M4"

    - id: "M4"
      name: "独立研究完成"
      trigger: "所有Agent提交草稿"
      next: "M5"

    - id: "M5"
      name: "交叉验证完成"
      trigger: "验证结果记录完成"
      next: "M6"

    - id: "M6"
      name: "成果整合完成"
      deliverables: ["final-report.md"]
      next: "END"
```

---

## 输出模板

```markdown
# 研究框架文档

## 框架信息
- 项目ID：{projectId}
- 创建日期：{date}
- 方法论：{methodology}

---

## 文件目录结构

```
research-projects/{project-id}/
├── 01-topic-definition/
│   ├── topic-brief.md
│   ├── constraints.md
│   └── scope-definition.md
├── 02-literature-review/
│   ├── search-strategy.md
│   ├── literature-analysis.md
│   └── research-gaps.md
├── 03-research-design/
│   ├── research-questions.md
│   ├── hypotheses.md
│   ├── methodology-plan.md
│   └── validation-criteria.md
├── 04-agent-outputs/
│   ├── {agent-1}/
│   └── {agent-2}/
├── 05-collaboration-logs/
│   ├── validation-records/
│   ├── conflict-records/
│   └── consensus-records/
└── 06-final-deliverables/
    ├── research-proposal.md
    ├── final-report.md
    └── references.md
```

---

## 研究流程

{流程图}

---

## 里程碑定义

| 里程碑 | 名称 | 触发条件 | 交付物 | 下一阶段 |
|--------|------|---------|--------|---------|
| M1 | 课题定义完成 | - | {deliverables} | M2 |
| M2 | 文献综述完成 | M1完成 | {deliverables} | M3 |
| M3 | 研究设计完成 | M2完成 | {deliverables} | M4 |
| M4 | 独立研究完成 | M3完成 | - | M5 |
| M5 | 交叉验证完成 | 验证完成 | - | M6 |
| M6 | 成果整合完成 | 共识达成 | {deliverables} | END |

---

## 协作节点

### 独立研究节点
- 触发条件：研究设计完成
- 参与Agent：{agent-list}
- 产出：各Agent草稿文档

### 互相印证节点
- 触发条件：所有Agent提交草稿
- 验证方式：{validation-method}
- 产出：验证记录、共识/分歧记录

### 冲突复盘节点
- 触发条件：存在未解决分歧
- 处理方式：{conflict-resolution-method}
- 产出：冲突解决报告或重新研究指令
```

---

## 完成条件

- [ ] 文件目录结构已定义
- [ ] 研究流程图已绘制
- [ ] 里程碑已定义
- [ ] 协作节点已定义
- [ ] 触发条件已明确

## 下一步

加载 `step-07-collaboration-rules.md`
