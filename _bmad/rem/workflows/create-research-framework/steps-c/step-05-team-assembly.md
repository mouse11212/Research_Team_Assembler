# Step 05: 团队组建与规模评估（Agent动态生成）

## 目标
根据课题需求、方法论选择和文献综述，动态生成Agent团队配置。

## 输入
- 课题分析报告（Step-01输出）
- 方法论选择报告（Step-02输出）
- 文献综述报告（Step-03输出）
- 研究设计方案（Step-04输出）

## 输出
- 团队配置方案
- Agent角色定义
- 主负责Agent指定

---

## Agent生成流程

### 三层生成逻辑（优先级从高到低）

```
┌─────────────────────────────────────────────────────────────┐
│ 第一层：课题关键词推导（最高优先级）                          │
├─────────────────────────────────────────────────────────────┤
│ 输入：课题关键词、研究领域                                    │
│ 处理：                                                       │
│   1. 提取课题中的领域术语                                    │
│   2. 匹配预设Agent模板库                                     │
│   3. 生成初步Agent列表                                       │
│ 输出：初步Agent配置                                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 第二层：文献综述细化（次优先级）                              │
├─────────────────────────────────────────────────────────────┤
│ 输入：文献综述的知识基础提取                                  │
│ 处理：                                                       │
│   1. 识别细分领域                                            │
│   2. 识别关键研究者/机构                                     │
│   3. 细化Agent的Knowledge Domains和Expertise Areas           │
│ 输出：细化Agent配置（从通用专家→细分领域专家）                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 第三层：方法论流程分解（第三优先级）                          │
├─────────────────────────────────────────────────────────────┤
│ 输入：选择的方法论                                           │
│ 处理：                                                       │
│   1. 分析方法论流程阶段                                      │
│   2. 匹配方法论Agent角色                                     │
│   3. 生成方法论类Agent                                       │
│ 输出：方法论Agent配置                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Agent生成规则

### 方法论类Agent（根据方法论自动配置）

| 方法论 | 必需Agent | 可选Agent |
|--------|----------|----------|
| **第一性原理** | 假设质疑者、逻辑推导者 | 证据验证者 |
| **系统性思维** | 要素分析者、关系建模者 | 动态仿真者 |
| **DSR设计科学** | 需求分析者、方案设计者 | 原型构建者、评估验证者 |

### 领域专家Agent（根据课题动态生成）

```yaml
domainExpertGeneration:
  # 匹配预设模板
  presetMatching:
    - keyword: "金融"
      template: "financial-expert"
    - keyword: "物理"
      template: "physics-expert"
    - keyword: "历史"
      template: "history-expert"
    # ... 更多预设模板

  # 未匹配时的动态生成
  dynamicGeneration:
    trigger: "预设模板未匹配"
    process:
      - 分析课题领域特征
      - 定义Agent角色和职责
      - 配置Knowledge Domains
      - 配置Expertise Areas
```

### 辅助Agent（固定配置）

| Agent | 职责 | 是否必需 |
|-------|------|---------|
| 研究协调员 | 团队协调、进度管理、冲突解决 | ✅ 必需 |
| 跨学科审查员 | 同行评审、跨领域验证 | ✅ 必需 |
| 知识管理者 | 文献管理、知识组织 | ✅ 必需 |
| 方法论专家 | 方法论指导、质量控制 | ✅ 必需 |

---

## 主负责Agent选择

### 选择标准

```yaml
leadAgentSelection:
  criteria:
    - 跨领域能力
    - 综合协调能力
    - 方法论熟悉度
  priority:
    - 首选：方法论专家（方法论复杂度高时）
    - 次选：研究协调员（团队规模大时）
    - 备选：跨学科审查员（需要强质量把控时）
```

---

## 输出模板

```yaml
teamConfiguration:
  # 基本信息
  topicId: "RF-{timestamp}"
  generatedAt: "{date}"

  # 团队规模
  totalSize: 8
  breakdown:
    methodologyAgents: 2
    domainExperts: 3
    auxiliaryAgents: 3

  # 主负责Agent
  leadAgent:
    name: "rem-agent-coordinator"
    displayName: "研究协调员"
    role: "主研究员"
    responsibilities:
      - "统筹研究进度"
      - "协调Agent协作"
      - "综合研究成果"

  # Agent配置
  agents:
    # 方法论类
    - id: "rem-agent-methodologist"
      role: "方法论专家"
      category: "methodology"
      collaborationMode:
        independent: true
        validation: true
        conflict: false

    - id: "rem-agent-first-principles-analyst"
      role: "假设质疑者"
      category: "methodology"
      collaborationMode:
        independent: true
        validation: true
        conflict: true

    # 领域专家类
    - id: "rem-agent-domain-expert-quantum"
      role: "量子计算专家"
      category: "domain_expert"
      knowledgeDomains:
        - "量子计算"
        - "量子算法"
      expertiseAreas:
        - "VQE算法"
        - "量子优化"
      collaborationMode:
        independent: true
        validation: true
        conflict: true

    - id: "rem-agent-domain-expert-finance"
      role: "金融领域专家"
      category: "domain_expert"
      knowledgeDomains:
        - "金融工程"
        - "风险管理"
      expertiseAreas:
        - "信用风险评估"
        - "期权定价"
      collaborationMode:
        independent: true
        validation: true
        conflict: true

    # 辅助类
    - id: "rem-agent-coordinator"
      role: "研究协调员"
      category: "auxiliary"
      collaborationMode:
        independent: true
        validation: true
        conflict: true

    - id: "rem-agent-reviewer"
      role: "跨学科审查员"
      category: "auxiliary"
      collaborationMode:
        independent: true
        validation: true
        conflict: true

    - id: "rem-agent-knowledge-manager"
      role: "知识管理者"
      category: "auxiliary"
      collaborationMode:
        independent: true
        validation: true
        conflict: false
```

---

## 完成条件

- [ ] 课题关键词分析完成
- [ ] 预设模板匹配完成
- [ ] 动态生成完成（如需要）
- [ ] 方法论Agent配置完成
- [ ] 领域专家Agent配置完成
- [ ] 辅助Agent配置完成
- [ ] 主负责Agent已指定
- [ ] 团队规模已评估

## 下一步

加载 `step-06-framework-design.md`
