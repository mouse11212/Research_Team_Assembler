# Step 04: 研究设计（9个核心问题）

## 目标
回答研究设计的9个核心问题，形成完整的研究设计方案。

## 输入
- 课题分析报告（Step-01输出）
- 方法论选择报告（Step-02输出）
- 文献综述报告（Step-03输出）

## 输出
- 研究设计方案

---

## 9个核心问题

### 问题1：核心研究问题是什么？

```yaml
question1:
  question: "核心研究问题是什么？"
  output:
    mainQuestion: "主研究问题"
    subQuestions:
      - "子问题1"
      - "子问题2"
    questionScope: "问题边界"
```

### 问题2：研究的目标和最终交付成果是什么？

```yaml
question2:
  question: "研究的目标和最终交付成果是什么？"
  output:
    primaryGoal: "主要目标"
    secondaryGoals:
      - "次要目标1"
      - "次要目标2"
    deliverables:
      - name: "交付物1"
        format: "格式"
        criteria: "验收标准"
```

### 问题3：研究边界/范围是什么？

```yaml
question3:
  question: "研究边界/范围是什么？"
  output:
    inScope:
      - "范围内1"
      - "范围内2"
    outOfScope:
      - "范围外1"
      - "范围外2"
    boundaryRationale: "边界设定理由"
```

### 问题4：核心研究假设（假说）是什么？

```yaml
question4:
  question: "核心研究假设（假说）是什么？"
  output:
    hypotheses:
      - id: "H1"
        statement: "假设陈述"
        testable: true/false
        variables:
          independent: "自变量"
          dependent: "因变量"
```

### 问题5：选用哪种研究方法论+技术路线？

```yaml
question5:
  question: "选用哪种研究方法论+技术路线？"
  output:
    selectedMethodology:
      id: "methodology-id"
      name: "方法论名称"
      rationale: "选择理由"
    technicalApproach:
      phases:
        - phase: "阶段1"
          activities: ["活动1", "活动2"]
          duration: "时长"
        - phase: "阶段2"
          activities: ["活动1", "活动2"]
          duration: "时长"
```

### 问题6：数据/文献/实验资源从哪获取、如何处理？

```yaml
question6:
  question: "数据/文献/实验资源从哪获取、如何处理？"
  output:
    dataSources:
      - type: "数据类型"
        source: "来源"
        accessMethod: "获取方式"
        processingSteps: ["处理步骤1", "处理步骤2"]
    literatureSources:
      - database: "数据库"
        searchStrategy: "检索策略"
    experimentResources:
      - resource: "资源"
        availability: "可用性"
```

### 问题7：如何验证研究成果有效？

```yaml
question7:
  question: "如何验证研究成果有效？"
  output:
    validationApproach:
      metrics:
        - metric: "评价指标1"
          target: "目标值"
          measurement: "测量方法"
      methods:
        - method: "验证方法1"
          description: "描述"
          criteria: "标准"
```

### 问题8：研究风险、局限性是什么？

```yaml
question8:
  question: "研究风险、局限性是什么？"
  output:
    risks:
      - risk: "风险1"
        probability: "高/中/低"
        impact: "高/中/低"
        mitigation: "缓解措施"
    limitations:
      - limitation: "局限性1"
        impact: "影响描述"
        acknowledgment: "如何处理"
```

### 问题9：研究阶段划分、每个阶段的交付物是什么？

```yaml
question9:
  question: "研究阶段划分、每个阶段的交付物是什么？"
  output:
    phases:
      - id: "P1"
        name: "阶段名称"
        duration: "时长"
        activities: ["活动1", "活动2"]
        deliverables:
          - name: "交付物1"
            format: "格式"
            criteria: "验收标准"
        milestones:
          - milestone: "里程碑1"
            date: "日期"
```

---

## 输出模板

```markdown
# 研究设计方案

## 方案信息
- 设计日期：{date}
- 方法论：{methodology}
- 预计周期：{duration}

---

## 问题1：核心研究问题

### 主研究问题
{mainQuestion}

### 子问题
1. {subQuestion1}
2. {subQuestion2}

### 问题边界
{questionScope}

---

## 问题2：研究目标与交付成果

### 研究目标
**主要目标**：{primaryGoal}

**次要目标**：
1. {secondaryGoal1}
2. {secondaryGoal2}

### 交付成果
| 交付物 | 格式 | 验收标准 |
|--------|------|---------|
| {name} | {format} | {criteria} |

---

## 问题3：研究边界

### 范围内
- {inScope1}
- {inScope2}

### 范围外
- {outOfScope1}
- {outOfScope2}

### 边界理由
{boundaryRationale}

---

## 问题4：研究假设

| 假设ID | 假设陈述 | 可验证 | 自变量 | 因变量 |
|--------|---------|--------|--------|--------|
| H1 | {statement} | ✓/✗ | {independent} | {dependent} |

---

## 问题5：方法论与技术路线

### 选定方法论
- **方法论**：{methodology}
- **选择理由**：{rationale}

### 技术路线
```
阶段1: {phase1} ({duration})
├── 活动1: {activity}
├── 活动2: {activity}
└── 里程碑: {milestone}

阶段2: {phase2} ({duration})
├── 活动1: {activity}
└── 里程碑: {milestone}
```

---

## 问题6：资源获取与处理

### 数据资源
| 类型 | 来源 | 获取方式 | 处理步骤 |
|------|------|---------|---------|
| {type} | {source} | {method} | {steps} |

### 文献资源
| 数据库 | 检索策略 |
|--------|---------|
| {database} | {strategy} |

---

## 问题7：验证方法

### 评价指标
| 指标 | 目标值 | 测量方法 |
|------|--------|---------|
| {metric} | {target} | {measurement} |

### 验证方法
1. **{method}**：{description}
   - 标准：{criteria}

---

## 问题8：风险与局限性

### 研究风险
| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| {risk} | {prob} | {impact} | {mitigation} |

### 研究局限性
| 局限性 | 影响 | 处理方式 |
|--------|------|---------|
| {limitation} | {impact} | {handling} |

---

## 问题9：阶段划分

| 阶段 | 时长 | 主要活动 | 交付物 | 里程碑 |
|------|------|---------|--------|--------|
| P1 | {duration} | {activities} | {deliverables} | {milestone} |
| P2 | {duration} | {activities} | {deliverables} | {milestone} |

---

## 方案确认

- [ ] 核心研究问题已明确
- [ ] 研究目标已量化
- [ ] 研究边界已界定
- [ ] 研究假设可验证
- [ ] 方法论已选定
- [ ] 资源已确认
- [ ] 验证方法已定义
- [ ] 风险已评估
- [ ] 阶段已划分
```

---

## 完成条件

- [ ] 9个问题全部回答
- [ ] 研究目标可量化
- [ ] 研究假设可验证
- [ ] 技术路线可行
- [ ] 资源可获取
- [ ] 验证方法可执行

## 下一步

加载 `step-05-team-assembly.md`
