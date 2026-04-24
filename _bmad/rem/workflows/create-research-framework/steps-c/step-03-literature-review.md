# Step 03: 文献综述

## 目标
系统性检索、筛选、分析相关文献，为研究提供知识基础，为Agent配置提供支撑。

## 输入
- 课题分析报告（Step-01输出）
- 方法论选择报告（Step-02输出）

## 输出
- 文献综述报告
- 知识基础提取（用于Agent配置）

## 支持模式

| 模式 | 描述 | 触发条件 |
|------|------|---------|
| **用户自供** | 用户提供已完成的文献综述 | 用户选择 |
| **AI辅助** | 系统调用Google Scholar API检索 | 用户选择 |

---

## 执行流程

### 1. 确定检索策略

```yaml
searchStrategy:
  # 核心关键词
  primaryKeywords:
    - "{从课题分析提取}"
  # 扩展关键词
  expandedKeywords:
    - "{同义词/相关词}"
  # 检索范围
  scope:
    timeRange: "近5年/近10年/不限"
    domains: "{研究领域列表}"
  # 数据库
  databases:
    - google_scholar
```

### 2. 调用Google Scholar API

```yaml
apiCall:
  endpoint: "https://serpapi.com/search"
  parameters:
    engine: "google_scholar"
    q: "{检索词组合}"
    hl: "zh-CN"
    num: 20
    as_ylo: "{起始年份}"
```

### 3. 文献筛选

筛选标准：
- 与研究问题的相关性
- 来源权威性（期刊影响因子、引用次数）
- 时效性（发表时间）
- 研究方法的科学性

### 4. 信息提取

从筛选后的文献中提取：

```yaml
literatureExtraction:
  papers:
    - title: "文献标题"
      authors: ["作者1", "作者2"]
      year: 2024
      source: "期刊/会议"
      citations: 100
      summary: "研究摘要"
      keyFindings:
        - "关键发现1"
        - "关键发现2"
      methodology: "使用的研究方法"
      relevance: "与本课题的相关性"
```

### 5. 知识基础提取

为Agent配置提供支撑：

```yaml
knowledgeBase:
  # 研究领域知识图谱
  domainKnowledge:
    - domain: "领域1"
      keyConcepts: ["概念1", "概念2"]
      majorResearchers: ["研究者1", "研究者2"]
      leadingInstitutions: ["机构1", "机构2"]

  # 研究空白
  researchGaps:
    - gap: "研究空白1"
      significance: "高/中/低"

  # 创新点定位
  innovationPoints:
    - point: "创新点1"
      basis: "基于文献X的发现"
```

---

## 输出模板

```markdown
# 文献综述报告

## 综述信息
- 综述日期：{date}
- 检索策略：{AI辅助/用户自供}
- 检索范围：{数据库、时间范围}

## 检索结果概览
- 检索总数：{total}
- 筛选后数量：{filtered}
- 深度分析数量：{analyzed}

## 文献分析

### 按领域分类

| 领域 | 文献数量 | 主要发现 |
|------|---------|---------|
| {领域1} | {count} | {findings} |
| {领域2} | {count} | {findings} |

### 关键文献

#### 文献1：{title}
- **作者**：{authors}
- **年份**：{year}
- **来源**：{source}
- **引用**：{citations}
- **摘要**：{summary}
- **关键发现**：
  - {finding1}
  - {finding2}
- **方法论**：{methodology}
- **相关性**：{relevance}

## 研究现状总结

### 已有研究
{已有研究的主要贡献和发现}

### 研究空白
| 空白描述 | 重要性 | 填补方式 |
|---------|--------|---------|
| {gap1} | 高/中/低 | {approach} |

### 创新点定位
{本课题相对于已有研究的创新点}

## Agent配置支撑

### 领域知识
- **核心概念**：{concepts}
- **主要研究者**：{researchers}
- **领先机构**：{institutions}

### 建议Agent配置
基于文献综述，建议配置以下Agent：
| Agent类型 | 数量 | 领域 | 理由 |
|----------|-----|------|------|
| {type} | {count} | {domain} | {reason} |

## 参考文献
{formatted references}
```

---

## 完成条件

- [ ] 检索策略已确定
- [ ] 文献检索已完成（AI辅助模式）
- [ ] 文献筛选已完成
- [ ] 关键信息已提取
- [ ] 研究空白已识别
- [ ] 创新点已定位
- [ ] Agent配置建议已生成

## 下一步

加载 `step-04-research-design.md`
