# Step 09: 成果模板选择

## 目标
选择或生成研究最终成果的输出模板。

## 输入
- 硆念框架文档（Step-06输出）

## 输出
- 成果模板配置

---

## 五种成果模板

### 模板1：研究计划书

```markdown
# 研究计划书

## 基本信息
- **课题名称**：{topic}
- **研究者**：{researcher}
- **日期**：{date}

## 研究背景
{background}

## 研究目标
### 主要目标
1. {goal1}
2. {goal2}

### 次要目标
1. {goal1}

## 研究问题
### 主研究问题
{mainQuestion}

### 子问题
1. {sub1}
2. {sub2}

## 研究方法
### 方法论
{methodology}

### 数据收集
{dataCollection}

### 分析方法
{analysisMethods}

## 预期成果
{expectedDeliverables}

## 时间计划
| 阶段 | 时间 | 产出 |
|------|------|------|------|
| 阶段1 | {duration} | {deliverable} |
| 阶段2 | {duration} | {deliverable} |
| 最终 | - | | {finalReport} |

## 参考文献
{references}
```

---

### 模板2：文献综述报告

```markdown
# 文献综述报告

## 基本信息
- **课题**：{topic}
- **综述者**：{reviewer}
- **日期**：{date}

## 检索策略
### 数据库
{databases}

### 检索词
{keywords}

### 时间范围
{timeRange}

## 文献筛选
### 筛选标准
{criteria}

### 筛选结果
- 检索总数：{total}
- 筛选后：{filtered}

## 主要发现

### 领域1：{domain1}
{findings}

### 领域2：{domain2}
{findings}

## 研究空白
{researchGaps}

## 参考文献
{references}
```

---

### 模板3：阶段性报告
```markdown
# 阶段性研究报告

## 基本信息
- **阶段**：{phase}
- **日期**：{date}

## 本阶段目标
{objectives}

## 主要发现
{findings}

## 证据支撑
{evidence}

## 结论
{conclusions}

## 下一阶段计划
{nextSteps}
```

---

### 模板4：最终研究报告 (IMRAD结构)
```markdown
# 最终研究报告
## 基本信息
- **课题**：{topic}
- **研究者**：{researcher}
- **日期**：{date}

## 摘要
{abstract}

## 引言 (Introduction)
{introduction}

## 方法 (Methods)
{methods}

## 结果 (Results)
{results}

## 讨论 (Discussion)
{discussion}

## 结论 (Conclusion)
{conclusion}

## 参考文献
{references}
```

---

### 模板5：研究框架配置 (YAML)
```yaml
researchFramework:
  id: RF-{timestamp}
  topic: "研究课题"
  createdAt: {timestamp}

  selectedMethodology:
    id: "methodology-id"
    name: "方法论名称"
    rationale: "选择理由"

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

  fileStructure:
    root: "research-projects/{project-id}/"
    structure:
      - "01-课题定义/"
      - "02-文献综述/"
      - "03-研究设计/"
      - "04-Agent产出/"
      - "05-协作记录/"
      - "06-最终成果/"

  stateManagement:
    documents: []
    transitions: []

  templates:
    researchProposal: "模板路径"
    literatureReview: "模板路径"
    finalReport: "模板路径"
```

---

## 完成条件

- [ ] 5种模板已选择/定义
- [ ] 模板格式已确认
- [ ] 输出路径已配置

## 下一步

加载 `step-10-final-output.md`
