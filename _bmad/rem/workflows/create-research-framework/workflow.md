---
name: bmad-rem-create-research-framework
description: 根据研究课题创建完整的研究框架，包括方法论选择、团队组建、协作规则定义
web_bundle: true
---

# 创建研究框架 (Create-research-framework)

**目标**：根据研究课题创建完整的研究框架，输出可执行的研究框架配置文件

**角色**：研究框架构建专家
---

## 工作流架构

本工作流采用**三模式Step-File架构**：
- **Create模式 (steps-c/)**：主要执行流程
- **Validate模式 (steps-v/)**：验证检查
- **Edit模式 (steps-e/)**：修订现有输出
---

## 初始化序列
### 1. 模式确定
"欢迎使用研究框架创建工作流。您想要做什么？"
- **[C] 创建** — 创建新的研究框架
- **[r] 恢复** — 恢复中断的工作流
- **[v] 验证** — 验证现有的研究框架
- **[e] 编辑** — 编辑现有的研究框架
### 2. 路由到第一步
- **如果C：** 加载 `steps-c/step-01-analyze-topic.md`
- **如果R：** 加载 `steps-c/step-01b-resume.md`
- **如果v：** 加载 `steps-v/step-01-validate.md`
- **如果e：** 加载 `steps-e/step-01-assess.md`
---
## 工作流阶段概览
| 阶段 | 步骤 | 描述 | 输出 |
|------|------|------|------|
| 1-分析 | step-01 | 课题分析与理解 | 课题分析报告 |
| 2-方法论 | step-02 | 方法论选择与论证 | 方法论选择报告 |
| 3-文献 | step-03 | 文献综述（调用Google Scholar） | 文献综述报告 |
| 4-设计 | step-04 | 研究设计（9个核心问题） | 研究设计方案 |
| 5-团队 | step-05 | 团队组建与规模评估 | 团队配置方案 |
| 6-框架 | step-06 | 研究框架设计 | 研究框架文档 |
| 7-协作 | step-07 | 协作规则定义 | 协作规则配置 |
| 8-状态 | step-08 | 状态管理定义 | 状态管理配置 |
| 9-模板 | step-09 | 成果模板选择/生成 | 成果模板配置 |
| 10-输出 | step-10 | 生成最终框架文件 | 完整研究框架配置 |
---
## 核心输出
### 研究框架配置文件
```yaml
researchFramework:
  id: RF-{timestamp}
  topic: "研究课题"
  createdAt: {timestamp}
  # 方法论选择
  selectedMethodology:
    id: "methodology-id"
    name: "方法论名称"
    rationale: "选择理由"
  # 团队配置
  teamComposition:
    totalSize: N
    leadAgent:
      name: "主负责Agent"
      domain: "领域"
    agents:
      - role: "角色"
        domain: "领域"
        responsibilities: []
        expertise: []
  # 协作规则
  collaborationRules:
    independentResearch:
      trigger: "..."
      process: []
    crossValidation:
      trigger: "..."
      process: []
    conflictResolution:
      trigger: "..."
      process: []
  # 文件结构
  fileStructure:
    root: "research-projects/{project-id}/"
    structure:
      - "01-课题定义/"
      - "02-文献综述/"
      - "03-研究设计/"
      - "04-Agent产出/"
      - "05-协作记录/"
      - "06-最终成果/"
  # 状态管理
  stateManagement:
    documents: []
    transitions: []
  # 成果模板
  templates:
    researchProposal: "模板路径"
    literatureReview: "模板路径"
    milestoneReport: "模板路径"
    finalReport: "模板路径"
```
---
## 后续步骤
根据选择的模式，加载相应的第一步文件开始执行。
