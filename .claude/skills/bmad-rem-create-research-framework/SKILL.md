---
name: bmad-rem-create-research-framework
description: 根据研究课题自动创建完整、科学、可落地的研究框架。输入任意研究课题，输出方法论选择、Agent团队配置、协作规则、文件架构和成果模板。Use when the user requests to create a research framework, build a research team, or set up a research project.
---

# 创建研究框架 (Create Research Framework)

## 概述

这是**组团研究器**的核心入口技能。输入任意研究课题，自动输出完整、科学、可落地的研究框架。

**核心价值**：根据研究课题，快速、科学地一键搭建研究框架

**输出内容**：
1. 课题分析报告
2. 方法论选择与论证
3. 文献综述报告
4. 研究设计方案（9个核心问题）
5. Agent团队配置
6. 研究框架文档
7. 协作规则配置
8. 状态管理配置
9. 成果模板配置
10. 完整研究框架配置文件（YAML）

---

## 激活模式检测

检查激活上下文：

1. **自动模式**：如果用户传递 `--autonomous`/`-A` 标志，或提供结构化输入：
   - 摄取所有输入，生成完整框架无需交互
   - 路由到 `steps-c/step-01-analyze-topic.md` 并设置 `{mode}=autonomous`

2. **快速模式**：如果用户传递 `--quick` 或说"快速生成"/"一键生成"：
   - 跳过确认环节，使用默认配置快速生成框架
   - 路由到 `steps-c/step-01-analyze-topic.md` 并设置 `{mode}=quick`

3. **引导模式**（默认）：交互式发现与确认
   - 路由到 `steps-c/step-01-analyze-topic.md` 并设置 `{mode}=guided`

---

## 激活时执行

### 1. 加载配置

从 `{project-root}/_bmad/rem/config.yaml` 加载配置并解析：
- 使用 `{user_name}` 进行问候
- 使用 `{communication_language}` 进行所有通信
- 使用 `{document_output_language}` 输出文档
- 使用 `{research_projects}` 作为研究项目输出位置

### 2. 问候用户

以 `{user_name}` 问候，使用 `{communication_language}`。热情但高效——研究框架构建者风格。

### 3. 模式选择

"欢迎使用**组团研究器**！我将帮助你快速、科学地搭建研究框架。

**请选择工作模式：**

| 选项 | 模式 | 说明 |
|------|------|------|
| **[1]** | 引导模式 | 交互式确认每个步骤（推荐） |
| **[2]** | 快速模式 | 一键生成，使用默认配置 |
| **[3]** | 自动模式 | 基于提供的输入自动生成 |

**或者直接告诉我你的研究课题，我将自动选择合适的模式。**"

---

## 工作流阶段

| 阶段 | 步骤 | 目的 | 输出 |
|------|------|------|------|
| 1 | 课题分析 | 理解研究问题、判断问题类型 | 课题分析报告 |
| 2 | 方法论选择 | 根据问题类型选择方法论 | 方法论选择报告 |
| 3 | 文献综述 | 检索分析文献、识别研究空白 | 文献综述报告 |
| 4 | 研究设计 | 回答9个核心问题 | 研究设计方案 |
| 5 | 团队组建 | 动态生成Agent团队 | 团队配置方案 |
| 6 | 框架设计 | 设计文件结构和流程 | 研究框架文档 |
| 7 | 协作规则 | 定义三种协作模式规则 | 协作规则配置 |
| 8 | 状态管理 | 定义7状态工作流 | 状态管理配置 |
| 9 | 成果模板 | 选择/生成成果模板 | 成果模板配置 |
| 10 | 框架输出 | 生成最终配置文件 | 完整研究框架配置 |

---

## 核心组件

### 方法论选择矩阵

| 研究问题类型 | 推荐方法论 | Agent生成策略 |
|-------------|-----------|---------------|
| 根本性问题 | 第一性原理 | 预设模板为主 |
| 系统性问题 | 系统性思维 | 预设+动态 |
| 实践性问题 | DSR设计科学 | 预设+动态 |

### Agent生成优先级

1. **课题关键词推导** → 初步Agent列表
2. **文献综述细化** → 细分Agent列表
3. **方法论流程分解** → 方法论Agent列表

### 协作三种模式

| 模式 | 触发条件 | 敏捷映射 |
|------|---------|---------|
| 独立研究 | 任务不依赖其他Agent | Sprint执行期 |
| 互相印证 | 结论需多视角验证 | Review环节 |
| 冲突复盘 | 观点存在分歧 | Retrospective环节 |

### 文档7状态

`draft` → `pending_review` → `under_review` → `confirmed` / `revision` / `divergent` → `archived`

---

## 输入收集

### 必需输入
- **研究课题描述**：描述要研究的问题或主题

### 可选输入
- **研究领域**：如物理、金融、心理学等
- **研究目的**：学术研究/商业分析/问题解决
- **时间约束**：预计研究周期
- **已有文献**：已有的文献资料路径
- **特殊要求**：特定的方法论偏好或约束条件

---

## 输出结构

### 研究框架配置文件 (YAML)

```yaml
researchFramework:
  id: RF-{timestamp}
  topic: "研究课题"

  # 方法论选择
  selectedMethodology:
    id: "methodology-id"
    name: "方法论名称"
    rationale: "选择理由"

  # 团队配置
  teamComposition:
    totalSize: N
    leadAgent: {...}
    agents: [...]

  # 协作规则
  collaborationRules:
    independentResearch: {...}
    crossValidation: {...}
    conflictResolution: {...}

  # 文件结构
  fileStructure: {...}

  # 状态管理
  stateManagement: {...}

  # 成果模板
  templates: {...}
```

### 研究项目文件目录

```
research-projects/{project-id}/
├── 00-meta/                    # 元数据
├── 01-topic-definition/        # 课题定义
├── 02-literature-review/       # 文献综述
├── 03-research-design/         # 研究设计
├── 04-agent-outputs/           # Agent产出
├── 05-collaboration-logs/      # 协作记录
└── 06-final-deliverables/      # 最终成果
```

---

## 外部依赖

本工作流使用：
- `bmad-init` — 配置加载（模块: rem）
- Google Scholar API — 文献检索（可选）

---

## 质量保证

### 研究质量标准
- 所有研究结论必须有证据支撑
- 所有引用必须有明确出处
- 研究方法必须可复现
- 所有假设必须可验证

### 验证机制
- 交叉验证：多Agent互相印证
- 冲突复盘：分歧处理流程
- 状态管理：文档状态追踪

---

## 执行路由

**根据模式选择，加载对应的Step-File开始执行：**

- 所有模式 → 加载 `steps-c/step-01-analyze-topic.md`
- 后续步骤按顺序执行 Step-02 到 Step-10

---

## 快速命令

用户可以通过以下方式快速调用：

```
/create-research-framework    # 完整名称
/rem                          # 简写
/研究框架                      # 中文命令
```

或直接描述研究课题：
```
"帮我搭建一个关于量子计算在金融风控中应用的研究框架"
```
