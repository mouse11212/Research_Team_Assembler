# Step 07: 协作规则定义

## 目标
定义三种协作模式的详细规则， 包括触发条件、 执行流程、 产出格式。

## 输入
- 研究框架文档（Step-06输出）

## 输出
- 协作规则配置

---

## 三种协作模式

### 模式1：独立研究

```yaml
independentResearch:
  # 触发条件
  trigger:
    condition: "Agent任务不依赖其他Agent输出"
    examples:
      - "领域专家进行本领域的文献综述"
      - "Agent撰写独立研究报告"

  # 执行流程
  process:
    - step: 1
      action: "接收任务分配"
      actor: "协调员"
    - step: 2
      action: "独立执行研究任务"
      actor: "领域专家"
    - step: 3
      action: "撰写研究报告"
      actor: "领域专家"
    - step: 4
      action: "提交成果"
      actor: "领域专家"
    - step: 5
      action: "审核产出质量"
      actor: "协调员"

  # 产出格式
  output:
    format: "独立研究报告"
    required_sections:
      - "研究背景"
      - "分析方法"
      - "主要发现"
      - "证据支撑"
      - "结论建议"
    file_path: "04-agent-outputs/{agent-id}/reports/"
```

### 模式2：互相印证

```yaml
crossValidation:
  # 触发条件
  trigger:
    condition: "研究结论需多视角验证"
    examples:
      - "跨领域概念边界验证"
      - "方法论应用一致性检查"
      - "证据充分性验证"

  # 执行流程
  process:
    - step: 1
      action: "识别验证点"
      actor: "协调员"
      output: "验证任务清单"
    - step: 2
      action: "分配验证任务"
      actor: "协调员"
      output: "验证任务分配表"
    - step: 3
      action: "执行交叉验证"
      actor: "审查员/其他专家"
      output: "验证报告"
    - step: 4
      action: "汇总验证结果"
      actor: "协调员"
      output: "验证汇总报告"
    - step: 5
      action: "记录共识或分歧"
      actor: "协调员"
      output: "共识/分歧记录"

  # 验证标准
  validationCriteria:
    - criterion: "逻辑一致性"
      description: "结论与证据逻辑一致"
      weight: 0.3
    - criterion: "证据充分性"
      description: "证据足够支撑结论"
      weight: 0.3
    - criterion: "跨领域一致性"
      description: "与其他领域结论不矛盾"
      weight: 0.2
    - criterion: "方法论规范性"
      description: "方法论应用正确"
      weight: 0.2

  # 分歧记录格式
  divergenceRecord:
    format:
      - "分歧点描述"
      - "涉及Agent"
      - "各方观点"
      - "证据对比"
      - "建议处理方式"

  # 产出格式
  output:
    format: "验证报告"
    file_path: "05-collaboration-logs/validation-records/"
```

### 模式3：冲突复盘

```yaml
conflictResolution:
  # 触发条件
  trigger:
    condition: "研究观点存在分歧"
    examples:
      - "交叉验证后发现矛盾结论"
      - "方法论应用存在争议"
      - "证据解释存在分歧"

  # 执行流程
  process:
    - step: 1
      action: "识别冲突点"
      actor: "协调员"
      output: "冲突识别报告"
    - step: 2
      action: "收集各方证据"
      actor: "协调员"
      output: "证据汇总表"
    - step: 3
      action: "组织协调会议"
      actor: "协调员"
      participants: "所有相关Agent"
    - step: 4
      action: "引导讨论"
      actor: "协调员"
      activities:
        - "各方陈述观点"
        - "证据对比分析"
        - "寻找共同点"
    - step: 5
      action: "尝试达成共识"
      actor: "协调员"
      possible_outcomes:
        - "达成共识"
        - "记录分歧"
        - "触发重新研究"
    - step: 6
      action: "记录处理结果"
      actor: "协调员"
      output: "冲突解决报告"

  # 证据收集流程
  evidenceCollection:
    - "各方提交支撑证据"
    - "证据来源验证"
    - "证据可信度评估"
    - "证据对比分析"

  # 共识达成机制
  consensusMechanism:
    methods:
      - id: "evidence-based"
        name: "证据优先"
        description: "以证据充分性决定"
      - id: "methodology-guided"
        name: "方法论指导"
        description: "方法论专家裁决"
      - id: "majority-vote"
        name: "多数同意"
        description: "多数Agent同意"

  # 重新研究触发条件
  reResearchTrigger:
    conditions:
      - "证据不足以支撑任何结论"
      - "方法论应用存在根本错误"
      - "研究假设被证伪"
    process:
      - "方法论专家重新审视研究设计"
      - "调整研究方案"
      - "重新分配研究任务"

  # 产出格式
  output:
    format: "冲突解决报告"
    file_path: "05-collaboration-logs/conflict-records/"
```

---

## 协作规则配置输出

```yaml
collaborationRules:
  # 独立研究规则
  independentResearch:
    enabled: true
    maxConcurrentAgents: 5
    qualityCheckRequired: true

  # 互相印证规则
  crossValidation:
    enabled: true
    minValidators: 2
    validationCriteria:
      - logic_consistency
      - evidence_sufficiency
      - cross_domain_consistency
      - methodology_compliance

  # 冲突复盘规则
  conflictResolution:
    enabled: true
    maxResolutionAttempts: 3
    reResearchAllowed: true
    escalationPath:
      - "协调员调解"
      - "方法论专家裁决"
      - "重新研究"
```

---

## 完成条件

- [ ] 独立研究规则已定义
- [ ] 互相印证规则已定义
- [ ] 冲突复盘规则已定义
- [ ] 触发条件已明确
- [ ] 执行流程已定义
- [ ] 产出格式已定义

## 下一步

加载 `step-08-state-management.md`
