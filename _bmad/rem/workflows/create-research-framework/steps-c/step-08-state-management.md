# Step 08: 状态管理定义

## 目标
定义所有研究文档的状态管理机制， 包括状态定义、 切换条件、 判断依据。

## 输入
- 卡作规则配置（Step-07输出）

## 输出
- 状态管理配置

---

## 7状态定义

| 状态 | 含义 | 触发条件 | 允许操作 |
|------|------|---------|---------|
| **draft** | 初始撰写中 | Agent开始撰写文档 | 编辑、删除 |
| **pending_review** | 待审核 | Agent完成初稿 | 查看、提交审核 |
| **under_review** | 审核中 | 协调员分配验证任务 | 查看、等待审核结果 |
| **revision** | 修订中 | 发现问题需修改 | 编辑、重新提交 |
| **confirmed** | 已确认 | 交叉验证通过 | 查看、归档 |
| **divergent** | 有分歧 | 验证后仍有不同观点 | 查看、触发冲突复盘 |
| **archived** | 已归档 | 研究阶段结束 | 查看 |

---

## 状态转换规则

```yaml
stateTransitions:
  # 正向转换
  - from: draft
    to: pending_review
    condition: "Agent完成初稿"
    action: "提交审核"

  - from: pending_review
    to: under_review
    condition: "协调员分配验证任务"
    action: "开始验证"

  - from: under_review
    to: confirmed
    condition: "交叉验证通过，无分歧"
    action: "标记为已确认"

  - from: under_review
    to: divergent
    condition: "验证后仍有不同观点"
    action: "标记为有分歧，
  - from: under_review
    to: revision
    condition: "发现问题需修改"
    action: "返回修订"

  - from: revision
    to: pending_review
    condition: "修改完成"
    action: "重新提交审核"

  - from: divergent
    to: confirmed
    condition: "分歧解决，达成共识"
    action: "标记为已确认"

  - from: confirmed
    to: archived
    condition: "研究阶段结束"
    action: "归档保存"

  # 禁止转换
  forbidden:
    - "draft → confirmed"  # 必须经过验证
    - "draft → archived"   # 必须经过完整流程
    - "divergent → archived"  # 必须先解决分歧
```

---

## 状态判断依据

### 判断为"已确认"的条件

```yaml
confirmedCriteria:
  logicalConsistency:
    description: "逻辑论证完整无断裂"
    checkPoints:
      - "前提→推导→结论链完整"
      - "无逻辑跳跃"
      - "结论由证据支撑"

  evidenceSufficiency:
    description: "证据充分支持结论"
    checkPoints:
      - "关键证据齐全"
      - "证据来源可靠"
      - "证据链完整"

  crossDomainConsistency:
    description: "跨领域结论一致"
    checkPoints:
      - "不同领域结论无矛盾"
      - "术语使用一致"
      - "概念定义统一"

  methodologyCompliance:
    description: "方法论应用正确"
    checkPoints:
      - "方法论选择合理"
      - "方法论执行规范"
      - "质量标准满足"
```

### 判断为"有分歧"的条件

```yaml
divergentCriteria:
  logicalConflict:
    description: "逻辑论证存在冲突"
    indicators:
      - "不同Agent得出相反结论"
      - "证据解释存在争议"
      - "方法论应用存在分歧"

  evidenceGap:
    description: "证据不足以支持任何结论"
    indicators:
      - "关键证据缺失"
      - "证据质量不足"
      - "证据来源存疑"

  crossDomainConflict:
    description: "跨领域结论存在矛盾"
    indicators:
      - "不同领域结论相互矛盾"
      - "核心概念定义冲突"
      - "边界划分存在争议"
```

---

## 状态管理输出

```yaml
stateManagementConfig:
  documentTypes:
    - type: "研究报告"
      states: [draft, pending_review, under_review, revision, confirmed, divergent, archived]
    - type: "文献综述"
      states: [draft, pending_review, confirmed, archived]
    - type: "研究设计"
      states: [draft, pending_review, confirmed, archived]
    - type: "数据文件"
      states: [draft, confirmed, archived]
    - type: "协作记录"
      states: [draft, confirmed, archived]

  stateFields:
    - currentState
    - previousStates
    - lastTransitionTime
    - transitionReason
    - responsibleAgent
```

---

## 完成条件

- [ ] 7种状态已定义
- [ ] 状态转换规则已定义
- [ ] 判断依据已明确
- [ ] 文档类型状态映射已配置

## 下一步
加载 `step-09-templates.md`
